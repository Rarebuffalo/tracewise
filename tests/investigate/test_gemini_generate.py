"""Gemini native `generateContent` codec (offline only). Synthetic fixtures; `httpx.MockTransport`; no network, no key.

Every fixture is built to the recorded field names (research/gemini-api-reference-2026-10-26, Addendum A). Nothing here
was observed from the real endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from tests.investigate.factory import B02_ANSWER, B02_FILES, evidence
from tracewise.analysis.diagnose import diagnose
from tracewise.investigate.gemini_generate import GeminiGenerateContentWire, SignedTurn
from tracewise.investigate.http_adapter import (
    AdapterConfig,
    HTTPProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRequestError,
    ProviderTimeout,
    ProviderUnavailable,
    WireError,
)
from tracewise.investigate.openai_responses import OpenAIResponsesWire
from tracewise.investigate.prompt import TOOL_SPECS
from tracewise.investigate.provider import Message, StepRequest, ToolCallRequest

MODEL = "gemini-test-1"
KEY = "synthetic-gemini-key-0000000000"
SIG = "SYNTHETIC-OPAQUE-SIGNATURE=="
FINISH_REASONS_REJECTED = (
    "FINISH_REASON_UNSPECIFIED", "MAX_TOKENS", "SAFETY", "RECITATION", "LANGUAGE", "OTHER", "BLOCKLIST",
    "PROHIBITED_CONTENT", "SPII", "MALFORMED_FUNCTION_CALL", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_OTHER",
    "NO_IMAGE", "IMAGE_RECITATION", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS", "MISSING_THOUGHT_SIGNATURE",
    "MALFORMED_RESPONSE", "ESCALATION", "PUP_LIMITED_DISABLED", "CONTINUATION", "SOMETHING_NEW",
)  # fmt: skip  # every documented value except STOP (N-13), plus an unknown one


def gresp(parts: list[dict[str, Any]], finish: str | None = "STOP", usage: Any = None, **extra: Any) -> dict[str, Any]:
    cand: dict[str, Any] = {"content": {"role": "model", "parts": parts}, "index": 0}
    if finish is not None:
        cand["finishReason"] = finish
    return {
        "candidates": [cand],
        "usageMetadata": usage if usage is not None else {"promptTokenCount": 40, "candidatesTokenCount": 7},
        **extra,
    }


def call(cid: str, name: str, args: dict[str, Any], sig: str | None = None) -> dict[str, Any]:
    part: dict[str, Any] = {"functionCall": {"id": cid, "name": name, "args": args}}
    if sig:
        part["thoughtSignature"] = sig
    return part


def req(*msgs: Message, tools: bool = True) -> StepRequest:
    return StepRequest(tuple(msgs), TOOL_SPECS if tools else (), tools, 4000, 30.0)


class Server:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, r: httpx.Request) -> httpx.Response:
        self.requests.append(r)
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a if isinstance(a, httpx.Response) else httpx.Response(200, json=a)


def provider(s: Server, **cfg: Any) -> tuple[HTTPProvider, GeminiGenerateContentWire]:
    w = GeminiGenerateContentWire(MODEL)
    p = HTTPProvider(w, SecretStr(KEY), AdapterConfig(MODEL, max_retries=0, **cfg), client=httpx.Client(transport=s.transport))
    return p, w


# ------------------------------------------------------------------ endpoint, model, authentication


def test_exact_endpoint_method_and_key_header_only() -> None:
    s = Server(gresp([{"text": "OK"}]))
    p, w = provider(s)
    assert p.step(req(Message("user", "hi"), tools=False)).text == "OK"
    r = s.requests[0]
    assert r.method == "POST" and str(r.url) == w.endpoint
    assert w.endpoint == f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    assert r.headers["x-goog-api-key"] == KEY and "authorization" not in r.headers
    assert KEY not in str(r.url) and KEY.encode() not in r.content


@pytest.mark.parametrize("bad", ["", "Gemini-1", "a/b", "a:b", "../x", "a?b=1", "a b", "a..b", "-a", "a" * 65, None])
def test_malformed_model_ids_are_refused(bad: Any) -> None:
    with pytest.raises(ValueError):
        GeminiGenerateContentWire(bad)


def test_the_request_model_must_be_the_codec_model() -> None:
    with pytest.raises(WireError, match="model"):
        GeminiGenerateContentWire(MODEL).encode("other-model", req(Message("user", "hi")))


# ------------------------------------------------------------------ request mapping


def test_encode_maps_system_user_tools_and_limits() -> None:
    w = GeminiGenerateContentWire(MODEL)
    body = w.encode(MODEL, req(Message("system", "policy"), Message("user", "evidence")))
    assert body["systemInstruction"] == {"parts": [{"text": "policy"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "evidence"}]}]
    decls = body["tools"][0]["functionDeclarations"]
    assert [d["name"] for d in decls] == [t.name for t in TOOL_SPECS]
    # JSON Schema goes in parametersJsonSchema, never in the OpenAPI-subset `parameters` (Addendum C, review D1)
    assert all("parameters" not in d for d in decls)
    assert [d["parametersJsonSchema"] for d in decls] == [t.parameters for t in TOOL_SPECS]
    assert body["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert body["generationConfig"] == {"maxOutputTokens": 4000, "candidateCount": 1}
    no_tools = w.encode(MODEL, req(Message("user", "evidence"), tools=False))
    assert "tools" not in no_tools and "toolConfig" not in no_tools


def test_tool_free_final_step_keeps_declarations_and_forbids_calls() -> None:
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))  # declares the tools
    r = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))
    history = (
        Message("user", "e"),
        Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay),
        Message("tool", "a.py", tool_call_id="c1"),
        Message("user", "now answer"),
    )
    body = w.encode(MODEL, req(*history, tools=False))
    assert body["toolConfig"] == {"functionCallingConfig": {"mode": "NONE"}}  # N-8
    assert [d["name"] for d in body["tools"][0]["functionDeclarations"]] == ["list_dir"]
    fresh = GeminiGenerateContentWire(MODEL)
    with pytest.raises(WireError):
        fresh.encode(MODEL, req(*history, tools=False))  # another instance: neither the replay nor declarations are known


# ------------------------------------------------------------------ response decoding


def test_decode_text_excludes_thoughts_and_maps_usage() -> None:
    w = GeminiGenerateContentWire(MODEL)
    r = w.decode(
        gresp(
            [{"text": "thinking summary", "thought": True}, {"text": "final "}, {"text": "answer", "thoughtSignature": SIG}],
            usage={"promptTokenCount": 40, "candidatesTokenCount": 7, "thoughtsTokenCount": 30},
        )
    )
    assert r.text == "final answer" and r.tool_calls == () and r.replay == ()
    assert (r.usage.input_tokens, r.usage.output_tokens) == (40, 37)  # thinking billed as output (N-24)


@pytest.mark.parametrize("reason", [*FINISH_REASONS_REJECTED, None])
def test_every_finish_reason_other_than_stop_fails_closed(reason: str | None) -> None:
    with pytest.raises(WireError, match="finish reason"):
        GeminiGenerateContentWire(MODEL).decode(gresp([{"text": "x"}], finish=reason))


@pytest.mark.parametrize(
    "doc",
    [
        [],
        "text",
        {"candidates": []},
        {"candidates": "x"},
        {**gresp([{"text": "a"}]), "candidates": [gresp([{"text": "a"}])["candidates"][0]] * 2},  # multiple
        {**gresp([{"text": "a"}]), "promptFeedback": {"blockReason": "SAFETY"}},
        {**gresp([{"text": "a"}]), "promptFeedback": "x"},
        {"candidates": ["x"], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}},
        {"candidates": [{"finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}},
        {
            "candidates": [{"finishReason": "STOP", "content": {"role": "user", "parts": [{"text": "a"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        },
        gresp([]),
        gresp(["x"]),
        gresp([{}]),
        gresp([{"inlineData": {"mimeType": "image/png", "data": "AA=="}}]),
        gresp([{"executableCode": {"code": "print(1)"}}]),
        gresp([{"text": 5}]),
        gresp([{"text": "a", "thought": "yes"}]),
        gresp([{"text": "a", "thoughtSignature": 5}]),
        gresp([{"text": "a", "thoughtSignature": ""}]),
        gresp([{"thought": True}]),
        gresp([{"functionCall": {"name": "list_dir", "args": {}}}]),  # no id: never invented (NG-4)
        gresp([{"functionCall": {"id": "", "name": "list_dir", "args": {}}}]),
        gresp([{"functionCall": {"id": "c", "args": {}}}]),
        gresp([{"functionCall": {"id": "c", "name": "list_dir", "args": "x"}}]),
        gresp([{"functionCall": {"id": "c", "name": "list_dir", "args": {}, "extra": 1}}]),
        gresp([{"functionCall": "x"}]),
        gresp([{"functionCall": {"id": "c", "name": "list_dir"}, "text": "a"}]),
        gresp([{"functionCall": {"id": "c", "name": "list_dir"}, "thought": True}]),
        gresp([call("c", "list_dir", {}), call("c", "grep", {"pattern": "x"})]),  # duplicate id
        gresp([{"text": "a"}], usage="x"),
        {"candidates": gresp([{"text": "a"}])["candidates"]},  # usage missing
        gresp([{"text": "a"}], usage={"promptTokenCount": 1}),
        gresp([{"text": "a"}], usage={"promptTokenCount": -1, "candidatesTokenCount": 1}),
        gresp([{"text": "a"}], usage={"promptTokenCount": True, "candidatesTokenCount": 1}),
        gresp([{"text": "a"}], usage={"promptTokenCount": 1, "candidatesTokenCount": 1, "thoughtsTokenCount": "9"}),
    ],
)
def test_decode_fails_closed_on_anything_outside_the_supported_subset(doc: Any) -> None:
    with pytest.raises(WireError):
        GeminiGenerateContentWire(MODEL).decode(doc)


def test_parallel_calls_with_ids_decode_in_order_and_signature_only_parts_are_kept() -> None:
    w = GeminiGenerateContentWire(MODEL)
    r = w.decode(
        gresp(
            [
                {"text": "plan", "thought": True},
                call("c1", "read_file", {"path": "a.py"}, SIG),
                call("c2", "grep", {"pattern": "x"}),
                {"thoughtSignature": SIG},
            ]
        )
    )
    assert [(c.id, c.name, json.loads(c.arguments)) for c in r.tool_calls] == [
        ("c1", "read_file", {"path": "a.py"}),
        ("c2", "grep", {"pattern": "x"}),
    ]
    assert r.text is None and len(r.replay) == 1 and isinstance(r.replay[0], SignedTurn)


# ------------------------------------------------------------------ continuation, pairing and replay


def test_full_investigation_replays_the_model_turn_verbatim_and_pairs_results_by_id() -> None:
    planted = "ghp_" + "Qx9" * 12
    files = {
        **B02_FILES,
        "coffee_shop/pricing.py": B02_FILES["coffee_shop/pricing.py"].replace(  # type: ignore[union-attr]
            "TAX_RATE = 0.21", f"TAX_RATE = 0.21  # {planted}"
        ),
    }
    turn = [
        {"text": "plan", "thought": True, "thoughtSignature": SIG},
        call("c1", "read_file", {"path": "coffee_shop/pricing.py", "start": 1, "end": 45}, SIG),
        call("c2", "list_dir", {"path": "coffee_shop"}),
    ]
    s = Server(gresp(turn), gresp([{"text": json.dumps(B02_ANSWER)}]))
    p, w = provider(s)
    vd = diagnose(evidence(files=files), p)
    assert vd.diagnosis.status.value == "diagnosed" and vd.diagnosis.usage.provider == "gemini"
    second = json.loads(s.requests[1].content)
    model_turn, results = second["contents"][-2], second["contents"][-1]
    assert model_turn == {"role": "model", "parts": turn}  # verbatim: thought part and signatures unchanged
    assert results["role"] == "user"
    pairs = [(r["functionResponse"]["id"], r["functionResponse"]["name"]) for r in results["parts"]]
    assert pairs == [("c1", "read_file"), ("c2", "list_dir")]
    assert "TAX_RATE" in results["parts"][0]["functionResponse"]["response"]["output"]
    wire = "\n".join(r.content.decode() for r in s.requests)
    assert "Qx9Qx9Qx9" not in wire  # P-2 still holds for tool results
    assert all(str(r.url) == w.endpoint for r in s.requests)
    assert SIG not in json.dumps(vd.diagnosis.model_dump(mode="json"))  # the replay never reaches the diagnosis


def _turn(w: GeminiGenerateContentWire, *calls: dict[str, Any]) -> tuple[tuple[ToolCallRequest, ...], tuple[Any, ...]]:
    w.encode(MODEL, req(Message("user", "e")))
    r = w.decode(gresp(list(calls)))
    return r.tool_calls, r.replay


def _history(tcs: tuple[ToolCallRequest, ...], replay: tuple[Any, ...], *results: Message) -> StepRequest:
    return req(Message("user", "e"), Message("assistant", "", tool_calls=tcs, replay=replay), *results)


def test_forged_and_modified_replay_is_refused() -> None:
    w = GeminiGenerateContentWire(MODEL)
    tcs, replay = _turn(w, call("c1", "list_dir", {"path": "src"}, SIG))
    ok = w.encode(MODEL, _history(tcs, replay, Message("tool", "x", tool_call_id="c1")))
    assert ok["contents"][1]["parts"][0]["thoughtSignature"] == SIG
    forged = SignedTurn(
        {"role": "model", "parts": [call("c1", "list_dir", {"path": "src"})]}, MODEL, b"\x00" * 16, None, b"\x00" * 32
    )
    with pytest.raises(WireError, match="provenance"):
        w.encode(MODEL, _history(tcs, (forged,), Message("tool", "x", tool_call_id="c1")))
    replay[0]._content["parts"][0]["functionCall"]["args"]["path"] = "/etc"  # tampering after decode
    with pytest.raises(WireError, match="provenance"):
        w.encode(MODEL, _history(tcs, replay, Message("tool", "x", tool_call_id="c1")))
    with pytest.raises(WireError, match="not produced by this codec"):
        w.encode(MODEL, _history(tcs, ({"role": "model", "parts": []},), Message("tool", "x", tool_call_id="c1")))


@pytest.mark.parametrize(
    "tcs",
    [
        (ToolCallRequest("c9", "list_dir", '{"path": "src"}'),),  # other id
        (ToolCallRequest("c1", "grep", '{"path": "src"}'),),  # other name
        (ToolCallRequest("c1", "list_dir", '{"path": "lib"}'),),  # other arguments
        (ToolCallRequest("c1", "list_dir", '{"path": "src"}'), ToolCallRequest("c2", "list_dir", "{}")),  # extra call
        (ToolCallRequest("c1", "list_dir", "not json"),),
    ],
)
def test_replay_must_match_the_validated_tool_calls_exactly(tcs: tuple[ToolCallRequest, ...]) -> None:
    w = GeminiGenerateContentWire(MODEL)
    _, replay = _turn(w, call("c1", "list_dir", {"path": "src"}, SIG))
    results = [Message("tool", "x", tool_call_id=tc.id) for tc in tcs]
    with pytest.raises(WireError):
        w.encode(MODEL, _history(tcs, replay, *results))


def test_replay_is_bound_to_its_codec_instance_model_and_provider() -> None:
    a = GeminiGenerateContentWire(MODEL)
    tcs, replay = _turn(a, call("c1", "list_dir", {"path": "src"}, SIG))
    result = Message("tool", "x", tool_call_id="c1")
    for other in (GeminiGenerateContentWire(MODEL), GeminiGenerateContentWire("gemini-other-2")):
        with pytest.raises(WireError):
            other.encode(other.model, _history(tcs, replay, result))
    with pytest.raises(WireError):
        OpenAIResponsesWire().encode("m", _history(tcs, replay, result))  # the OpenAI codec refuses it too
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "gAAAA"}
    with pytest.raises(WireError):
        a.encode(MODEL, _history(tcs, (reasoning,), result))  # and Gemini refuses OpenAI's opaque items
    with pytest.raises(WireError):
        a.encode(MODEL, _history(tcs, (), result))  # a tool-call turn without its replay
    with pytest.raises(WireError):
        a.encode(MODEL, req(Message("user", "e"), Message("assistant", "text", replay=replay)))  # replay without calls


@pytest.mark.parametrize(
    "results",
    [
        (),  # a call without a result
        (Message("tool", "x", tool_call_id="c9"),),  # an unmatched result
        (Message("tool", "x", tool_call_id="c1"), Message("tool", "x", tool_call_id="c1")),  # a duplicate result
        (Message("tool", "x", tool_call_id=None),),
    ],
)
def test_results_are_paired_by_id_only(results: tuple[Message, ...]) -> None:
    w = GeminiGenerateContentWire(MODEL)
    tcs, replay = _turn(w, call("c1", "list_dir", {"path": "src"}, SIG))
    with pytest.raises(WireError):
        w.encode(MODEL, _history(tcs, replay, *results))


def test_replay_is_never_displayed_or_serialised() -> None:
    w = GeminiGenerateContentWire(MODEL)
    _, replay = _turn(w, call("c1", "list_dir", {"path": "src"}, SIG))
    turn = replay[0]
    assert SIG not in repr(turn) and SIG not in str(turn) and "hidden" in repr(turn)
    with pytest.raises(TypeError):
        json.dumps({"replay": turn})
    with pytest.raises(WireError) as ei:  # and a refusal names no content
        GeminiGenerateContentWire(MODEL).encode(
            MODEL, _history(_turn(w, call("c2", "grep", {"pattern": "q"}))[0], replay, Message("tool", "x", tool_call_id="c2"))
        )
    assert SIG not in str(ei.value) and "src" not in str(ei.value)


# ------------------------------------------------------------------ transport behaviour through the shared adapter


def test_http_errors_redirects_size_and_timeouts_fail_closed_without_retries_or_content() -> None:
    marker = "LEAK-provider-error-body"
    cases: list[tuple[Any, type[Exception]]] = [
        (httpx.Response(500, json={"error": {"message": marker}}), ProviderUnavailable),
        (httpx.Response(429, json={"error": {"message": marker}}), ProviderUnavailable),
        (httpx.Response(401, json={"error": {"message": marker}}), ProviderAuthError),
        (httpx.Response(400, json={"error": {"message": marker}}), ProviderRequestError),
        (httpx.Response(302, headers={"location": "https://evil.example/"}), ProviderRequestError),
        (httpx.Response(200, content=b"not json " + marker.encode()), ProviderError),
        (httpx.ReadTimeout("slow"), ProviderTimeout),
    ]
    for answer, exc in cases:
        s = Server(answer)
        p, _ = provider(s)
        with pytest.raises(exc) as ei:
            p.step(req(Message("user", "hi")))
        assert len(s.requests) == 1  # no retry, no redirect followed
        assert marker not in str(ei.value) and KEY not in str(ei.value)
    s = Server(httpx.Response(200, content=b"x" * 5000))
    p, _ = provider(s, max_response_bytes=2048)
    with pytest.raises(ProviderError, match="exceeds"):
        p.step(req(Message("user", "hi")))


def test_benchmark_model_mode_wires_gemini_behind_the_same_guards(tmp_path: Path) -> None:
    import secrets

    from tracewise.bench.model_provider import build_model_run
    from tracewise.investigate.model_access import AccessRefused

    key = tmp_path / "k" / "gemini.key"
    key.parent.mkdir()
    key.write_text("synthetic-" + secrets.token_hex(12))
    key.chmod(0o600)
    ref = "2026-10-26 owner offline test"
    s = Server(gresp([{"text": "OK"}]))
    kw: dict[str, Any] = {"key_file": key, "authorization_ref": ref, "max_requests": 2, "env": {}}
    run = build_model_run(model=MODEL, api="gemini-generate-content", inner=s.transport, **kw)
    try:
        assert run.transport.endpoint == run.provider.codec.endpoint  # the codec's exact URL, model included
        assert run.transport.endpoint.endswith(f"/models/{MODEL}:generateContent")
        assert run.summary()["api"] == "gemini-generate-content"
        assert run.provider.step(req(Message("user", "hi"), tools=False)).text == "OK"
        with httpx.Client(transport=run.transport) as c, pytest.raises(AccessRefused):
            c.post("https://api.openai.com/v1/responses", content=b"{}")  # another provider's endpoint is refused
    finally:
        run.close()
    for bad in ("Gemini:1", "a/b"):
        with pytest.raises(AccessRefused, match="malformed"):
            build_model_run(model=bad, api="gemini-generate-content", **kw)
    with pytest.raises(AccessRefused, match="--api"):
        build_model_run(model=MODEL, api="gemini-chat", **kw)


def test_a_mock_gemini_benchmark_run_never_writes_the_key_or_the_replayed_turn(tmp_path: Path, capsys: Any) -> None:
    """Through the benchmark CLI (real harness, scorer and output check) with a Gemini-shaped mock: each
    investigation's first request gets a signed tool call, the next a final answer."""
    import secrets

    from tracewise.bench.__main__ import main

    key_value = "synthetic-" + secrets.token_hex(12)
    key = tmp_path / "k" / "gemini.key"
    key.parent.mkdir()
    key.write_text(key_value)
    key.chmod(0o600)
    answer = {"category": "unknown", "root_cause": "Not determined.", "why": "Synthetic mock answer.", "next_steps": ["x"]}
    bodies: list[bytes] = []

    def handle(r: httpx.Request) -> httpx.Response:
        bodies.append(r.content)
        if b"functionResponse" not in r.content:
            return httpx.Response(200, json=gresp([call(f"c{len(bodies)}", "list_dir", {"path": "."}, SIG)]))
        return httpx.Response(200, json=gresp([{"text": json.dumps(answer)}]))

    out = tmp_path / "out"
    argv = [
        "run", "--kind", "model", "--api", "gemini-generate-content", "--model", MODEL, "--key-file", str(key),
        "--authorization-ref", "2026-10-26 owner offline test", "--max-requests", "10", "--case", "B-02", "--reps", "1",
        "--out", str(out),
    ]  # fmt: skip
    assert main(argv, env={}, inner=httpx.MockTransport(handle)) in (0, 1)
    results = json.loads((out / "results.json").read_text())
    assert results["provider"]["api"] == "gemini-generate-content" and results["provider"]["kind"] == "model"
    assert any(SIG.encode() in b for b in bodies[1:])  # the signed turn went back to the provider...
    written = "".join(p.read_text() for p in out.iterdir())
    captured = capsys.readouterr()
    assert SIG not in written + captured.out + captured.err  # ...and nowhere else
    assert key_value not in written + captured.out + captured.err
    with pytest.raises(SystemExit):
        main(["run", "--provider", "oracle", "--api", "gemini-generate-content", "--out", str(tmp_path / "x")], env={})


