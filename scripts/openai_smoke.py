#!/usr/bin/env python3
"""Isolated OpenAI Responses smoke harness (Phase 47). NOT product code; never run by make, pytest, CI or the benchmark.

Purpose: one controlled check that the recorded contract (research/openai-api-reference-2026-10-19) matches the real
endpoint, once the owner has authorised it (docs/SMOKE-RUNBOOK.md). It answers API-compatibility questions only
(G-4, G-5, G-7, G-8, and the shapes behind G-1/G-2). It says NOTHING about diagnosis quality.

It drives the product's own codec (`OpenAIResponsesWire`) and adapter (`HTTPProvider`) through a guarded transport.
That transport allows only https://api.openai.com/v1/responses, caps request and response sizes, and records a
content-free shape summary of each exchange. The conversation is fixed and synthetic: no repository content, logs,
credentials or benchmark data.

Modes (exactly one):
  --offline SCENARIO   deterministic fixtures through httpx.MockTransport; synthetic key; no network.
  --live               a real request. Refused unless --model, --key-file and --authorization-ref are all given;
                       refused under pytest or CI. The key is read ONLY from --key-file (owner-only permissions,
                       outside the repository), never from the environment, and never printed.

Evidence goes to stdout as one JSON document: outcome classes, HTTP statuses, item types, booleans, lengths and token
counts. Never text, arguments, ids, reasoning items, encrypted_content, error messages or headers.
Reasoning items are held in memory only for the replay step and then dropped.

Exit codes: 0 pass; 2 refused (configuration or safety); 3 transport or timeout; 4 auth (401/403); 5 quota/billing
(never retried); 6 rate-limited or unavailable (429/5xx; no retries); 7 request refused (other 4xx); 8 unsupported
response (malformed, incomplete, refusal, unknown shape, too large); 9 contract compatible but an observation is
missing (e.g. the model did not call the tool).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from tracewise.context.tools import TOOL_NAMES
from tracewise.investigate import deadline_http, model_access
from tracewise.investigate.deadline_http import (  # re-exported: the harness and its tests use these names
    DeadlineBackend as DeadlineBackend,
)
from tracewise.investigate.deadline_http import DeadlineExceeded, DeadlineHTTPTransport
from tracewise.investigate.deadline_http import DeadlineStream as DeadlineStream
from tracewise.investigate.http_adapter import (
    AdapterConfig,
    HTTPProvider,
    ProviderAuthError,
    ProviderQuotaError,
    ProviderRequestError,
    ProviderUnavailable,
)
from tracewise.investigate.openai_responses import ENDPOINT, OpenAIResponsesWire
from tracewise.investigate.prompt import TOOL_SPECS
from tracewise.investigate.provider import Message, ProviderError, ProviderTimeout, StepRequest, StepResponse

REPO_ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ fixed limits (docs/SMOKE-RUNBOOK.md §4)
MAX_REQUESTS = 3  # HTTP attempts in total; no retries (max_retries=0)
MAX_REQUEST_BYTES = 32_768
MAX_RESPONSE_BYTES = 262_144
MAX_OUTPUT_CHARS = 2_048  # also sent as max_output_tokens
STEP_TIMEOUT_S = 30.0
TOTAL_DEADLINE_S = 90.0

# ------------------------------------------------------------------ the fixed synthetic conversation (§3)
INSTRUCTIONS = "You are a test fixture for an API compatibility check. Follow the user's instruction exactly."
TEXT_PROMPT = "Reply with exactly the two letters OK and nothing else."
TOOL_PROMPT = 'Call the list_dir tool exactly once with the argument path set to "docs". Do not reply with text.'
TOOL_RESULT = "README.md\nGUIDE.md\n"  # synthetic directory listing; no real repository is read
FINAL_PROMPT = "Now reply with exactly the two letters OK and nothing else."

OFFLINE_KEY = "offline-smoke-not-a-key"
_ENUM = re.compile(r"^[a-z0-9_.]{1,64}$")

EXIT = {
    "pass": 0,
    "refused": 2,
    "transport": 3,
    "auth": 4,
    "quota": 5,
    "unavailable": 6,
    "request_refused": 7,
    "unsupported_response": 8,
    "observation_missing": 9,
    "deadline": 10,
    "harness_error": 1,
}


class Refused(Exception):
    """Configuration or safety refusal: nothing (more) was sent."""


class ResponseTooLarge(Exception):
    """The provider's response exceeded the smoke cap: an unsupported response, not a transport failure."""


