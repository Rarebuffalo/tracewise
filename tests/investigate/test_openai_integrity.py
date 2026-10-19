"""Phase 46: independent audit of the OpenAI Responses codec (offline, synthetic fixtures, no key, no network).

* Identifiers: the recorded contract (research/openai-api-reference-2026-10-19, R-5/R-6) pairs every
  `function_call_output` with its `function_call` by `call_id` and documents NO length limit (gap G-5). Provider-issued
  ids are therefore preserved exactly; anything that would make the pairing ambiguous fails closed.
* Reasoning replay (R-10): only provider-issued `reasoning` items carrying `encrypted_content` are passed back, in
  order, next to the function calls of the same response. Anything else in the replay channel (which is not
  redacted) is refused, so it cannot become a path around P-2.
* P-2 on the real codec's bytes: every request, including retried attempts and the repair round.
* Error text never quotes the provider's document.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from tests.investigate.factory import B02_ANSWER, evidence
from tests.investigate.test_model_input_privacy import REPO, REPO_NEEDLES, _repo_evidence
from tests.investigate.test_openai_responses import KEY, Server, req, resp
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider, WireError
from tracewise.investigate.openai_responses import OpenAIResponsesWire
from tracewise.investigate.provider import Message, ToolCallRequest

W = OpenAIResponsesWire()
PREFIX = "call_" + "p" * 59  # 64 characters shared by two distinct provider-issued ids
assert len(PREFIX) == 64


def run(*items: Any, files: dict[str, str] | None = None, ev: Any = None) -> tuple[Any, Server]:
    s = Server(*items)
    p = HTTPProvider(
        W,
        SecretStr(KEY),
        AdapterConfig("model-x"),
        client=httpx.Client(transport=httpx.MockTransport(s)),
        sleep=lambda _s: None,
    )
    vd = diagnose(ev if ev is not None else evidence(files=files) if files else evidence(), p)
    return vd, s


def sent(s: Server, n: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = json.loads(s.requests[n].content)["input"]
    return items


def reasoning(rid: str) -> dict[str, Any]:
    return {"type": "reasoning", "id": rid, "summary": [], "encrypted_content": f"opaque-{rid}"}


def with_reasoning(doc: dict[str, Any], *items: dict[str, Any]) -> dict[str, Any]:
    return {**doc, "output": [*items, *doc["output"]]}


FINAL = json.dumps(B02_ANSWER)
READ = ("read_file", {"path": "coffee_shop/pricing.py", "start": 30, "end": 41})
GREP = ("grep", {"pattern": "TAX_RATE"})


# ------------------------------------------------------------------ identifiers (46C)


def test_ids_sharing_a_64_char_prefix_stay_distinct_and_pair_with_their_own_results() -> None:
    a, b = PREFIX + "-alpha", PREFIX + "-beta"
    vd, s = run(resp(calls=((a, *READ), (b, *GREP))), resp(text=FINAL))
    items = sent(s, 1)
    calls = {i["call_id"]: i["name"] for i in items if i["type"] == "function_call"}
    outs = {i["call_id"]: i["output"] for i in items if i["type"] == "function_call_output"}
    assert calls == {a: "read_file", b: "grep"}  # exact provider-issued ids, never truncated
    assert set(outs) == {a, b}
    assert "tool read_file" in outs[a] and "tool grep" in outs[b]  # each result is paired with its own call
    assert vd.diagnosis.status.value == "diagnosed"


def test_a_long_id_is_preserved_exactly_across_rounds() -> None:
    long_id = "call_" + "z" * 300
    _, s = run(resp(calls=((long_id, *READ),)), resp(calls=(("call_2", *GREP),)), resp(text=FINAL))
    third = sent(s, 2)
    assert [i["call_id"] for i in third if i["type"] == "function_call"] == [long_id, "call_2"]
    assert [i["call_id"] for i in third if i["type"] == "function_call_output"] == [long_id, "call_2"]


@pytest.mark.parametrize(
    "calls",
    [
        [{"type": "function_call", "call_id": "dup", "name": "grep", "arguments": "{}"}] * 2,
        [{"type": "function_call", "name": "grep", "arguments": "{}"}],
        [{"type": "function_call", "call_id": 7, "name": "grep", "arguments": "{}"}],
    ],
    ids=["duplicate-in-one-response", "missing", "not-a-string"],
)
def test_decode_refuses_ambiguous_or_missing_call_ids(calls: list[dict[str, Any]]) -> None:
    with pytest.raises(WireError):
        W.decode({**resp(), "output": calls})


def test_an_id_reused_in_a_later_round_fails_closed_before_anything_is_sent() -> None:
    vd, s = run(resp(calls=(("same", *READ),)), resp(calls=(("same", *GREP),)), resp(text=FINAL))
    assert len(s.requests) == 2  # the third request (ambiguous pairing) was never sent
    assert vd.diagnosis.status.value == "inconclusive" and vd.diagnosis.inconclusive_reason == "provider_failed"


@pytest.mark.parametrize(
    "msgs",
    [
        (Message("tool", "orphan", tool_call_id="nope"),),
        (Message("assistant", "", tool_calls=(ToolCallRequest("c1", "grep", "{}"),)), Message("user", "no result")),
        (
            Message("assistant", "", tool_calls=(ToolCallRequest("c1", "grep", "{}"),)),
            Message("tool", "r1", tool_call_id="c1"),
            Message("tool", "r2", tool_call_id="c1"),
        ),
        (Message("assistant", "", tool_calls=(ToolCallRequest("c1", "grep", "{}"),)), Message("tool", "r", tool_call_id=None)),
    ],
    ids=["result-without-call", "call-without-result", "two-results-one-call", "result-without-id"],
)
def test_encode_refuses_a_conversation_whose_pairing_is_not_exact(msgs: tuple[Message, ...]) -> None:
    with pytest.raises(WireError):
        W.encode("m", req(Message("user", "u"), *msgs))


# ------------------------------------------------------------------ reasoning replay provenance (46B)


def test_reasoning_items_stay_attached_to_their_own_round_in_order() -> None:
    _, s = run(
        with_reasoning(resp(calls=(("call_a", *READ),)), reasoning("rs_a")),
        with_reasoning(resp(calls=(("call_b", *GREP),)), reasoning("rs_b")),
        resp(text=FINAL),
    )
    seq = [(i["type"], i.get("id") or i.get("call_id")) for i in sent(s, 2) if i["type"] != "message"]
    assert seq == [
        ("reasoning", "rs_a"),
        ("function_call", "call_a"),
        ("function_call_output", "call_a"),
        ("reasoning", "rs_b"),
        ("function_call", "call_b"),
        ("function_call_output", "call_b"),
    ]
    assert sent(s, 2)[1] == reasoning("rs_a")  # passed back verbatim, never decoded or rebuilt


@pytest.mark.parametrize(
    "item",
    [
        {"type": "reasoning", "id": "rs", "summary": []},  # no encrypted_content although store=false (R-10)
        {"type": "reasoning", "id": "rs", "encrypted_content": ""},
        {"type": "reasoning", "encrypted_content": "x"},
        {"type": "reasoning", "id": 3, "encrypted_content": "x"},
    ],
    ids=["no-encrypted-content", "empty-encrypted-content", "no-id", "id-not-a-string"],
)
def test_decode_refuses_reasoning_items_without_the_documented_opaque_payload(item: dict[str, Any]) -> None:
    with pytest.raises(WireError):
        W.decode(with_reasoning(resp(calls=(("c", *GREP),)), item))


@pytest.mark.parametrize(
    "smuggled",
    [
        {"type": "message", "role": "user", "content": "AKIA" + "RQSMUGGLEDZZZZZZ"},
        {"type": "function_call_output", "call_id": "x", "output": "unredacted"},
        "a string",
    ],
    ids=["message", "tool-output", "not-an-item"],
)
def test_the_unredacted_replay_channel_only_carries_reasoning_items(smuggled: Any) -> None:
    m = Message("assistant", "", tool_calls=(ToolCallRequest("c1", "grep", "{}"),), replay=(smuggled,))
    with pytest.raises(WireError):
        W.encode("m", req(Message("user", "u"), m, Message("tool", "r", tool_call_id="c1")))


def test_retried_attempts_resend_the_identical_body_with_replay_once() -> None:
    _, s = run(
        with_reasoning(resp(calls=(("call_a", *READ),)), reasoning("rs_a")),
        httpx.Response(503, json={"error": {"code": "server_is_overloaded"}}),
        resp(text=FINAL),
    )
    assert len(s.requests) == 3 and s.requests[1].content == s.requests[2].content
    assert [i.get("id") for i in sent(s, 2) if i["type"] == "reasoning"] == ["rs_a"]


# ------------------------------------------------------------------ P-2 on every serialised request (46B)


def test_p2_holds_on_every_request_the_real_codec_serialises(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    malformed = "{not json " + REPO["replayed"]
    _, s = run(
        with_reasoning(resp(calls=(("c1", *READ),)), reasoning("rs_1")),
        resp(calls=(("c2", *GREP),)),
        httpx.Response(503, json={"error": {"code": "server_is_overloaded"}}),  # retried attempt is checked too
        resp(calls=(("c3", "get_diff", {}),)),
        resp(calls=(("c4", "list_dir", {"path": "coffee_shop"}),)),
        resp(calls=(("c5", "grep", {"pattern": REPO["argument"]}),)),  # the model echoes a secret in an argument
        resp(text=malformed),  # malformed final answer: replayed for the single repair round
        resp(text=FINAL),
        ev=_repo_evidence(monkeypatch),
    )
    assert len(s.requests) == 8
    wire = "\n".join(r.content.decode() for r in s.requests)
    assert [k for k, n in REPO_NEEDLES.items() if n in wire] == []
    for ordinary in ("return round(subtotal_ * TAX_RATE, 2)", "coffee_shop/pricing.py", "TAX_RATE"):
        assert ordinary in wire  # ordinary source context still reaches the model
    assert KEY not in wire