# ------------------------------------------------------------------ review fixes (2026-10-26)


def test_a_genuine_replay_cannot_be_reused_in_another_conversation_or_repeated() -> None:
    """A replay is bound to the exact request that produced it (system instruction and contents), so it is accepted only
    directly after that history: not in another conversation, not twice in the same one."""
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "conversation A")))
    r = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))
    turn = Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay)
    result = Message("tool", "x", tool_call_id="c1")
    assert w.encode(MODEL, req(Message("user", "conversation A"), turn, result))["contents"][1]["role"] == "model"
    with pytest.raises(WireError, match="conversation"):
        w.encode(MODEL, req(Message("user", "conversation B"), turn, result))
    with pytest.raises(WireError, match="conversation"):
        w.encode(MODEL, req(Message("system", "other policy"), Message("user", "conversation A"), turn, result))
    with pytest.raises(WireError, match="conversation"):
        w.encode(MODEL, req(Message("user", "conversation A"), turn, result, Message("user", "again"), turn, result))
    orphan = GeminiGenerateContentWire(MODEL).decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))  # no request
    with pytest.raises(WireError):
        w.encode(MODEL, req(Message("user", "conversation A"), Message("assistant", "", tool_calls=orphan.tool_calls,
                                                                         replay=orphan.replay), result))  # fmt: skip