class SchemaViolation(Exception):
    """Valid JSON whose structure is not the recorded one: an unsupported response (exit 8)."""


# ------------------------------------------------------------------ wall-clock deadline


class Deadline(deadline_http.Deadline):
    """The run's wall-clock deadline (§4a). The socket-level enforcement lives in
    `tracewise.investigate.deadline_http` (shared with the benchmark's model mode); each step's deadline is
    min(step start + STEP_TIMEOUT_S, run start + TOTAL_DEADLINE_S)."""

    def start_step(self, overall_at: float, step_timeout_s: float = STEP_TIMEOUT_S) -> None:
        super().start_step(overall_at, step_timeout_s)


# ------------------------------------------------------------------ guarded, recording transport


def _enum(v: Any) -> str | None:
    """Record provider enum-like values (status, error.code, ...) only when they look like identifiers."""
    if v is None:
        return None
    return v if isinstance(v, str) and _ENUM.match(v) else "<other>"


def request_shape(body: bytes) -> dict[str, Any]:
    doc = json.loads(body)
    items = doc.get("input", [])
    return {
        "bytes": len(body),
        "keys": sorted(doc),
        "store": doc.get("store"),
        "tools": len(doc.get("tools", [])),
        "tool_choice": _enum(doc.get("tool_choice")),
        "max_output_tokens": doc.get("max_output_tokens"),
        "input_item_types": [_enum(i.get("type")) for i in items if isinstance(i, dict)],
    }


