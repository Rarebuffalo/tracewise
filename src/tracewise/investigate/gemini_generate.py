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

from tracewise.investigate.http_adapter import WireError
from tracewise.investigate.provider import StepRequest, StepResponse, StepUsage, ToolCallRequest, ToolSpec

HOST = "https://generativelanguage.googleapis.com"  # N-1
# DECISION: model ids are lowercase dotted/dashed names (as listed on S-9); anything else, including '/', ':' or '?',
# could change the request path and is refused.
_MODEL = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
_ALLOWED_PART_KEYS = frozenset({"text", "thought", "thoughtSignature", "functionCall"})
ACCEPTED_FINISH = "STOP"  # N-13: the only accepted finish reason; every other value fails closed


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


class GeminiGenerateContentWire:
    name: Literal["openai", "gemini", "fake"] = "gemini"

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
        if model != self.model:
            raise WireError("request model differs from the codec's model")
        if not any(m.role == "assistant" and m.tool_calls for m in request.messages):
            self._epoch = secrets.token_bytes(16)  # a new conversation: every earlier turn becomes stale
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
        self._last_request = self._request_digest(system, contents)
        if request.allow_tools and request.tools:
            decls = [_declaration(t) for t in request.tools]
            for d in decls:
                self._declared[d["name"]] = d
            body["tools"] = [{"functionDeclarations": decls}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}  # N-8
        elif called:
            # The tool-free final step: keep the declarations the history refers to and forbid new calls (N-8 NONE),
            # rather than omitting tools, which can end in UNEXPECTED_TOOL_CALL (N-13).
            missing = sorted(called - set(self._declared))
            if missing:
                raise WireError("history refers to a tool this codec never declared")
            body["tools"] = [{"functionDeclarations": [self._declared[n] for n in sorted(called)]}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        return body

    def _replayed_turn(self, replay: tuple[Any, ...], tool_calls: tuple[ToolCallRequest, ...], prefix: bytes) -> dict[str, Any]:
        if len(replay) != 1:
            raise WireError("a tool-call turn needs exactly one replay item")
        content = self._verified(replay[0], prefix)
        calls = [p["functionCall"] for p in content["parts"] if isinstance(p, dict) and "functionCall" in p]
        if len(calls) != len(tool_calls):
            raise WireError("replayed calls differ from the validated tool calls")
        for fc, tc in zip(calls, tool_calls, strict=True):
            try:
                args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
            except ValueError:
                raise WireError("tool-call arguments are not JSON") from None
            if fc.get("id") != tc.id or fc.get("name") != tc.name or fc.get("args", {}) != args:
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
            raise WireError("the prompt was blocked")  # N-14; never quote the reason or ratings
        candidates = doc.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise WireError("expected exactly one candidate")
        cand = candidates[0]
        if not isinstance(cand, dict):
            raise WireError("candidate is not an object")
        if cand.get("finishReason") != ACCEPTED_FINISH:
            raise WireError("finish reason is not STOP")  # missing, blocked, truncated, malformed call, continuation, unknown
        content = cand.get("content")
        if not isinstance(content, dict) or content.get("role", "model") != "model":
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
        thoughts = usage.get("thoughtsTokenCount", 0)
        if not _count(thoughts):
            raise WireError("usage malformed")
        # Billed as output: response pricing is output plus thinking tokens (N-24).
        out = StepUsage(usage["promptTokenCount"], usage["candidatesTokenCount"] + thoughts)
        replay: tuple[Any, ...] = ()
        if calls:
            replay = (SignedTurn(content, self.model, self._epoch, prefix, self._mac(content, self._epoch, prefix)),)
        return StepResponse("".join(texts) if texts else None, tuple(calls), out, replay)

    def is_permanent(self, status: int, doc: Any) -> bool:
        """NG-5: the `generateContent` error body is not documented, so no 429 is classified as permanent here; the
        benchmark and smoke paths use zero retries regardless."""
        return False


def _declaration(t: ToolSpec) -> dict[str, Any]:
    return {"name": t.name, "description": t.description, "parameters": t.parameters}


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