def test_replay_refuses_pickling_and_copying() -> None:
    import copy
    import pickle

    w = GeminiGenerateContentWire(MODEL)
    _, replay = _turn(w, call("c1", "list_dir", {"path": "src"}, SIG))
    for f in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError) as ei:
            f(replay[0])
        assert SIG not in str(ei.value)


def test_product_settings_reject_gemini_and_selection_is_unchanged() -> None:
    from pydantic import ValidationError

    from tracewise.config import Settings
    from tracewise.investigate import providers

    with pytest.raises(ValidationError):
        Settings(llm_provider="gemini")  # type: ignore[arg-type]
    with pytest.raises(providers.ProviderConfigError, match="not enabled"):
        providers.provider_factory(Settings(tw_env="test", llm_provider="openai", openai_api_key=SecretStr("x" * 12)))


def test_repair_turn_after_a_signed_text_answer_is_an_explicit_limitation_that_fails_closed() -> None:
    """The investigator's repair turn re-sends the rejected answer as plain text (truncated, no replay), so a signature
    on that text part is not sent back. Whether text-part signatures are required is undocumented (NG-2). If the
    provider demands one, it answers MISSING_THOUGHT_SIGNATURE (or an HTTP 400): both fail closed, never a guess."""
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e"), tools=False))
    first = w.decode(gresp([{"text": "not json", "thoughtSignature": SIG}]))
    assert first.text == "not json" and first.replay == ()  # no tool calls: nothing to replay
    repair = req(Message("user", "e"), Message("assistant", "not json"), Message("user", "fix it"), tools=False)
    body = w.encode(MODEL, repair)
    assert body["contents"][1] == {"role": "model", "parts": [{"text": "not json"}]}  # explicit: no signature
    with pytest.raises(WireError, match="finish reason"):
        w.decode(gresp([{"text": "x"}], finish="MISSING_THOUGHT_SIGNATURE"))
    s = Server(httpx.Response(400, json={"error": {"message": SIG}}))
    p, _ = provider(s)
    with pytest.raises(ProviderRequestError) as ei:
        p.step(repair)
    assert SIG not in str(ei.value)