def response_shape(status: int, body: bytes, headers: httpx.Headers) -> dict[str, Any]:
    """Content-free summary of a response. Every JSON type is checked before it is iterated or measured; anything
    not in the recorded structure becomes a fixed `schema_violations` code (never the offending value)."""
    out: dict[str, Any] = {
        "http_status": status,
        "bytes": len(body),
        "retry_after_present": "retry-after" in headers,
        "ratelimit_headers": sorted(h for h in headers if h.lower().startswith("x-ratelimit-")),
    }
    violations: set[str] = set()
    try:
        doc = json.loads(body)
    except ValueError:
        out["json"] = False
        return out
    out["json"] = True
    if not isinstance(doc, dict):
        out["top_level"] = _enum(type(doc).__name__)
        out["schema_violations"] = ["top_level_not_object"]
        return out
    out["keys"] = sorted(k for k in doc if _ENUM.match(k))
    err = doc.get("error")
    if isinstance(err, dict):  # G-2: the error body shape; never the message
        out["error"] = {
            "code": _enum(err.get("code")),
            "type": _enum(err.get("type")),
            "keys": sorted(k for k in err if _ENUM.match(k))[:10],
        }
    elif err is not None:
        violations.add("error_not_object")
    out["object"] = _enum(doc.get("object"))
    out["status"] = _enum(doc.get("status"))
    inc = doc.get("incomplete_details")
    if isinstance(inc, dict):
        out["incomplete_reason"] = _enum(inc.get("reason"))  # G-1
    elif inc is not None:
        violations.add("incomplete_details_not_object")
    output = doc.get("output")
    items: list[dict[str, Any]] = []
    if isinstance(output, list):
        for it in output:
            items.append(_item_shape(it, violations))
    elif output is not None:
        violations.add("output_not_list")
    out["output"] = items
    usage = doc.get("usage")
    if isinstance(usage, dict):
        out["usage"] = {k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens") if type(usage.get(k)) is int}
        # R-11 breakdowns, integers only: whether reasoning tokens sit inside `output_tokens` (and so inside the
        # 2,048 `max_output_tokens` cap) and whether any input was billed as cached are unknowns the run should record.
        for parent, key in (("output_tokens_details", "reasoning_tokens"), ("input_tokens_details", "cached_tokens")):
            detail = usage.get(parent)
            if isinstance(detail, dict) and type(detail.get(key)) is int:
                out["usage"][key] = detail[key]
    elif usage is not None:
        violations.add("usage_not_object")
    if violations:
        out["schema_violations"] = sorted(violations)
    return out


def _item_shape(it: Any, violations: set[str]) -> dict[str, Any]:
    if not isinstance(it, dict):
        violations.add("item_not_object")
        return {"type": "<not-an-object>"}
    kind = it.get("type")
    if not isinstance(kind, str):
        violations.add("item_type_not_string")
    rec: dict[str, Any] = {"type": _enum(kind)}
    if kind == "reasoning":  # G-8: presence and size only; the payload is never recorded
        enc, summary = it.get("encrypted_content"), it.get("summary")
        if enc is not None and not isinstance(enc, str):
            violations.add("encrypted_content_not_string")
        if summary is not None and not isinstance(summary, list):
            violations.add("summary_not_list")
        rec["encrypted_content_present"] = isinstance(enc, str) and bool(enc)
        rec["summary_parts"] = len(summary) if isinstance(summary, list) else 0
    elif kind == "function_call":  # G-5: the id length, never the id
        cid, args = it.get("call_id"), it.get("arguments")
        if not isinstance(cid, str):
            violations.add("call_id_not_string")
        if not isinstance(args, str):
            violations.add("arguments_not_string")
        rec["call_id_length"] = len(cid) if isinstance(cid, str) else None
        rec["known_tool"] = it.get("name") in TOOL_NAMES
        rec["arguments_is_string"] = isinstance(args, str)
    elif kind == "message":
        content = it.get("content")
        types: list[str | None] = []
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    violations.add("content_part_not_object")
                    continue
                types.append(_enum(part.get("type")))
                if part.get("type") == "output_text" and not isinstance(part.get("text"), str):
                    violations.add("text_not_string")
        else:
            violations.add("content_not_list")
        rec["content_types"] = types
    return rec


class GuardedTransport(httpx.BaseTransport):
    """Only the recorded endpoint; bounded sizes; a hard request budget; the wall-clock deadline (checked before
    sending and after every chunk of the body); a content-free record of every exchange."""

    def __init__(self, inner: httpx.BaseTransport, deadline: Deadline) -> None:
        self.inner, self.deadline = inner, deadline
        self.records: list[dict[str, Any]] = []
        self.sent = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.deadline.remaining() <= 0:
            raise DeadlineExceeded()  # nothing starts after the deadline
        if str(request.url) != ENDPOINT or request.method != "POST":
            raise Refused("only POST to the recorded endpoint is allowed")
        if self.sent >= MAX_REQUESTS:
            raise Refused("request budget exhausted")
        body = request.read()
        if len(body) > MAX_REQUEST_BYTES:
            raise Refused("request exceeds the size cap")
        rec: dict[str, Any] = {"request": request_shape(body)}
        self.records.append(rec)
        self.sent += 1
        raw = bytearray()
        try:
            resp = self.inner.handle_request(request)
            try:
                for chunk in resp.iter_bytes():  # decoded; bounded in size and time while reading
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        rec["response"] = {"http_status": resp.status_code, "too_large": True}
                        raise ResponseTooLarge()
                    if self.deadline.remaining() <= 0:
                        raise DeadlineExceeded()
            finally:
                resp.close()
        except DeadlineExceeded:
            rec["deadline_exceeded"] = True
            raise
        except httpx.TransportError as e:
            if self.deadline.expired:  # the watchdog or a clamped socket operation cut the exchange off
                rec["deadline_exceeded"] = True
                raise DeadlineExceeded() from None
            rec["transport_error"] = type(e).__name__
            raise
        shape = response_shape(resp.status_code, bytes(raw), resp.headers)
        rec["response"] = shape
        if shape.get("schema_violations") and 200 <= resp.status_code < 300:
            raise SchemaViolation()  # never handed to the codec as if it were a supported response
        headers = [(k, v) for k, v in resp.headers.multi_items() if k.lower() not in ("content-encoding", "content-length")]
        return httpx.Response(resp.status_code, headers=headers, content=bytes(raw))

    def close(self) -> None:
        self.inner.close()


# ------------------------------------------------------------------ key handling (live only)


def read_key_file(path: str) -> SecretStr:
    """The only key source: an owner-only regular file outside the repository. Never the environment.
    The rules live in `tracewise.investigate.model_access` (shared with the benchmark's model mode)."""
    try:
        return model_access.read_key_file(path, repo_root=REPO_ROOT)
    except model_access.AccessRefused as e:
        raise Refused(str(e)) from None


# ------------------------------------------------------------------ the three steps (§2)


@dataclass
class Run:
    provider: HTTPProvider
    transport: GuardedTransport
    deadline: Deadline
    overall_at: float  # run start + TOTAL_DEADLINE_S; fixed for the whole run
    steps: list[dict[str, Any]] = field(default_factory=list)

    def step(self, name: str, messages: tuple[Message, ...], tools: bool) -> StepResponse:
        self.deadline.start_step(self.overall_at)  # raises DeadlineExceeded once the overall deadline has passed
        # As the investigator sends it: the same tools on every step; `tools=False` only clears `allow_tools`, which the
        # codec sends as `tool_choice: "none"` (multi-provider design step 2).
        req = StepRequest(messages, TOOL_SPECS, tools, MAX_OUTPUT_CHARS, self.deadline.remaining())
        rec: dict[str, Any] = {"step": name, "tools_offered": tools}
        self.steps.append(rec)
        resp = self.provider.step(req)
        rec.update(
            accepted=True,
            text_present=resp.text is not None,
            text_is_ok=(resp.text or "").strip() == "OK",
            tool_calls=len(resp.tool_calls),
            known_tools=all(tc.name in TOOL_NAMES for tc in resp.tool_calls),
            reasoning_items_kept_for_replay=len(resp.replay),
            usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
        )
        return resp


def run_steps(run: Run) -> str:
    system = Message("system", INSTRUCTIONS)
    run.step("text", (system, Message("user", TEXT_PROMPT)), tools=False)  # G-4: auth, serialisation, a valid response
    first = Message("user", TOOL_PROMPT)
    r2 = run.step("tool_call", (system, first), tools=True)
    if not r2.tool_calls:
        return "observation_missing"  # the contract held, but G-5/G-7/G-8 were not exercised
    assistant = Message("assistant", r2.text or "", tool_calls=r2.tool_calls, replay=r2.replay)
    results = tuple(Message("tool", TOOL_RESULT, tool_call_id=tc.id) for tc in r2.tool_calls)
    # G-7: the final step keeps the same `tools` with `tool_choice: "none"` while earlier calls stay in the input,
    # exactly as the investigator does.
    # The exact ids (G-5) and the reasoning items (R-10, G-8) are sent back unchanged.
    r3 = run.step("tool_result_without_tools", (system, first, assistant, *results, Message("user", FINAL_PROMPT)), tools=False)
    return "pass" if r3.text is not None else "observation_missing"


def classify(e: BaseException) -> str:
    if isinstance(e, Refused):
        return "refused"
    if isinstance(e, DeadlineExceeded):
        return "deadline"
    if isinstance(e, ResponseTooLarge | SchemaViolation):
        return "unsupported_response"
    if isinstance(e, ProviderTimeout):
        return "transport"
    if isinstance(e, ProviderQuotaError):
        return "quota"
    if isinstance(e, ProviderAuthError):
        return "auth"
    if isinstance(e, ProviderUnavailable):
        return "transport" if "transport error" in str(e) else "unavailable"
    if isinstance(e, ProviderRequestError):
        return "request_refused"
    if isinstance(e, ProviderError):
        return "unsupported_response"
    return "refused"


# ------------------------------------------------------------------ offline fixtures (deterministic)


def _resp(output: list[dict[str, Any]], status: str = "completed", **extra: Any) -> dict[str, Any]:
    return {
        "id": "resp_offline",
        "object": "response",
        "status": status,
        "error": None,
        "incomplete_details": None,
        "output": output,
        "usage": {"input_tokens": 50, "output_tokens": 5, "total_tokens": 55},
        **extra,
    }


def _text(t: str) -> dict[str, Any]:
    return {"type": "message", "id": "msg_o", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": t, "annotations": []}]}  # fmt: skip


OFFLINE_OPAQUE = "OFFLINE-OPAQUE-REASONING-PAYLOAD"
OFFLINE_CALL_ID = "call_offline_" + "q" * 80  # longer than 64 characters: G-5 must survive exactly
REASONING = {"type": "reasoning", "id": "rs_offline", "summary": [], "encrypted_content": OFFLINE_OPAQUE}
CALL = {"type": "function_call", "id": "fc_o", "call_id": OFFLINE_CALL_ID, "name": "list_dir", "arguments": '{"path": "docs"}'}
OK = _resp([_text("OK")])


def _json(doc: Any, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=doc, headers=headers)


SCENARIOS: dict[str, list[Any]] = {
    "pass": [OK, _resp([REASONING, CALL]), OK],
    "no_tool_call": [OK, OK],
    "missing_encrypted_content": [OK, _resp([{"type": "reasoning", "id": "rs", "summary": []}, CALL])],
    "incomplete": [_resp([_text("O")], status="incomplete", incomplete_details={"reason": "max_output_tokens"})],
    "refusal": [_resp([{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "no"}]}])],
    "unknown_item": [_resp([{"type": "web_search_call", "id": "ws"}])],
    "malformed_json": [httpx.Response(200, content=b"{not json")],
    "too_large": [httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))],
    "auth": [_json({"error": {"code": "invalid_api_key", "type": "invalid_request_error", "message": "m"}}, 401)],
    "quota": [_json({"error": {"code": "credit_balance_exhausted", "type": "insufficient_quota", "message": "m"}}, 429)],
    "rate_limited": [
        _json({"error": {"code": "rate_limit_exceeded", "type": "requests", "message": "m"}}, 429, {"retry-after": "1"})
    ],
    "server_error": [_json({"error": {"code": "server_is_overloaded", "message": "m"}}, 503)],
    "bad_request": [_json({"error": {"code": "invalid_value", "type": "invalid_request_error", "param": "input"}}, 400)],
    "transport_error": ["connect_error"],
    "final_step_rejects_without_tools": [OK, _resp([REASONING, CALL]), _json({"error": {"type": "invalid_request_error"}}, 400)],
}


