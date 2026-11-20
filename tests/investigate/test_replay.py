"""O-5: provider continuation state is bound to its investigation, size-limited, verified before it is sent back,
replayed on the turns the provider's protocol names (tool turns, or every assistant turn), and never shown. Offline:
scripted providers only."""

from __future__ import annotations

import copy
import json
import logging
import pickle
from typing import Any

import pytest

from tests.investigate.factory import B02_ANSWER, answer, evidence, tool
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.fake import ScriptedProvider
from tracewise.investigate.loop import InvestigationLimits, investigate
from tracewise.investigate.provider import Message, StepRequest, StepResponse, StepUsage
from tracewise.investigate.replay import (
    MAX_CONVERSATION_BYTES,
    MAX_ENVELOPE_BYTES,
    ReplayContext,
    ReplayError,
    ReplayLedger,
)
from tracewise.report.render import render

CANARY = "REASONING-CANARY-7f3a"


def item(payload: str = CANARY, n: int = 0) -> dict[str, Any]:
    return {"type": "reasoning", "id": f"rs_{n}", "encrypted_content": payload}


def with_state(resp: StepResponse, *items: dict[str, Any]) -> StepResponse:
    return StepResponse(resp.text, resp.tool_calls, resp.usage, tuple(items))


def ctx(**kw: Any) -> ReplayContext:
    base: dict[str, Any] = {"provider": "fake", "model": "fake-scripted-1", "installation_id": 9, "job_id": 1, "attempt": 1}
    return ReplayContext(**{**base, **kw})


# ------------------------------------------------------------------ binding and integrity


def test_state_opens_only_in_the_context_that_sealed_it() -> None:
    c = ctx()
    led = ReplayLedger(c)
    env = led.seal([item()])
    assert led.open([env]) == (item(),)


@pytest.mark.parametrize(
    "other",
    [
        {"investigation": "another-investigation"},
        {"attempt": 2},
        {"job_id": 2},
        {"installation_id": 10},
        {"provider": "openai"},
        {"model": "fake-scripted-2"},
    ],
    ids=["investigation", "attempt", "job", "tenant", "provider", "model"],
)
def test_state_from_another_context_is_refused(other: dict[str, Any]) -> None:
    c = ctx(investigation="i-1")
    env = ReplayLedger(c).seal([item()])
    foreign = ReplayLedger(ctx(**{"investigation": "i-1", **other}))
    with pytest.raises(ReplayError) as info:
        foreign.open([env])
    assert info.value.reason == "context_mismatch" and CANARY not in str(info.value)


def test_state_not_issued_by_this_ledger_is_refused_even_in_the_same_context() -> None:
    c = ctx(investigation="same")
    env = ReplayLedger(c).seal([item()])
    with pytest.raises(ReplayError, match="unknown_envelope"):
        ReplayLedger(c).open([env])


def test_raw_or_missing_state_is_refused() -> None:
    led = ReplayLedger(ctx())
    with pytest.raises(ReplayError, match="not_sealed"):
        led.open([item()])  # raw provider items never travel in the history unsealed
    with pytest.raises(ReplayError, match="missing"):
        led.seal([])


@pytest.mark.parametrize("bad", [b"bytes", "text", ["list"], {"x": float("nan")}, {"x": object()}])
def test_malformed_state_is_refused(bad: Any) -> None:
    with pytest.raises(ReplayError, match="malformed"):
        ReplayLedger(ctx()).seal([bad])


def test_state_changed_after_sealing_is_never_sent_back() -> None:
    led = ReplayLedger(ctx())
    original = item()
    env = led.seal([original])
    original["encrypted_content"] = "tampered"
    with pytest.raises(ReplayError, match="modified"):
        led.open([env])


def test_an_oversized_envelope_is_refused_never_truncated() -> None:
    led = ReplayLedger(ctx())
    with pytest.raises(ReplayError, match="envelope_too_large"):
        led.seal([item("x" * MAX_ENVELOPE_BYTES)])
    assert led.total == 0


def test_the_conversation_total_is_capped() -> None:
    led = ReplayLedger(ctx())
    chunk = "x" * (MAX_ENVELOPE_BYTES - 200)
    for n in range(MAX_CONVERSATION_BYTES // MAX_ENVELOPE_BYTES):
        led.seal([item(chunk, n)])
    with pytest.raises(ReplayError, match="conversation_too_large"):
        led.seal([item(chunk, 99)])


def test_envelopes_are_masked_and_cannot_be_copied_or_serialised() -> None:
    env = ReplayLedger(ctx()).seal([item()])
    assert CANARY not in repr(env) and CANARY not in str(env)
    for op in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError):
            op(env)
    with pytest.raises(TypeError):
        json.dumps(env)
    m = Message("assistant", "", replay=(item(),))
    assert CANARY not in repr(m) and CANARY not in repr(StepResponse(replay=(item(),)))
    assert CANARY not in repr(StepRequest((m,), (), True, 10, 1.0))


