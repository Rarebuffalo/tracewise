"""Provider-neutral codec contract (multi-provider design §4 and §8). Every wire codec must satisfy the same
behaviour the investigator relies on, whatever its provider's wire format. A new codec (Anthropic, DeepSeek) joins
the parametrisation with its own response builders; the assertions do not change. Offline: no network, no keys."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tracewise.investigate.gemini_generate import GeminiGenerateContentWire
from tracewise.investigate.http_adapter import (
    CodecCapabilities,
    WireError,
    WireRefusal,
    WireTruncated,
    require_engine_support,
)
from tracewise.investigate.openai_responses import OpenAIResponsesWire
from tracewise.investigate.prompt import TOOL_SPECS
from tracewise.investigate.provider import (
    Message,
    ProviderError,
    ProviderRefusal,
    ProviderTruncated,
    StepRequest,
    StepResponse,
    StepUsage,
    ToolCallRequest,
)

TOOL_NAMES = [t.name for t in TOOL_SPECS]


@dataclass(frozen=True)
class Codec:
    """One codec under contract, with builders for the provider's own response documents."""

    name: str
    model: str
    make: Callable[[], Any]
    text: Callable[[str], dict[str, Any]]
    call: Callable[[str, str, dict[str, Any]], dict[str, Any]]
    truncated: Callable[[], dict[str, Any]]
    refused: Callable[[], dict[str, Any]]
    no_usage: Callable[[], dict[str, Any]]
    declared: Callable[[dict[str, Any]], list[str]]
    tool_mode: Callable[[dict[str, Any]], str]  # normalised: "auto" or "none"


def _oai(output: list[dict[str, Any]], status: str = "completed", usage: Any = ...) -> dict[str, Any]:
    doc: dict[str, Any] = {"id": "resp_1", "object": "response", "status": status, "output": output}
    if usage is not ...:
        doc["usage"] = usage
    else:
        doc["usage"] = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    return doc


def _oai_incomplete(reason: str) -> dict[str, Any]:
    return _oai([_oai_text("partial")], status="incomplete") | {"incomplete_details": {"reason": reason}}  # R-13


def _oai_text(text: str) -> dict[str, Any]:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


OPENAI = Codec(
    "openai-responses",
    "model-x",
    OpenAIResponsesWire,
    lambda t: _oai([_oai_text(t)]),
    lambda cid, n, a: _oai([{"type": "function_call", "call_id": cid, "name": n, "arguments": json.dumps(a)}]),
    lambda: _oai_incomplete("max_output_tokens"),
    lambda: _oai([{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "no"}]}]),
    lambda: _oai([_oai_text("x")], usage=None),
    lambda body: [t["name"] for t in body.get("tools", [])],
    lambda body: body["tool_choice"],
)


def _gem(parts: list[dict[str, Any]], finish: str = "STOP", usage: Any = ...) -> dict[str, Any]:
    doc: dict[str, Any] = {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}]}
    if usage is ...:
        doc["usageMetadata"] = {"promptTokenCount": 10, "candidatesTokenCount": 3}
    return doc


GEMINI = Codec(
    "gemini-generate-content",
    "gemini-test-1",
    lambda: GeminiGenerateContentWire("gemini-test-1"),
    lambda t: _gem([{"text": t}]),
    lambda cid, n, a: _gem([{"functionCall": {"id": cid, "name": n, "args": a}, "thoughtSignature": "SIG=="}]),
    lambda: _gem([{"text": "partial"}], finish="MAX_TOKENS"),
    lambda: _gem([{"text": "x"}], finish="SAFETY"),
    lambda: _gem([{"text": "x"}], usage=None),
    lambda body: [d["name"] for d in body.get("tools", [{}])[0].get("functionDeclarations", [])],
    lambda body: body["toolConfig"]["functionCallingConfig"]["mode"].lower(),
)

CODECS = [pytest.param(c, id=c.name) for c in (OPENAI, GEMINI)]