def test_a_stale_turn_is_refused_even_when_the_identical_history_is_reconstructed() -> None:
    """The same benchmark case run twice produces byte-identical histories, so the request digest alone would match.
    Each conversation has its own random epoch: a turn from conversation 1 is stale in conversation 2."""
    w = GeminiGenerateContentWire(MODEL)
    resp = gresp([call("c1", "list_dir", {"path": "src"}, SIG)])
    w.encode(MODEL, req(Message("user", "same evidence")))
    old = w.decode(resp)
    w.encode(MODEL, req(Message("user", "same evidence")))  # conversation 2 starts: identical first request
    new = w.decode(resp)
    result = Message("tool", "x", tool_call_id="c1")

    def history(r: Any) -> StepRequest:
        return req(Message("user", "same evidence"), Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay), result)

    with pytest.raises(WireError, match="conversation"):
        w.encode(MODEL, history(old))
    assert w.encode(MODEL, history(new))["contents"][1]["parts"][0]["thoughtSignature"] == SIG  # the live turn works
    assert w.encode(MODEL, history(new))  # and keeps working at every later step of its own conversation


def test_one_decode_per_encode_a_second_response_is_never_replayable() -> None:
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))
    first = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))
    second = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))  # no fresh request
    result = Message("tool", "x", tool_call_id="c1")
    w.encode(MODEL, req(Message("user", "e"), Message("assistant", "", tool_calls=first.tool_calls, replay=first.replay), result))
    with pytest.raises(WireError, match="conversation"):
        w.encode(
            MODEL, req(Message("user", "e"), Message("assistant", "", tool_calls=second.tool_calls, replay=second.replay), result)
        )