class OfflineTransport(httpx.MockTransport):
    def __init__(self, scenario: str) -> None:
        self.script = list(SCENARIOS[scenario])
        self.bodies: list[bytes] = []

        def handler(req: httpx.Request) -> httpx.Response:
            self.bodies.append(req.read())
            item = self.script.pop(0)
            if item == "connect_error":
                raise httpx.ConnectError("offline: simulated connection failure", request=req)
            return item if isinstance(item, httpx.Response) else _json(item)

        super().__init__(handler)


# ------------------------------------------------------------------ entry point


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="openai_smoke", description=__doc__.split("\n\n")[0] if __doc__ else None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", choices=sorted(SCENARIOS), help="deterministic fixture; no network")
    mode.add_argument("--live", action="store_true", help="one real smoke evaluation (requires owner authorisation)")
    ap.add_argument("--model", required=True, help="explicit model identifier; there is no default and no fallback")
    ap.add_argument("--key-file", help="live only: owner-only file outside the repository holding the project key")
    ap.add_argument("--authorization-ref", help="live only: the owner's written authorisation reference")
    return ap.parse_args(argv)


def build(args: argparse.Namespace, env: dict[str, str], deadline: Deadline) -> tuple[HTTPProvider, GuardedTransport, str]:
    config = AdapterConfig(args.model, max_retries=0, max_response_bytes=MAX_RESPONSE_BYTES)  # validates the model id
    if args.live:
        if env.get("PYTEST_CURRENT_TEST") or env.get("CI"):
            raise Refused("live mode is never run by test runners or CI")
        if not args.key_file or not args.authorization_ref:
            raise Refused("live mode needs --key-file and --authorization-ref")
        try:
            model_access.check_authorization_ref(args.authorization_ref)
        except model_access.AccessRefused as e:
            raise Refused(str(e)) from None
        key = read_key_file(args.key_file)
        inner: httpx.BaseTransport = DeadlineHTTPTransport(deadline)
        mode = "live"
    else:
        if args.key_file or args.authorization_ref:
            raise Refused("offline mode takes no key file or authorization reference")
        key, inner, mode = SecretStr(OFFLINE_KEY), OfflineTransport(args.offline), f"offline:{args.offline}"
    guarded = GuardedTransport(inner, deadline)
    client = httpx.Client(transport=guarded, follow_redirects=False, trust_env=False)
    return HTTPProvider(OpenAIResponsesWire(), key, config, client=client, sleep=lambda _s: None), guarded, mode