def _req(*msgs: Message, allow_tools: bool = True) -> StepRequest:
    # As the investigator sends it: the same tools on every step; a tool-free step only clears `allow_tools`.
    return StepRequest(tuple(msgs), TOOL_SPECS, allow_tools, 4000, 30.0)


def _one_tool_turn(c: Codec) -> tuple[Any, StepResponse, tuple[Message, ...]]:
    w = c.make()
    w.encode(c.model, _req(Message("system", "policy"), Message("user", "evidence")))
    r = w.decode(c.call("c1", "list_dir", {"path": "src"}))
    history = (
        Message("system", "policy"),
        Message("user", "evidence"),
        Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay),
        Message("tool", "RESULT-MARKER a.py", tool_call_id="c1"),
    )
    return w, r, history


@pytest.mark.parametrize("c", CODECS)
def test_tool_steps_declare_exactly_the_four_read_only_tools(c: Codec) -> None:
    body = c.make().encode(c.model, _req(Message("user", "evidence")))
    assert c.declared(body) == TOOL_NAMES and c.tool_mode(body) == "auto"


@pytest.mark.parametrize("c", CODECS)
def test_a_tool_free_step_keeps_the_same_declarations_and_selects_none(c: Codec) -> None:
    """Step 2: the declarations never change within a conversation; only the mode does."""
    w, _, history = _one_tool_turn(c)
    first = c.make().encode(c.model, _req(Message("user", "evidence")))
    final = w.encode(c.model, _req(*history, Message("user", "now answer"), allow_tools=False))
    assert c.declared(final) == c.declared(first) == TOOL_NAMES
    assert c.tool_mode(final) == "none"


@pytest.mark.parametrize("c", CODECS)
def test_text_decodes_to_an_answer_with_counted_usage(c: Codec) -> None:
    w = c.make()
    w.encode(c.model, _req(Message("user", "evidence")))
    r = w.decode(c.text("ANSWER"))
    assert r.text == "ANSWER" and r.tool_calls == ()
    assert r.usage.input_tokens > 0 and r.usage.output_tokens > 0


@pytest.mark.parametrize("c", CODECS)
def test_a_call_decodes_with_its_id_and_its_result_is_paired_on_the_next_step(c: Codec) -> None:
    w, r, history = _one_tool_turn(c)
    (tc,) = r.tool_calls
    assert (tc.id, tc.name) == ("c1", "list_dir")
    args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
    assert args == {"path": "src"}
    body = w.encode(c.model, _req(*history))
    assert json.dumps(body).count("RESULT-MARKER") == 1  # the result travels once, with the call it answers


@pytest.mark.parametrize("c", CODECS)
def test_a_call_without_a_result_cannot_be_sent(c: Codec) -> None:
    w, _, history = _one_tool_turn(c)
    with pytest.raises(WireError):
        w.encode(c.model, _req(*history[:-1], Message("user", "skip the result")))


@pytest.mark.parametrize("c", CODECS)
@pytest.mark.parametrize(("kind", "error"), [("truncated", WireTruncated), ("refused", WireRefusal), ("no_usage", WireError)])
def test_truncation_refusal_and_missing_usage_fail_closed_with_their_kind(c: Codec, kind: str, error: type) -> None:
    """A partial, refused or unmetered response is never taken for an answer; step 4 names which it was."""
    w = c.make()
    w.encode(c.model, _req(Message("user", "evidence")))
    with pytest.raises(error):
        w.decode(getattr(c, kind)())


@pytest.mark.parametrize(
    ("doc", "error"),
    [
        (_oai_incomplete("max_output_tokens"), WireTruncated),
        (_oai_incomplete("content_filter"), WireError),
    ],
    ids=["max-output-tokens", "other-incomplete-reason"],
)
def test_openai_reports_truncation_only_for_the_documented_reason(doc: dict[str, Any], error: type) -> None:
    with pytest.raises(error) as e:
        _decode(OPENAI, doc)
    assert type(e.value) is error  # an undocumented reason stays a generic contract failure (R-13)