# ------------------------------------------------------------------ contract audit fixes (2026-10-30)


def test_the_final_tool_free_step_also_uses_json_schema_declarations() -> None:
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))
    r = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))
    h = (
        Message("user", "e"),
        Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay),
        Message("tool", "x", tool_call_id="c1"),
    )
    decl = w.encode(MODEL, req(*h, tools=False))["tools"][0]["functionDeclarations"][0]
    assert "parameters" not in decl and decl["parametersJsonSchema"]["additionalProperties"] is False


def test_secret_shaped_arguments_survive_the_provider_view_redaction() -> None:
    """D2: the investigator redacts tool-call arguments in the view sent to the provider. The replay check must accept
    the redacted form of exactly the signed arguments (and nothing else), while the signed, unredacted turn is what is
    replayed."""
    from tracewise.investigate.loop import investigate

    turn = [call("c1", "grep", {"pattern": "password=\\w+"}, SIG)]
    s = Server(gresp(turn), gresp([{"text": json.dumps(B02_ANSWER)}]))
    p, _ = provider(s)
    res = investigate(evidence(files=B02_FILES), p)
    assert res.outcome == "answered" and len(s.requests) == 2  # not provider_failed at the replay check
    second = json.loads(s.requests[1].content)
    assert second["contents"][-2] == {"role": "model", "parts": turn}  # the signed turn, verbatim
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))
    r = w.decode(gresp([call("c1", "grep", {"pattern": "password=\\w+"}, SIG)]))
    for forged_args in ('{"pattern": "password=[REDACTED] or more"}', '{"pattern": "other"}'):
        tcs = (ToolCallRequest("c1", "grep", forged_args),)
        with pytest.raises(WireError, match="differ"):
            w.encode(MODEL, req(Message("user", "e"), Message("assistant", "", tool_calls=tcs, replay=r.replay),
                                Message("tool", "x", tool_call_id="c1")))  # fmt: skip