def main(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    out: Any = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    out = out or sys.stdout
    args = parse(sys.argv[1:] if argv is None else argv)
    evidence: dict[str, Any] = {
        "harness": "openai_smoke",
        "version": 1,
        "endpoint": ENDPOINT,
        "model": args.model,
        "authorization_ref": args.authorization_ref,
        "limits": {
            "max_requests": MAX_REQUESTS,
            "max_retries": 0,
            "max_request_bytes": MAX_REQUEST_BYTES,
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "max_output_tokens": MAX_OUTPUT_CHARS,
            "step_timeout_s": STEP_TIMEOUT_S,
            "total_deadline_s": TOTAL_DEADLINE_S,
        },
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    secrets: list[str] = []
    transport: GuardedTransport | None = None
    deadline = Deadline(clock)
    result = "harness_error"
    failure: BaseException | None = None
    try:
        provider, transport, evidence["mode"] = build(args, dict(os.environ) if env is None else env, deadline)
    except (Refused, ValueError) as e:  # configuration: nothing was sent
        result, failure = "refused", e
    else:
        secrets.append(provider._key.get_secret_value())
        run = Run(provider, transport, deadline, clock() + TOTAL_DEADLINE_S)
        try:
            result = run_steps(run)
        except (Refused, DeadlineExceeded, ResponseTooLarge, SchemaViolation, ProviderError) as e:
            result, failure = classify(e), e
        except Exception as e:  # a harness defect: contained, classified, never a traceback or a pass
            result, failure = "harness_error", e
        finally:
            evidence["steps"] = run.steps
            provider.close()  # closes the transports, the connection pool and the deadline watchdog
        if failure is not None and deadline.expired:
            result = "deadline"  # whatever surfaced, the wall-clock deadline is what ended the exchange
    if failure is not None:
        evidence["failure"] = {
            "class": result,
            "error_type": type(failure).__name__,
            "detail": str(failure) if isinstance(failure, Refused) else None,  # fixed harness text only
        }
    evidence["exchanges"] = transport.records if transport else []
    evidence["requests_sent"] = transport.sent if transport else 0
    evidence["result"] = result
    evidence["exit"] = EXIT[result]
    text = json.dumps(evidence, indent=2, sort_keys=True)
    if any(s and s in text for s in secrets) or OFFLINE_OPAQUE in text:
        print('{"result": "refused", "detail": "evidence would contain a secret; nothing written"}', file=out)
        return EXIT["refused"]
    print(text, file=out)
    return EXIT[result]


if __name__ == "__main__":
    sys.exit(main())