@pytest.mark.parametrize(
    ("doc", "error"),
    [
        (_gem([{"text": "x"}], finish="MAX_TOKENS"), ProviderTruncated),
        (_gem([{"text": "x"}], finish="SAFETY"), ProviderRefusal),
        ({"promptFeedback": {"blockReason": "SAFETY"}}, ProviderRefusal),
        (_gem([{"text": "x"}], finish="OTHER"), ProviderError),
    ],
    ids=["max-tokens", "safety", "prompt-blocked", "other"],
)
def test_the_http_provider_surfaces_the_kind_without_quoting_the_document(doc: dict[str, Any], error: type) -> None:
    from tests.investigate.test_gemini_generate import Server, provider

    p, _ = provider(Server(doc))
    with pytest.raises(ProviderError) as e:
        p.step(_req(Message("user", "evidence")))
    assert type(e.value) is error and "SAFETY" not in str(e.value)


@pytest.mark.parametrize("c", CODECS)
@pytest.mark.parametrize("doc", [None, [], "text", {"unexpected": True}])
def test_unknown_shapes_fail_closed(c: Codec, doc: Any) -> None:
    w = c.make()
    w.encode(c.model, _req(Message("user", "evidence")))
    with pytest.raises(WireError):
        w.decode(doc)


# ------------------------------------------------------------------ usage breakdown (design step 3)


def _decode(c: Codec, doc: dict[str, Any]) -> StepResponse:
    w = c.make()
    w.encode(c.model, _req(Message("user", "evidence")))
    r: StepResponse = w.decode(doc)
    return r


def test_openai_usage_breakdown_is_mapped_from_the_recorded_detail_fields() -> None:
    usage = {
        "input_tokens": 100,
        "output_tokens": 40,
        "input_tokens_details": {"cached_tokens": 60},  # R-11
        "output_tokens_details": {"reasoning_tokens": 25},  # R-11
    }
    u = _decode(OPENAI, _oai([_oai_text("A")], usage=usage)).usage
    assert (u.input_tokens, u.output_tokens, u.cached_input_tokens, u.reasoning_output_tokens) == (100, 40, 60, 25)


def test_gemini_usage_breakdown_counts_thoughts_as_reasoning_and_cached_content_as_cached_input() -> None:
    doc = _gem([{"text": "A"}])
    doc["usageMetadata"] = {
        "promptTokenCount": 100,
        "cachedContentTokenCount": 60,  # N-23: part of the prompt count
        "toolUsePromptTokenCount": 5,
        "candidatesTokenCount": 15,
        "thoughtsTokenCount": 25,
    }
    u = _decode(GEMINI, doc).usage
    assert (u.input_tokens, u.output_tokens, u.cached_input_tokens, u.reasoning_output_tokens) == (105, 40, 60, 25)


def _oai_usage(**details: Any) -> dict[str, Any]:
    return _oai([_oai_text("A")], usage={"input_tokens": 10, "output_tokens": 3, **details})