def test_a_rejected_call_to_an_undeclared_tool_does_not_break_the_final_step() -> None:
    """D3: the model calls a name that was never declared; the investigator answers REJECTED. The tool-free step must
    still encode, declaring only the known names, and never invent a declaration."""
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))
    r = w.decode(gresp([call("c1", "rm_rf", {}, SIG), call("c2", "list_dir", {"path": "."})]))
    h = (
        Message("user", "e"),
        Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay),
        Message("tool", "REJECTED: unknown tool 'rm_rf'", tool_call_id="c1"),
        Message("tool", "a.py", tool_call_id="c2"),
        Message("user", "answer now"),
    )
    body = w.encode(MODEL, req(*h, tools=False))
    assert [d["name"] for d in body["tools"][0]["functionDeclarations"]] == ["list_dir"]
    assert body["toolConfig"] == {"functionCallingConfig": {"mode": "NONE"}}
    w2 = GeminiGenerateContentWire(MODEL)
    w2.encode(MODEL, req(Message("user", "e"), tools=False))  # nothing declared at all
    r2 = w2.decode(gresp([call("c1", "rm_rf", {}, SIG)]))
    h2 = (Message("user", "e"), Message("assistant", "", tool_calls=r2.tool_calls, replay=r2.replay),
          Message("tool", "REJECTED", tool_call_id="c1"))  # fmt: skip
    assert "tools" not in w2.encode(MODEL, req(*h2, tools=False))  # nothing known: no invented declaration