# ------------------------------------------------------------------ in the investigation loop


def test_tool_turn_state_goes_back_verbatim_on_the_next_request() -> None:
    p = ScriptedProvider([with_state(tool("get_diff"), item()), answer(**B02_ANSWER)])
    res = investigate(evidence(), p)
    assert res.outcome == "answered"
    (turn,) = [m for m in p.requests[1].messages if m.role == "assistant"]
    assert turn.replay == (item(),)  # the codec receives the verified raw items


class EveryTurn(ScriptedProvider):
    replay_scope = "all_turns"


class NoState(ScriptedProvider):
    replay_scope = "none"


def test_every_turn_providers_get_their_state_and_exact_text_back_on_the_repair_turn() -> None:
    bad = "{not json " + "y" * 3000  # longer than the 2,000 characters a tool-turn provider's repair copy keeps
    p = EveryTurn(
        [with_state(tool("get_diff"), item(n=1)), with_state(StepResponse(text=bad, usage=StepUsage(1, 1)), item(n=2)),
         answer(**B02_ANSWER)]
    )  # fmt: skip
    res = investigate(evidence(), p)
    assert res.outcome == "answered"
    turns = [m for m in p.requests[2].messages if m.role == "assistant"]
    assert [t.replay for t in turns] == [(item(n=1),), (item(n=2),)]
    assert turns[1].content == bad  # unaltered: the provider checks earlier turns exactly


def test_tool_turn_providers_keep_todays_repair_turn() -> None:
    bad = "{not json " + "y" * 3000
    p = ScriptedProvider([StepResponse(text=bad, usage=StepUsage(1, 1)), answer(**B02_ANSWER)])
    investigate(evidence(), p)
    (turn,) = [m for m in p.requests[1].messages if m.role == "assistant"]
    assert turn.replay == () and len(turn.content) == 2000


@pytest.mark.parametrize(
    ("provider", "script"),
    [
        (ScriptedProvider, [with_state(tool("get_diff"), item("x" * MAX_ENVELOPE_BYTES)), answer(**B02_ANSWER)]),
        (ScriptedProvider, [with_state(tool("get_diff"), {"bad": float("nan")}), answer(**B02_ANSWER)]),  # type: ignore[arg-type]
        (NoState, [with_state(tool("get_diff"), item()), answer(**B02_ANSWER)]),
    ],
    ids=["oversized", "malformed", "undeclared"],
)
def test_refused_state_ends_the_investigation_inconclusive_without_leaking_it(provider: Any, script: Any, caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    p = provider(script)
    vd = diagnose(evidence(), p)
    d = vd.diagnosis
    assert d.status.value == "inconclusive" and d.inconclusive_reason == "provider_failed"
    assert len(p.requests) == 1  # the conversation never continued with state it could not keep
    events = [r.tw for r in caplog.records if isinstance(getattr(r, "tw", None), dict) and "event" in r.tw]
    assert any(e["event"] == "investigation.replay_refused" for e in events)
    everything = caplog.text + json.dumps(events, default=str) + render(vd) + json.dumps(d.model_dump(mode="json"))
    assert CANARY not in everything and "x" * 100 not in everything


def test_continuation_state_never_reaches_logs_reports_or_evidence(caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    p = ScriptedProvider([with_state(tool("read_file", path="coffee_shop/pricing.py", start=30, end=41), item()),
                          answer(**B02_ANSWER)])  # fmt: skip
    vd = diagnose(evidence(), p)
    assert vd.diagnosis.status.value == "diagnosed"
    blob = caplog.text + render(vd) + json.dumps(vd.diagnosis.model_dump(mode="json")) + repr(vd)
    assert CANARY not in blob


def test_the_context_is_bound_to_the_job_attempt_given_by_the_caller() -> None:
    p = ScriptedProvider([answer(**B02_ANSWER)])
    with pytest.raises(ValueError, match="does not match"):
        investigate(evidence(), p, InvestigationLimits(), replay_context=ctx(provider="openai"))
    res = investigate(evidence(), ScriptedProvider([answer(**B02_ANSWER)]), replay_context=ctx(job_id=5, attempt=2))
    assert res.outcome == "answered"


def test_replay_sizes_are_observable_without_content(caplog: Any) -> None:
    caplog.set_level(logging.INFO)
    p = ScriptedProvider([with_state(tool("get_diff"), item("z" * 500)), answer(**B02_ANSWER)])
    investigate(evidence(), p)
    (rec,) = [r for r in caplog.records if r.getMessage() == "investigation finished"]
    tw = rec.tw  # type: ignore[attr-defined]
    assert tw["replay_envelopes"] == 1 and 500 < tw["replay_bytes"] == tw["replay_largest_bytes"] < 700
    assert "z" * 50 not in caplog.text