def _gem_usage(**extra: Any) -> dict[str, Any]:
    return {**_gem([{"text": "A"}]), "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3, **extra}}


@pytest.mark.parametrize(
    ("c", "doc"),
    [
        (OPENAI, _oai_usage(input_tokens_details={"cached_tokens": 11})),
        (OPENAI, _oai_usage(output_tokens_details={"reasoning_tokens": -1})),
        (OPENAI, _oai_usage(output_tokens_details="x")),
        (GEMINI, _gem_usage(cachedContentTokenCount=11)),
        (GEMINI, _gem_usage(cachedContentTokenCount="5")),
    ],
    ids=["oai-cached-over-total", "oai-negative", "oai-not-object", "gem-cached-over-total", "gem-not-int"],
)
def test_an_impossible_usage_breakdown_fails_closed(c: Codec, doc: dict[str, Any]) -> None:
    with pytest.raises(WireError, match="usage"):
        _decode(c, doc)


@pytest.mark.parametrize(
    ("c", "doc", "want"),
    [
        (OPENAI, _oai_usage(), (None, None)),  # no detail objects: not reported
        (OPENAI, _oai_usage(input_tokens_details={}, output_tokens_details={}), (None, None)),  # objects without keys
        (OPENAI, _oai_usage(input_tokens_details={"cached_tokens": 0}, output_tokens_details={"reasoning_tokens": 0}), (0, 0)),
        (GEMINI, _gem_usage(), (None, None)),
        (GEMINI, _gem_usage(cachedContentTokenCount=0, thoughtsTokenCount=0), (0, 0)),
    ],
    ids=["oai-absent", "oai-empty", "oai-zero", "gem-absent", "gem-zero"],
)
def test_an_unreported_breakdown_is_unknown_never_zero(c: Codec, doc: dict[str, Any], want: tuple[Any, Any]) -> None:
    u = _decode(c, doc).usage
    assert (u.cached_input_tokens, u.reasoning_output_tokens) == want and (u.input_tokens, u.output_tokens) == (10, 3)


def test_the_investigation_breakdown_is_unknown_unless_every_step_reported_it() -> None:
    from tests.investigate.factory import B02_ANSWER
    from tests.investigate.test_loop import run

    t = StepResponse(tool_calls=(ToolCallRequest("c1", "get_diff", {}),), usage=StepUsage(50, 5, 10, None))
    a = StepResponse(text=json.dumps(B02_ANSWER), usage=StepUsage(100, 40, 60, 25))
    res, _, _ = run([t, a])  # type: ignore[no-untyped-call]
    assert (res.input_tokens, res.output_tokens, res.cached_input_tokens, res.reasoning_output_tokens) == (150, 45, 70, None)
    assert res.usage_source == "provider"


def test_the_investigation_totals_carry_the_breakdown() -> None:
    from tests.investigate.factory import B02_ANSWER
    from tests.investigate.test_loop import run  # the loop's scripted-provider harness

    a = StepResponse(text=json.dumps(B02_ANSWER), usage=StepUsage(100, 40, 60, 25))
    res, _, _ = run([a])  # type: ignore[no-untyped-call]
    assert (res.input_tokens, res.output_tokens, res.cached_input_tokens, res.reasoning_output_tokens) == (100, 40, 60, 25)


# ------------------------------------------------------------------ capability metadata (design step 4)


@pytest.mark.parametrize("c", CODECS)
def test_every_codec_declares_capabilities_the_engine_can_run(c: Codec) -> None:
    caps = c.make().capabilities
    assert caps.tool_choice_none and caps.replay_scope == "tool_turns" and caps.usage_breakdown
    require_engine_support(caps)  # accepted


@pytest.mark.parametrize(
    ("caps", "match"),
    [
        (CodecCapabilities(tool_choice_none=True, replay_scope="every_other_turn", usage_breakdown=True), "unknown replay"),  # type: ignore[arg-type]
        (CodecCapabilities(tool_choice_none=False, replay_scope="tool_turns", usage_breakdown=True), "forbid tool calls"),
    ],
    ids=["unknown-replay-scope", "no-none-mode"],
)
def test_a_codec_the_engine_cannot_run_is_refused_when_the_provider_is_built(caps: CodecCapabilities, match: str) -> None:
    """A codec the loop cannot run is refused at construction, before any request; it never fails mid-investigation.
    Replay on every assistant turn (Anthropic- or DeepSeek-shaped, records A-38 and D-27) is supported since O-5: see
    `test_every_turn_replay_scope_is_accepted_but_no_such_provider_can_be_selected`."""
    from pydantic import SecretStr

    from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider

    class NeedsMore(OpenAIResponsesWire):
        capabilities = caps

    with pytest.raises(ValueError, match=match):
        HTTPProvider(NeedsMore(), SecretStr("synthetic-key-0000"), AdapterConfig("model-x"))


def test_every_turn_replay_scope_is_accepted_but_no_such_provider_can_be_selected() -> None:
    from tracewise.investigate import providers

    require_engine_support(CodecCapabilities(tool_choice_none=True, replay_scope="all_turns", usage_breakdown=True))
    src = (Path(providers.__file__)).read_text()
    assert "anthropic" not in src.lower() and "deepseek" not in src.lower()  # no codec, no selection: still refused
