"""OpenAI Responses API wire codec (T-605 preparation, Phase 45D). Offline: no key used, no request ever made by tests.

Every mapping below cites the recorded official contract (research/openai-api-reference-2026-10-19/README.md, items
R-1..R-14). Choices that the documentation leaves to the integrator are marked DECISION. Gaps are listed in
docs/MODEL-ADAPTER.md and are NOT papered over here: an unknown response shape fails closed (WireError → the
investigator reports `provider_failed`, never a guessed diagnosis).

Selection: `investigate/providers.py` still refuses `LLM_PROVIDER=openai` (see MODEL-ADAPTER.md §2b for the gates).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from tracewise.investigate.http_adapter import WireError
from tracewise.investigate.provider import StepRequest, StepResponse, StepUsage, ToolCallRequest

ENDPOINT = "https://api.openai.com/v1/responses"  # R-1 (POST /v1/responses; host from the official example)
# R-12: these 429 `error.code` / `error.type` values mean quota, billing or spend exhaustion; retrying cannot help.
PERMANENT_429_CODES = frozenset(
    {
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)
PERMANENT_429_TYPES = frozenset({"insufficient_quota"})


class OpenAIResponsesWire:
    name: Literal["openai", "fake"] = "openai"
    endpoint = ENDPOINT

    def auth_headers(self, key: str) -> dict[str, str]:
        return {"authorization": f"Bearer {key}"}  # R-2

    # ------------------------------------------------------------------ request

    def encode(self, model: str, request: StepRequest) -> dict[str, Any]:
        instructions = "\n\n".join(m.content for m in request.messages if m.role == "system")  # R-3 `instructions`
        items: list[dict[str, Any]] = []
        issued: set[str] = set()  # every call_id sent so far: provider-issued ids must stay unique (R-6 pairing)
        awaiting: list[str] = []  # calls whose output has not been sent yet
        for m in request.messages:
            if m.role == "system":
                continue
            if m.role == "tool":  # R-6: function_call_output with the matching call_id; output is a string
                if m.tool_call_id not in awaiting:
                    raise WireError("tool result does not answer exactly one pending call")
                awaiting.remove(m.tool_call_id)
                items.append({"type": "function_call_output", "call_id": m.tool_call_id, "output": m.content})
                continue
            if awaiting:
                raise WireError("a call has no result before the next turn")
            if m.role == "assistant":
                for r in m.replay:  # R-10: provider-issued reasoning items, passed back verbatim (never redacted)
                    if not _is_reasoning_item(r):
                        raise WireError("the replay channel carries only reasoning items")
                    items.append(r)
                if m.content:
                    items.append({"type": "message", "role": "assistant", "content": m.content})  # R-4
                for tc in m.tool_calls:  # R-5: the model's own function_call items, arguments as a JSON string
                    # G-5: no documented length limit, so the provider-issued id is sent back exactly as received.
                    if not (isinstance(tc.id, str) and tc.id) or tc.id in issued:
                        raise WireError("call ids must be present and unique")
                    issued.add(tc.id)
                    awaiting.append(tc.id)
                    args = tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments)
                    items.append({"type": "function_call", "call_id": tc.id, "name": tc.name, "arguments": args})
                continue
            items.append({"type": "message", "role": "user", "content": m.content})  # R-4
        if awaiting:
            raise WireError("a call has no result")
        body: dict[str, Any] = {
            "model": model,  # R-3
            "input": items,  # R-4
            "store": False,  # R-3: default true; DECISION: false (data minimisation; stateless replay, R-10)
            "max_output_tokens": request.max_output_chars,  # R-3; DECISION: char cap as an upper bound, see §2b
        }
        if instructions:
            body["instructions"] = instructions
        if request.allow_tools and request.tools:
            body["tools"] = [
                {
                    "type": "function",  # R-7
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    # R-7/R-8: strict requires every property to be required; our specs have optional fields.
                    "strict": False,
                }
                for t in request.tools
            ]
            body["tool_choice"] = "auto"  # R-9
        return body

    # ------------------------------------------------------------------ response

    def decode(self, doc: Any) -> StepResponse:
        if not isinstance(doc, dict) or doc.get("object") != "response":  # R-11
            raise WireError("not a response object")
        status = doc.get("status")
        if status != "completed":  # R-11 statuses; R-13 incomplete (e.g. max_output_tokens): fail closed
            raise WireError("response status is not completed")  # never quote the document (WireError contract)
        output = doc.get("output")
        if not isinstance(output, list):
            raise WireError("output is not a list")
        texts: list[str] = []
        calls: list[ToolCallRequest] = []
        replay: list[dict[str, Any]] = []
        for item in output:
            kind = item.get("type") if isinstance(item, dict) else None
            if kind == "message":  # R-11: content parts output_text / refusal
                for part in item.get("content") or []:
                    ptype = part.get("type") if isinstance(part, dict) else None
                    if ptype == "output_text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                    elif ptype == "refusal":
                        raise WireError("the model refused")  # DECISION: a refusal is never a diagnosis
                    else:
                        raise WireError("unknown message content part")
            elif kind == "function_call":  # R-5
                cid, name, args = item.get("call_id"), item.get("name"), item.get("arguments")
                if not (isinstance(cid, str) and cid and isinstance(name, str) and isinstance(args, str)):
                    raise WireError("malformed function_call")
                if any(c.id == cid for c in calls):
                    raise WireError("duplicate call_id in one response")  # results could not be paired unambiguously
                calls.append(ToolCallRequest(cid, name, args))  # untrusted; the investigator validates and parses
            elif kind == "reasoning":  # R-10: opaque; returned to the provider on the next turn
                if not _is_reasoning_item(item):
                    raise WireError("reasoning item without its opaque payload")  # store=false: R-10 says it is present
                replay.append(item)
            else:
                raise WireError("unexpected output item type")  # no other tools are enabled
        usage = doc.get("usage")
        if not isinstance(usage, dict) or not all(isinstance(usage.get(k), int) for k in ("input_tokens", "output_tokens")):
            raise WireError("usage missing")  # R-11; never invented
        return StepResponse(
            "".join(texts) if texts else None,
            tuple(calls),
            StepUsage(usage["input_tokens"], usage["output_tokens"]),
            tuple(replay) if calls else (),  # R-10: needed only alongside function calls
        )

    # ------------------------------------------------------------------ errors

    def is_permanent(self, status: int, doc: Any) -> bool:
        """R-12: quota, billing and spend 429s are not retried. Rate-limit 429 and 5xx stay retryable (R-14)."""
        if status != 429 or not isinstance(doc, dict) or not isinstance(doc.get("error"), dict):
            return False
        err = doc["error"]
        return err.get("code") in PERMANENT_429_CODES or err.get("type") in PERMANENT_429_TYPES


def _is_reasoning_item(item: Any) -> bool:
    """R-10: a provider-issued reasoning item. With `store: false` it carries `encrypted_content` (opaque; never
    decoded, rebuilt or redacted here). Only such items may travel in the unredacted replay channel."""
    return (
        isinstance(item, dict)
        and item.get("type") == "reasoning"
        and isinstance(item.get("id"), str)
        and bool(item["id"])
        and isinstance(item.get("encrypted_content"), str)
        and bool(item["encrypted_content"])
    )