def test_a_failed_encode_changes_no_codec_state() -> None:
    """D4/D5: a failed encode neither starts a new conversation nor leaves a decode binding to a request never sent."""
    w = GeminiGenerateContentWire(MODEL)
    w.encode(MODEL, req(Message("user", "e")))
    r = w.decode(gresp([call("c1", "list_dir", {"path": "src"}, SIG)]))
    live = (
        Message("user", "e"),
        Message("assistant", "", tool_calls=r.tool_calls, replay=r.replay),
        Message("tool", "x", tool_call_id="c1"),
    )
    with pytest.raises(WireError):
        w.encode(MODEL, req(Message("system", "s")))  # no content: fails, and must not start a new conversation
    assert w.encode(MODEL, req(*live))  # the live conversation continues
    with pytest.raises(WireError):
        w.encode(MODEL, req(Message("user", "e"), Message("tool", "x", tool_call_id="zz")))  # fails after a good encode
    orphan = w.decode(gresp([call("c9", "list_dir", {"path": "src"}, SIG)]))  # its request binding was dropped
    with pytest.raises(WireError, match="conversation"):
        w.encode(MODEL, req(*live, Message("assistant", "", tool_calls=orphan.tool_calls, replay=orphan.replay),
                            Message("tool", "x", tool_call_id="c9")))  # fmt: skip


def test_a_model_turn_must_carry_the_model_role() -> None:
    """D6: content is replayed verbatim, so a turn without role 'model' is refused rather than patched."""
    doc = gresp([call("c1", "list_dir", {"path": "src"}, SIG)])
    del doc["candidates"][0]["content"]["role"]
    with pytest.raises(WireError, match="model"):
        GeminiGenerateContentWire(MODEL).decode(doc)


def test_tool_use_prompt_tokens_count_as_input() -> None:
    usage = {"promptTokenCount": 40, "candidatesTokenCount": 7, "thoughtsTokenCount": 3, "toolUsePromptTokenCount": 5}
    r = GeminiGenerateContentWire(MODEL).decode(gresp([{"text": "a"}], usage=usage))
    assert (r.usage.input_tokens, r.usage.output_tokens) == (45, 10)
    for bad in ("5", -1, True):
        with pytest.raises(WireError):
            GeminiGenerateContentWire(MODEL).decode(gresp([{"text": "a"}], usage={**usage, "toolUsePromptTokenCount": bad}))
