"""Gemini native `generateContent` wire codec (offline only; never selected by the product).

Written against the recorded contract (research/gemini-api-reference-2026-10-26/README.md, record facts R-n and
Addendum A facts N-n). Choices the documentation leaves open are marked DECISION; the gaps it leaves are NG-n and fail
closed here: an unknown or unsupported shape raises `WireError`, which the investigator reports as `provider_failed`,
never as a diagnosis.

Selection: `investigate/providers.py` does not know this codec. Only the owner-run benchmark model mode
(`python -m tracewise.bench run --kind model --api gemini-generate-content`) constructs it.

**Replay (opaque model turns).** Thought signatures "can be attached to any part" (N-15) and must be resent "exactly as
they were received" (N-16); where they must appear is not documented (NG-2). The only faithful approach is to send
the model's own returned `Content` back unchanged. That content travels in `Message.replay`, which skips P-2
redaction, so it is admitted only as a `SignedTurn`:
* created by `decode` of **this codec instance**, for **this model**, and authenticated with an HMAC key that never
  leaves the instance (a forged, modified, or other-instance/other-model envelope is refused);
* bound to its exchange: the MAC covers a digest of the exact request (system instruction and contents) that
  produced it, and it is accepted only directly after that same history, so it cannot be repeated later in the
  same conversation;
* bound to its conversation: every request that carries no signed turn starts a new conversation with a fresh random
  epoch (only a conversation's first steps lack one, because history only grows), and a turn is accepted only in the
  epoch that minted it, so a stale turn is refused even when an identical history is reconstructed (for example the
  same benchmark case run again);
* one decode per encode: decoding consumes the request binding, so a second response for the same request can never
  be replayed. The codec handles one exchange at a time (`HTTPProvider.step` encodes once, then decodes that request's
  response); it is not for concurrent use;
* attached to an assistant turn whose `tool_calls` (already validated by the investigator) match the envelope's
  function calls exactly: same ids, names and arguments, in the same order (else refused);
* never shown: `repr` and `str` are masked, and the envelope refuses JSON serialisation, pickling and copying.
Tool execution never reads the envelope: the investigator executes only its own validated `tool_calls`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Literal

from tracewise.investigate.http_adapter import CodecCapabilities, WireError, WireRefusal, WireTruncated
from tracewise.investigate.provider import StepRequest, StepResponse, StepUsage, ToolCallRequest, ToolSpec
from tracewise.prepass.sanitize import redact

HOST = "https://generativelanguage.googleapis.com"  # N-1
# DECISION: model ids are lowercase dotted/dashed names (as listed on S-9); anything else, including '/', ':' or '?',
# could change the request path and is refused.
_MODEL = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
_ALLOWED_PART_KEYS = frozenset({"text", "thought", "thoughtSignature", "functionCall"})
ACCEPTED_FINISH = "STOP"  # N-13: the only accepted finish reason; every other value fails closed
# N-13 content-blocking reasons (text output). Reported as a refusal; MAX_TOKENS as truncation; the rest stay generic.
_BLOCKED_FINISH = frozenset({"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"})


class SignedTurn:
    """An opaque, authenticated copy of one model `Content` returned by `decode`. Never displayed."""

    __slots__ = ("_content", "_epoch", "_mac", "_model", "_prefix")

    def __init__(self, content: dict[str, Any], model: str, epoch: bytes, prefix: bytes | None, mac: bytes) -> None:
        self._content, self._model, self._epoch, self._prefix, self._mac = content, model, epoch, prefix, mac

    def __repr__(self) -> str:
        return "SignedTurn(<gemini model turn hidden>)"

    __str__ = __repr__

    def __reduce_ex__(self, protocol: object) -> Any:  # pickle, copy and deepcopy all go through here
        raise TypeError("SignedTurn cannot be serialised or copied")

    def __replay_bytes__(self) -> bytes:
        """Exact identity for the shared replay ledger (size cap and integrity, O-5); never logged or shown."""
        return json.dumps(
            [self._model, self._content, self._epoch.hex(), self._prefix.hex() if self._prefix else None, self._mac.hex()],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()


class GeminiGenerateContentWire:
    name: Literal["openai", "gemini", "fake"] = "gemini"
    # N-8 NONE; N-15 signatures on the model turns this codec replays (text-part signatures, NG-2, are unrecorded);
    # N-23 cached and thoughts counts; whether maxOutputTokens includes thinking is undocumented (NG-1).
    capabilities = CodecCapabilities(tool_choice_none=True, replay_scope="tool_turns", usage_breakdown=True)

    def __init__(self, model: str) -> None:
        if not isinstance(model, str) or len(model) > 64 or not _MODEL.match(model):
            raise ValueError("Gemini model id is missing or malformed")
        self.model = model
        self.endpoint = f"{HOST}/v1beta/models/{model}:generateContent"  # N-1; the host lock compares the whole URL
        self._key = secrets.token_bytes(32)  # per instance; authenticates replay envelopes, never leaves the codec
        self._declared: dict[str, dict[str, Any]] = {}  # declarations sent earlier, reused for the tool-free final step
        self._last_request: bytes | None = None  # digest of the request just encoded; binds the turn decoded for it
        self._epoch = secrets.token_bytes(16)  # the current conversation; renewed by every request without a signed turn

    def auth_headers(self, key: str) -> dict[str, str]:
        return {"x-goog-api-key": key}  # N-2: never in the URL or body

    # ------------------------------------------------------------------ replay authentication

    @staticmethod
    def _request_digest(system: list[str], contents: list[dict[str, Any]]) -> bytes:
        return hashlib.sha256(json.dumps([system, contents], sort_keys=True, separators=(",", ":")).encode()).digest()

    def _mac(self, content: dict[str, Any], epoch: bytes, prefix: bytes | None) -> bytes:
        canonical = json.dumps(
            [self.model, epoch.hex(), prefix.hex() if prefix else None, content], sort_keys=True, separators=(",", ":")
        ).encode()
        return hmac.new(self._key, canonical, hashlib.sha256).digest()

    def _verified(self, turn: Any, prefix: bytes) -> dict[str, Any]:
        if not isinstance(turn, SignedTurn):
            raise WireError("replay item was not produced by this codec")
        mac = self._mac(turn._content, turn._epoch, turn._prefix)
        if turn._model != self.model or not hmac.compare_digest(turn._mac, mac):
            raise WireError("replay item failed provenance check")  # forged, modified, or another instance/model
        if not hmac.compare_digest(turn._epoch, self._epoch):
            raise WireError("replay item does not belong to this conversation")  # stale: an earlier conversation
        if turn._prefix is None or not hmac.compare_digest(turn._prefix, prefix):
            raise WireError("replay item does not belong to this conversation")  # reused in another exchange
        return turn._content

    # ------------------------------------------------------------------ request

    def encode(self, model: str, request: StepRequest) -> dict[str, Any]:
        # State changes only when the whole request encodes: a failed encode never moves the conversation epoch, the
        # decode binding or the declaration cache (review D4, D5); any earlier unconsumed binding is dropped first.
        self._last_request = None
        if model != self.model:
            raise WireError("request model differs from the codec's model")
        new_conversation = not any(m.role == "assistant" and m.tool_calls for m in request.messages)
        system: list[str] = []
        contents: list[dict[str, Any]] = []
        pending: dict[str, str] = {}  # call id -> name, awaiting a result
        results: list[dict[str, Any]] = []
        called: set[str] = set()
        for m in request.messages:
            if m.role == "tool":
                if m.tool_call_id not in pending:
                    raise WireError("tool result does not answer exactly one pending call")
                name = pending.pop(m.tool_call_id)
                # DECISION: the result text is wrapped as {"output": text}; `response` must be a JSON object (N-7).
                results.append({"functionResponse": {"id": m.tool_call_id, "name": name, "response": {"output": m.content}}})
                continue
            if pending:
                raise WireError("a call has no result before the next turn")
            if results:
                # DECISION (NG-3): function responses are sent as a 'user' Content, the only non-model role allowed (N-5).
                contents.append({"role": "user", "parts": results})
                results = []
            if m.role == "system":
                system.append(m.content)
            elif m.role == "user":
                contents.append({"role": "user", "parts": [{"text": m.content}]})
            elif m.role == "assistant":
                if m.tool_calls:
                    content = self._replayed_turn(m.replay, m.tool_calls, self._request_digest(system, contents))
                    for tc in m.tool_calls:
                        pending[tc.id] = tc.name
                        called.add(tc.name)
                    contents.append(content)
                else:
                    if m.replay:
                        raise WireError("replay is only accepted on a turn with tool calls")
                    if m.content:
                        contents.append({"role": "model", "parts": [{"text": m.content}]})
            else:
                raise WireError("unsupported message role")
        if pending:
            raise WireError("a call has no result")
        if results:
            contents.append({"role": "user", "parts": results})
        if not contents:
            raise WireError("no content to send")
        body: dict[str, Any] = {
            "contents": contents,
            # DECISION (NG-1): both fields appear in the reference's samples; their semantics (including whether thinking
            # tokens count) are not documented, so this is an upper bound requested from the provider, not a guarantee.
            "generationConfig": {"maxOutputTokens": request.max_output_chars, "candidateCount": 1},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
        declared = dict(self._declared)
        if request.tools:
            # The investigator sends the same tools on every step; a tool-free step keeps them and forbids calls (N-8
            # NONE) instead of omitting them, which can end in UNEXPECTED_TOOL_CALL (N-13).
            decls = [_declaration(t) for t in request.tools]
            declared.update((d["name"], d) for d in decls)
            body["tools"] = [{"functionDeclarations": decls}]
            mode = "AUTO" if request.allow_tools else "NONE"
            body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}  # N-8
        else:
            # The tool-free final step: keep the declarations the history refers to and forbid new calls (N-8 NONE),
            # rather than omitting tools, which can end in UNEXPECTED_TOOL_CALL (N-13). A call to a name that was never
            # declared was refused by the investigator ("REJECTED"); no declaration is invented for it (review D3).
            known = [declared[n] for n in sorted(called) if n in declared]
            if known:
                body["tools"] = [{"functionDeclarations": known}]
                body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        # Commit: this request is now the one a decode may bind to.
        self._declared = declared
        if new_conversation:
            self._epoch = secrets.token_bytes(16)  # a new conversation: every earlier turn becomes stale
        self._last_request = self._request_digest(system, contents)
        return body

    def _replayed_turn(self, replay: tuple[Any, ...], tool_calls: tuple[ToolCallRequest, ...], prefix: bytes) -> dict[str, Any]:
        if len(replay) != 1:
            raise WireError("a tool-call turn needs exactly one replay item")
        content = self._verified(replay[0], prefix)
        calls = [p["functionCall"] for p in content["parts"] if isinstance(p, dict) and "functionCall" in p]
        if len(calls) != len(tool_calls):
            raise WireError("replayed calls differ from the validated tool calls")
        for fc, tc in zip(calls, tool_calls, strict=True):
            if fc.get("id") != tc.id or fc.get("name") != tc.name or not _same_args(fc.get("args", {}), tc.arguments):
                raise WireError("replayed calls differ from the validated tool calls")
        return content  # verbatim: thought signatures stay exactly where the model put them

    # ------------------------------------------------------------------ response

    def decode(self, doc: Any) -> StepResponse:
        # One decode per encode: the binding is consumed here, before any check, so a later or second response for
        # the same request can never yield a replayable turn (None: decoded without a request).
        prefix, self._last_request = self._last_request, None
        if not isinstance(doc, dict):
            raise WireError("response is not an object")
        feedback = doc.get("promptFeedback")
        if feedback is not None and (not isinstance(feedback, dict) or feedback.get("blockReason") is not None):
            raise WireRefusal("the prompt was blocked")  # N-14; never quote the reason or ratings
        candidates = doc.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise WireError("expected exactly one candidate")
        cand = candidates[0]
        if not isinstance(cand, dict):
            raise WireError("candidate is not an object")
        finish = cand.get("finishReason")
        if finish == "MAX_TOKENS":
            raise WireTruncated("finish reason is MAX_TOKENS")  # N-13
        if finish in _BLOCKED_FINISH:
            raise WireRefusal("finish reason reports a blocked response")  # N-13; never quote the reason or ratings
        if finish != ACCEPTED_FINISH:
            raise WireError("finish reason is not STOP")  # missing, blocked, truncated, malformed call, continuation, unknown
        content = cand.get("content")
        if not isinstance(content, dict) or content.get("role") != "model":  # replayed verbatim: never patched (D6)
            raise WireError("candidate content is missing or not from the model")
        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise WireError("candidate content has no parts")
        texts: list[str] = []
        calls: list[ToolCallRequest] = []
        for part in parts:
            if not isinstance(part, dict) or not part or set(part) - _ALLOWED_PART_KEYS:
                raise WireError("unsupported part")  # inline data, code execution, files, ... are not used here
            sig = part.get("thoughtSignature")
            if sig is not None and not (isinstance(sig, str) and sig):
                raise WireError("malformed thought signature")
            thought = part.get("thought", False)
            if not isinstance(thought, bool):
                raise WireError("malformed thought flag")
            if "functionCall" in part:
                if "text" in part or thought:
                    raise WireError("unsupported part")
                calls.append(_call(part["functionCall"], calls))
            elif "text" in part:
                if not isinstance(part["text"], str):
                    raise WireError("text part is not a string")
                if not thought:
                    texts.append(part["text"])  # thought summaries are never answer text
            elif sig is None:
                raise WireError("empty part")  # a signature-only part is kept for replay; anything else is unknown
        usage = doc.get("usageMetadata")
        if not isinstance(usage, dict) or not all(_count(usage.get(k)) for k in ("promptTokenCount", "candidatesTokenCount")):
            raise WireError("usage missing")  # never invented
        thoughts = usage.get("thoughtsTokenCount")  # absent: not reported (None), added to the total as 0
        tool_use = usage.get("toolUsePromptTokenCount", 0)
        cached = usage.get("cachedContentTokenCount")  # N-23: part of the prompt count; absent: not reported
        if not all(_count(v) for v in (thoughts, tool_use, cached) if v is not None):
            raise WireError("usage malformed")
        if cached is not None and cached > usage["promptTokenCount"]:
            raise WireError("usage malformed")
        # Input: prompt plus tool-use prompt (separate terms of the documented total, N-23/N-30). Output: candidates plus
        # thoughts (response pricing is output plus thinking tokens, N-24). Cached tokens are part of the prompt count.
        out = StepUsage(usage["promptTokenCount"] + tool_use, usage["candidatesTokenCount"] + (thoughts or 0), cached, thoughts)
        replay: tuple[Any, ...] = ()
        if calls:
            replay = (SignedTurn(content, self.model, self._epoch, prefix, self._mac(content, self._epoch, prefix)),)
        return StepResponse("".join(texts) if texts else None, tuple(calls), out, replay)

    def is_permanent(self, status: int, doc: Any) -> bool:
        """NG-5: the `generateContent` error body is not documented, so no 429 is classified as permanent here; the
        benchmark and smoke paths use zero retries regardless."""
        return False


def _declaration(t: ToolSpec) -> dict[str, Any]:
    # The tool specs are JSON Schema (`additionalProperties`, lower-case types). `parameters` takes the OpenAPI Schema
    # subset, which has neither; `parametersJsonSchema` takes JSON Schema and is mutually exclusive with it (Addendum C).
    return {"name": t.name, "description": t.description, "parametersJsonSchema": t.parameters}


def _same_args(signed: Any, arguments: Any) -> bool:
    """The signed `args` equal the validated call's arguments, as decoded (`json.dumps(args, sort_keys=True)`), or as
    the investigator hands them over after its redaction of the provider view (`provider_view`): the same
    deterministic `redact` applied to the same string. Anything else is a mismatch."""
    if isinstance(arguments, str):
        canonical = json.dumps(signed, sort_keys=True)
        return arguments in (canonical, redact(canonical))
    return isinstance(arguments, dict) and signed == arguments


def _call(fc: Any, seen: list[ToolCallRequest]) -> ToolCallRequest:
    if not isinstance(fc, dict) or set(fc) - {"id", "name", "args"}:
        raise WireError("malformed function call")
    cid, name, args = fc.get("id"), fc.get("name"), fc.get("args", {})
    # NG-4: the id is optional in the contract, but results are paired only by id; a missing id is never invented.
    if not (isinstance(cid, str) and cid):
        raise WireError("function call has no id")
    if not (isinstance(name, str) and name) or not isinstance(args, dict):
        raise WireError("malformed function call")
    if any(c.id == cid for c in seen):
        raise WireError("duplicate function call id")
    return ToolCallRequest(cid, name, json.dumps(args, sort_keys=True))  # untrusted; the investigator validates it


def _count(v: Any) -> bool:
    return type(v) is int and v >= 0
