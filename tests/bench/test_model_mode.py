"""Benchmark model mode (`run --kind model`): every guard, exercised with a mock transport only.

No key is real (each is generated per test), no request leaves the process (httpx.MockTransport; the network guard
plugin also blocks sockets), and the real network transport is never constructed here.
"""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

import httpx
import pytest

from tracewise.bench import __main__ as cli
from tracewise.bench import model_provider
from tracewise.bench.__main__ import main
from tracewise.bench.harness import INTERRUPTED_BEFORE, INTERRUPTED_DURING, run_suite
from tracewise.bench.model_provider import MAX_REQUEST_BYTES, MAX_REQUESTS_CEILING, NOTICE, build_model_run
from tracewise.bench.providers import make
from tracewise.bench.report import render_report
from tracewise.bench.score import score_results
from tracewise.investigate.model_access import (
    REPO_ROOT,
    AccessRefused,
    EndpointBudgetTransport,
    RequestBudgetExhausted,
    RequestTooLarge,
    SecretCanary,
    read_key_file,
)
from tracewise.investigate.openai_responses import ENDPOINT
from tracewise.investigate.provider import Message, StepRequest

REF = "2026-10-25 owner test-only reference"
ANSWER = {"category": "unknown", "root_cause": "Not determined.", "why": "Synthetic mock answer.", "next_steps": ["x"]}


def response(text: str) -> dict[str, Any]:
    return {
        "object": "response",
        "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def tool_call_response(n: int) -> dict[str, Any]:
    call = {"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": "list_dir", "arguments": "{}"}
    return {"object": "response", "status": "completed", "output": [call], "usage": {"input_tokens": 10, "output_tokens": 5}}


class Mock:
    """A stand-in for the network: records requests, answers with a fixed Responses document or status.
    `tool_first`: every investigation's first request gets a tool call, so it needs at least a second request."""

    def __init__(self, status: int = 200, *, tool_first: bool = False, answer: dict[str, Any] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status, self.tool_first, self.answer = status, tool_first, answer or ANSWER
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"type": "server_error"}})
        if self.tool_first and b"function_call_output" not in req.content:
            return httpx.Response(200, json=tool_call_response(len(self.requests)))
        return httpx.Response(200, json=response(json.dumps(self.answer)))


@pytest.fixture
def key_file(tmp_path: Path) -> tuple[Path, str]:
    key = "sk-synthetic-" + secrets.token_hex(16)  # generated per test; never a real credential
    p = tmp_path / "keys" / "model.key"
    p.parent.mkdir()
    p.write_text(key + "\n")
    p.chmod(0o600)
    return p, key


def args(key: Path, out: Path, *extra: str, max_requests: str = "10") -> list[str]:
    return [
        "run", "--kind", "model", "--model", "test-model-1", "--key-file", str(key), "--authorization-ref", REF,
        "--max-requests", max_requests, "--case", "B-02", "--reps", "1", "--out", str(out), *extra,
    ]  # fmt: skip


def outputs(out: Path) -> str:
    return "".join(p.read_text() for p in sorted(out.glob("*")) if p.is_file())


# ------------------------------------------------------------------ refusals (nothing sent, nothing written)


@pytest.mark.parametrize("env", [{"CI": "true"}, {"PYTEST_CURRENT_TEST": "x"}])
def test_refused_under_ci_or_a_test_runner(key_file, tmp_path, env) -> None:  # type: ignore[no-untyped-def]
    mock = Mock()
    with pytest.raises(AccessRefused, match="test runners or CI"):
        build_model_run(model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env=env, inner=mock.transport)
    assert main(args(key_file[0], tmp_path / "out"), env=env, inner=mock.transport) == 2
    assert mock.requests == [] and not (tmp_path / "out").exists()


def test_the_cli_refuses_under_this_test_runner_by_default(key_file, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """No `env` seam: the real process environment of pytest is read, so the mode refuses before any key read."""
    mock = Mock()
    assert main(args(key_file[0], tmp_path / "out"), inner=mock.transport) == 2
    assert mock.requests == [] and not (tmp_path / "out").exists()
    assert key_file[1] not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"authorization_ref": None}, "authorization reference is required"),
        ({"authorization_ref": "short"}, "malformed"),
        ({"authorization_ref": "x" * 8 + "\nINJECT"}, "malformed"),
        ({"model": None}, "explicit model id"),
        ({"model": "bad model id!"}, "model id is malformed"),
        ({"max_requests": None}, "--max-requests"),
        ({"max_requests": 0}, "--max-requests"),
        ({"max_requests": MAX_REQUESTS_CEILING + 1}, "--max-requests"),
        ({"key_file": None}, "key file is required"),
    ],
)
def test_configuration_refusals(key_file, over, why) -> None:  # type: ignore[no-untyped-def]
    mock = Mock()
    kw: dict[str, Any] = {"model": "m-1", "key_file": key_file[0], "authorization_ref": REF, "max_requests": 5}
    kw.update(over)
    with pytest.raises(AccessRefused, match=why) as ei:
        build_model_run(**kw, env={}, inner=mock.transport)
    assert key_file[1] not in str(ei.value) and mock.requests == []


def test_key_file_rules(tmp_path: Path, key_file) -> None:  # type: ignore[no-untyped-def]
    good, key = key_file
    assert read_key_file(good).get_secret_value() == key
    loose = tmp_path / "loose.key"
    loose.write_text(key)
    for mode in (0o644, 0o640, 0o604):
        loose.chmod(mode)
        with pytest.raises(AccessRefused, match="owner only"):
            read_key_file(loose)
    link = tmp_path / "link.key"
    link.symlink_to(good)
    with pytest.raises(AccessRefused, match="symlink"):
        read_key_file(link)
    with pytest.raises(AccessRefused, match="regular file"):
        read_key_file(tmp_path)
    with pytest.raises(AccessRefused, match="not readable"):
        read_key_file(tmp_path / "missing.key")
    repo = tmp_path / "repo"  # a stand-in repository root, so nothing is written inside the real one
    (repo / "sub").mkdir(parents=True)
    inside = repo / "sub" / "model.key"
    inside.write_text(key)
    inside.chmod(0o600)
    with pytest.raises(AccessRefused, match="outside the repository"):
        read_key_file(inside, repo_root=repo)
    assert REPO_ROOT == Path(__file__).resolve().parents[2]  # the default root is this repository
    for content in ("short", "two words here", "x" * 600):
        bad = tmp_path / "bad.key"
        bad.write_text(content)
        bad.chmod(0o600)
        with pytest.raises(AccessRefused):
            read_key_file(bad)
        bad.unlink()


def test_cli_rejects_mixed_kinds(key_file, tmp_path) -> None:  # type: ignore[no-untyped-def]
    for argv in (
        ["run", "--kind", "model", "--provider", "oracle", "--out", str(tmp_path)],
        ["run", "--provider", "oracle", "--model", "m-1", "--out", str(tmp_path)],
        ["run", "--out", str(tmp_path)],
    ):
        with pytest.raises(SystemExit) as e:
            main(argv, env={})
        assert e.value.code == 2


# ------------------------------------------------------------------ transport: host lock and request cap


def test_transport_allows_only_post_to_the_endpoint_and_counts_a_hard_cap() -> None:
    mock = Mock()
    t = EndpointBudgetTransport(mock.transport, ENDPOINT, 2, max_request_bytes=1024)
    with httpx.Client(transport=t) as c:
        for method, url in (("GET", ENDPOINT), ("POST", "https://api.openai.com/v1/other"), ("POST", "https://evil.example/")):
            with pytest.raises(AccessRefused):
                c.request(method, url)
        assert mock.requests == [] and t.refused == 3
        c.post(ENDPOINT, json={})
        c.post(ENDPOINT, json={})
        with pytest.raises(RequestBudgetExhausted):
            c.post(ENDPOINT, json={})
    assert (len(mock.requests), t.sent, t.refused, t.exhausted) == (2, 2, 4, True)


def test_adapter_retries_are_zero_and_the_reference_is_never_used(key_file) -> None:  # type: ignore[no-untyped-def]
    mock = Mock(status=503)
    run = build_model_run(model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={}, inner=mock.transport)
    assert run.provider.config.max_retries == 0

    class Untouchable:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError("the model factory must never read the reference")

    provider = run.factory()(Untouchable(), "C1", Untouchable())  # type: ignore[arg-type]
    req = StepRequest((Message("user", "hello"),), (), False, 1000, 5.0)
    with pytest.raises(Exception) as ei:
        provider.step(req)
    assert len(mock.requests) == 1  # a 503 is not retried
    assert key_file[1] not in str(ei.value) and key_file[1] not in repr(provider)
    sent = mock.requests[0]
    assert str(sent.url) == ENDPOINT and sent.headers["authorization"] == f"Bearer {key_file[1]}"


# ------------------------------------------------------------------ a full mock run through the real harness


def test_mock_model_run_is_labelled_capped_and_never_contains_the_key(key_file, tmp_path, caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    mock = Mock()
    out = tmp_path / "out"
    code = main(args(key_file[0], out), env={}, inner=mock.transport)
    assert code in (0, 1)  # completeness depends on the scorer; the plumbing is what is under test
    results = json.loads((out / "results.json").read_text())
    prov = results["provider"]
    assert prov["kind"] == "model" and prov["name"] == "model:test-model-1" and prov["notice"] == NOTICE
    assert prov["authorization_ref"] == REF and prov["max_retries"] == 0
    assert prov["requests"] == {
        "max": 10,
        "sent": len(mock.requests),
        "refused": 0,
        "refused_over_cap": 0,
        "refused_too_large": 0,
        "budget_exhausted": False,
    }
    assert prov["max_request_bytes"] == MAX_REQUEST_BYTES
    assert results["interrupted"] is None and results["run_id"] == results["config_id"]  # complete: one identity
    assert 1 <= len(mock.requests) <= 10 and all(str(r.url) == ENDPOINT for r in mock.requests)
    report = (out / "report.md").read_text()
    assert "Model-based evaluation, not proven model accuracy" in report and "Protocol validation" not in report
    key = key_file[1]
    assert key not in outputs(out) and key not in caplog.text and str(key_file[0]) not in outputs(out)
    for r in mock.requests:  # the expected answer never reaches the model
        assert b"reference.yaml" not in r.content and b"truth" not in r.content.lower()


def records_by_commit(out: Path) -> dict[str, dict[str, Any]]:
    return {r["commit"]: r for r in json.loads((out / "results.json").read_text())["records"]}


def test_exhaustion_after_completed_runs_stops_cleanly_and_keeps_their_results(key_file, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """B-02 C1 needs exactly one request (an immediate answer), which uses the whole cap of 1. C2 never starts."""
    mock = Mock()
    out = tmp_path / "out"
    assert main(args(key_file[0], out, max_requests="1"), env={}, inner=mock.transport) == 1
    assert len(mock.requests) == 1  # nothing beyond the cap reached the network
    recs = records_by_commit(out)
    assert recs["C1"]["status"] == "completed" and "diagnosis" in recs["C1"]  # the completed run is kept as is
    assert recs["C2"] == {**recs["C2"], "status": "interrupted", "reason": INTERRUPTED_BEFORE}
    assert "diagnosis" not in recs["C2"] and "report" not in recs["C2"]
    results = json.loads((out / "results.json").read_text())
    assert results["interrupted"] == {"reason": "request_budget_exhausted", "runs": 1}
    assert results["provider"]["requests"] == {
        "max": 1,
        "sent": 1,
        "refused": 0,
        "refused_over_cap": 0,
        "refused_too_large": 0,
        "budget_exhausted": True,
    }
    assert results["run_id"] == results["config_id"] + "-interrupted"
    scores = json.loads((out / "scores.json").read_text())
    rows = {r["commit"]: r for r in scores["runs"]}
    assert rows["C2"]["outcome"] == "interrupted" and "points" not in rows["C2"]
    assert rows["C1"]["outcome"] != "interrupted"
    counts = scores["summary"]["counts"]
    assert (counts["interrupted"], counts["executed"], scores["summary"]["complete"]) == (1, 1, False)
    report = (out / "report.md").read_text()
    assert "INCOMPLETE: stopped by the request budget" in report and "not** full-evaluation results" in report


def test_exhaustion_during_a_run_discards_that_run_and_never_sends_past_the_cap(key_file, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The first answer is a tool call, so the investigation needs a second request; the cap of 1 refuses it."""
    mock = Mock(tool_first=True)
    out = tmp_path / "out"
    assert main(args(key_file[0], out, max_requests="1"), env={}, inner=mock.transport) == 1
    assert len(mock.requests) == 1  # the refused second request never reached the network
    recs = records_by_commit(out)
    assert recs["C1"]["status"] == "interrupted" and recs["C1"]["reason"] == INTERRUPTED_DURING
    assert set(recs["C1"]) <= {
        "case", "case_version", "track", "commit", "repetition", "provider", "source_type", "phase", "elapsed_ms",
        "status", "error_type", "reason",
    }  # fmt: skip  # no diagnosis, report or prepass survives, so nothing can score it
    assert recs["C2"]["status"] == "interrupted" and recs["C2"]["reason"] == INTERRUPTED_BEFORE
    results = json.loads((out / "results.json").read_text())
    assert results["provider"]["requests"]["refused_over_cap"] == 1 and results["interrupted"]["runs"] == 2
    scores = json.loads((out / "scores.json").read_text())
    assert [r["outcome"] for r in scores["runs"]] == ["interrupted", "interrupted"]
    s = scores["summary"]
    assert s["reliability"] == {} and s["abstentions_from_execution_failures"] == 0  # not a provider failure either
    assert s["track_b"]["points"] == 0 and s["track_b"]["max_points"] == 0.0  # no denominators from interrupted runs


class FakeBudget:
    def __init__(self, *, exhausted: bool) -> None:
        self._exhausted = exhausted

    def exhausted(self) -> bool:
        return self._exhausted

    def refusals(self) -> int:
        return 0

    def oversized(self) -> int:
        return 0


def test_exhaustion_before_any_run_interrupts_analysis_runs_but_not_the_pre_pass_only_track() -> None:
    results = run_suite(
        "scripted:oracle", make("oracle"), case_ids=["B-14", "A-04"], repetitions=1, budget=FakeBudget(exhausted=True)
    )
    status = {(r["case"], r["commit"]): r["status"] for r in results["records"]}
    assert status[("B-14", "C1")] == status[("B-14", "C2")] == "interrupted"
    assert all(v != "interrupted" for (case, _), v in status.items() if case == "A-04")  # Track A uses no provider
    assert results["interrupted"] == {"reason": "request_budget_exhausted", "runs": 2}


def test_an_interrupted_run_never_earns_an_abstention_score() -> None:
    """B-14 is unanswerable: an abstention there scores +2. Interrupted, it must score nothing."""
    results = run_suite("scripted:abstain", make("abstain"), case_ids=["B-14"], repetitions=1)
    clean = score_results(results)
    assert {r["outcome"] for r in clean["runs"]} == {"justified_abstention"}
    results["records"] = [{**r, "status": "interrupted", "reason": INTERRUPTED_DURING} for r in results["records"]]
    results["interrupted"] = {"reason": "request_budget_exhausted", "runs": 2}
    s = score_results(results)
    assert {r["outcome"] for r in s["runs"]} == {"interrupted"} and all("points" not in r for r in s["runs"])
    assert s["summary"]["track_b"]["abstention_recall"]["of"] == 0 and s["summary"]["complete"] is False
    assert "INCOMPLETE" in render_report(s)


def test_scripted_results_are_unchanged_by_the_budget_support() -> None:
    results = run_suite("scripted:oracle", make("oracle"), case_ids=["B-14"], repetitions=1)
    assert "interrupted" not in results  # no budget, no new field
    s = score_results(results)
    assert s["summary"]["counts"]["interrupted"] == 0 and s["summary"]["complete"] is True
    assert "INCOMPLETE" not in render_report(s) and "Protocol validation, not model accuracy" in render_report(s)


# ------------------------------------------------------------------ secret checks without provider internals


def test_secret_canary_detects_an_injected_key_and_never_shows_it() -> None:
    from pydantic import SecretStr

    key = "sk-synthetic-" + secrets.token_hex(16)
    c = SecretCanary(SecretStr(key))
    assert c.found_in("clean", f"prefix {key} suffix") and not c.found_in("clean", key[:-1])
    assert key not in repr(c) and key not in str(c) and not hasattr(c, "__dict__")
    with pytest.raises(ValueError):
        SecretCanary(SecretStr(""))


def test_cli_refuses_to_write_outputs_that_would_contain_the_key(key_file, tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    key = key_file[1]
    monkeypatch.setattr(cli, "render_report", lambda scores: render_report(scores) + f"\nleak {key}\n")
    out = tmp_path / "out"
    assert main(args(key_file[0], out), env={}, inner=Mock().transport) == 2
    assert not out.exists()  # nothing written
    captured = capsys.readouterr()
    assert "output would contain the key" in captured.err and key not in captured.err + captured.out


def test_the_cli_and_report_never_touch_provider_internals() -> None:
    from pathlib import Path as P

    bench = P(cli.__file__).parent
    for name in ("__main__.py", "report.py", "score.py", "harness.py", "model_provider.py"):
        text = (bench / name).read_text()
        assert "._key" not in text and "get_secret_value" not in text, name


# ------------------------------------------------------------------ C2: request-body cap at the transport boundary


def test_body_cap_boundary_and_the_over_cap_request_is_never_sent() -> None:
    mock = Mock()
    t = EndpointBudgetTransport(mock.transport, ENDPOINT, 10, max_request_bytes=100)
    with httpx.Client(transport=t) as c:
        c.post(ENDPOINT, content=b"x" * 100)  # exactly at the cap: sent
        with pytest.raises(RequestTooLarge) as ei:
            c.post(ENDPOINT, content=b"s" * 101)  # one byte over: refused
    assert len(mock.requests) == 1 and len(mock.requests[0].content) == 100
    assert (t.sent, t.oversize_refused, t.budget_refused, t.exhausted) == (1, 1, 0, False)  # not a budget event
    assert str(ei.value) == "request body exceeds the size cap" and "sss" not in str(ei.value)


def test_body_cap_applies_to_the_serialised_body_of_a_later_investigation_turn(key_file, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The second request of an investigation carries the tool result, so it is larger than the first. With the cap
    set to exactly the first request's size, the first is sent and the second is refused unsent; that run is an
    error row (never scored), and the evaluation goes on (this is not the request budget)."""
    probe = Mock(tool_first=True)
    assert main(args(key_file[0], tmp_path / "probe", "--case", "B-02"), env={}, inner=probe.transport) in (0, 1)
    first, second = len(probe.requests[0].content), len(probe.requests[1].content)
    assert second > first  # the serialised body grows with the conversation
    monkeypatch.setattr(model_provider, "MAX_REQUEST_BYTES", first)
    mock = Mock(tool_first=True)
    out = tmp_path / "out"
    assert main(args(key_file[0], out), env={}, inner=mock.transport) == 1
    assert len(mock.requests) >= 1 and all(len(r.content) <= first for r in mock.requests)
    results = json.loads((out / "results.json").read_text())
    c1 = records_by_commit(out)["C1"]
    assert (c1["status"], c1["error_type"]) == ("error", "RequestTooLarge") and "diagnosis" not in c1
    assert results["provider"]["requests"]["refused_too_large"] >= 1 and results["interrupted"] is None
    scores = json.loads((out / "scores.json").read_text())
    assert {r["commit"]: r["outcome"] for r in scores["runs"]}["C1"] == "error" and not scores["summary"]["complete"]


# ------------------------------------------------------------------ C1: a real wall-clock deadline per request


def test_each_request_gets_a_total_deadline_from_its_own_timeout() -> None:
    from tracewise.investigate.deadline_http import Deadline, DeadlineExceeded, RequestDeadlineTransport

    now = [100.0]
    seen: list[float | None] = []
    d = Deadline(lambda: now[0])

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(d.at)
        return httpx.Response(200, json={})

    t = RequestDeadlineTransport(httpx.MockTransport(handler), d)
    with httpx.Client(transport=t) as c:
        c.post(ENDPOINT, content=b"{}", timeout=httpx.Timeout(7.5, connect=2.0))
        now[0] = 200.0
        c.post(ENDPOINT, content=b"{}", timeout=httpx.Timeout(3.0, connect=1.0))
    assert seen == [107.5, 203.0]  # the longest of the request's own timeouts, from the moment it is sent
    unbounded = RequestDeadlineTransport(httpx.MockTransport(handler), d)
    with httpx.Client(transport=unbounded, timeout=None) as c, pytest.raises(DeadlineExceeded):  # noqa: S113 - deliberately unbounded: it must be refused
        c.post(ENDPOINT, content=b"{}")  # no timeout: never sent
    assert len(seen) == 2


def test_the_model_run_wires_the_deadline_backend_without_sending_anything(key_file) -> None:  # type: ignore[no-untyped-def]
    from tracewise.investigate.deadline_http import DeadlineBackend, DeadlineHTTPTransport, RequestDeadlineTransport

    run = build_model_run(model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={})
    try:
        timed = run.transport.inner
        assert isinstance(timed, RequestDeadlineTransport) and isinstance(timed.inner, DeadlineHTTPTransport)
        assert timed.inner.backend.deadline is timed.deadline and isinstance(timed.inner.backend, DeadlineBackend)
        assert run.transport.max_request_bytes == MAX_REQUEST_BYTES and run.transport.sent == 0
    finally:
        run.close()


def test_a_trickling_response_cannot_outlive_the_investigation_budget() -> None:
    """End to end through the product adapter on a loopback peer that trickles one byte every 50 ms: plain httpx
    would keep reading (each read succeeds well inside its timeout); the deadline stops the exchange at the
    investigation's remaining time. Loopback only; the real endpoint is never contacted."""
    import time

    from pydantic import SecretStr

    from tests.investigate.test_openai_smoke_hardening import Server
    from tracewise.investigate.deadline_http import Deadline, DeadlineHTTPTransport, RequestDeadlineTransport
    from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider
    from tracewise.investigate.openai_responses import OpenAIResponsesWire
    from tracewise.investigate.provider import ProviderError

    srv = Server("trickle")

    class Loopback(OpenAIResponsesWire):
        endpoint = f"http://127.0.0.1:{srv.port}/v1/responses"

    d = Deadline()
    client = httpx.Client(transport=RequestDeadlineTransport(DeadlineHTTPTransport(d), d), trust_env=False)
    p = HTTPProvider(
        Loopback(), SecretStr("synthetic-key-0000"), AdapterConfig("m-1", max_retries=0, allow_loopback_http=True), client=client
    )
    t0 = time.monotonic()
    try:
        with pytest.raises(ProviderError):
            p.step(StepRequest((Message("user", "hi"),), (), False, 1000, 0.5))  # 0.5 s left in the investigation
    finally:
        p.close()
        srv.close()
    assert time.monotonic() - t0 < 1.5 and d.expired  # ~0.5 s plus the watchdog interval, not unbounded


# ------------------------------------------------------------------ C3: complete and interrupted identities


def test_equivalent_complete_runs_share_one_id_and_an_interrupted_run_never_does(key_file, tmp_path) -> None:  # type: ignore[no-untyped-def]
    ids = []
    for name in ("a", "b"):
        assert main(args(key_file[0], tmp_path / name), env={}, inner=Mock().transport) in (0, 1)
        r = json.loads((tmp_path / name / "results.json").read_text())
        ids.append((r["run_id"], r["config_id"]))
    assert ids[0] == ids[1] and ids[0][0] == ids[0][1]  # reproducible, and complete runs use the configuration id
    assert main(args(key_file[0], tmp_path / "partial", max_requests="1"), env={}, inner=Mock().transport) == 1
    partial = json.loads((tmp_path / "partial" / "results.json").read_text())
    assert partial["config_id"] == ids[0][1]  # the same configuration (the cap is not part of it)...
    assert partial["run_id"] == ids[0][0] + "-interrupted" != ids[0][0]  # ...but never the same run identity


def test_re_scoring_an_interrupted_run_keeps_it_marked_incomplete(key_file, tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert main(args(key_file[0], tmp_path / "partial", max_requests="1"), env={}, inner=Mock().transport) == 1
    assert main(["score", str(tmp_path / "partial" / "results.json"), "--out", str(tmp_path / "rescored")]) == 0
    scores = json.loads((tmp_path / "rescored" / "scores.json").read_text())
    assert scores["run_id"].endswith("-interrupted") and scores["summary"]["complete"] is False
    report = (tmp_path / "rescored" / "report.md").read_text()
    assert report.splitlines()[0].endswith("(INCOMPLETE)") and "not a complete evaluation" in report


# ------------------------------------------------------------------ Stage 4A: output path, logging, transport edges


def test_an_unexpected_error_is_contained_without_a_traceback_or_any_output(key_file, tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    key = key_file[1]

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"internal failure mentioning {key}")  # worst case: a message carrying the key

    monkeypatch.setattr(cli, "run_suite", boom)
    out = tmp_path / "out"
    assert main(args(key_file[0], out), env={}, inner=Mock().transport) == 3
    captured = capsys.readouterr()
    assert "stopped unexpectedly (RuntimeError)" in captured.err and "Traceback" not in captured.err
    assert key not in captured.err + captured.out and not out.exists()


def test_the_written_artifacts_are_exactly_the_checked_bytes(key_file, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "out"
    assert main(args(key_file[0], out), env={}, inner=Mock().transport) in (0, 1)
    results = json.loads((out / "results.json").read_text())
    _scores, texts = cli._outputs(results)
    assert {p.name: p.read_text() for p in out.iterdir()} == texts  # what was checked is what was written
    assert capsys.readouterr().out.strip() == texts["report.md"].strip()


def test_entry_point_logging_scrubs_the_key_and_main_leaves_handlers_alone(key_file, capsys) -> None:  # type: ignore[no-untyped-def]
    import logging

    from tracewise.logging import secret_filter

    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    key = key_file[1]
    try:
        cli.configure_logging()
        secret_filter.register(key)  # as the adapter does when it is built
        logging.getLogger("tracewise.test").warning("diagnostic text %s", key)
        logging.getLogger("tracewise.test").info("below the level: not printed %s", key)
        err = capsys.readouterr().err
        assert "diagnostic text" in err and key not in err and "below the level" not in err
    finally:
        secret_filter.unregister(key)
        root.handlers[:] = saved
        root.setLevel(level)
    before = list(root.handlers)
    main(["verify"])
    assert list(root.handlers) == before  # main() itself never replaces a caller's handlers


def test_proxy_environment_variables_cannot_redirect_the_request(key_file, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import httpcore

    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    run = build_model_run(model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={})
    try:
        assert run.provider._client._mounts == {}  # no proxy mount on the client (trust_env=False)
        pool = run.transport.inner.inner._pool  # type: ignore[attr-defined]
        assert type(pool) is httpcore.ConnectionPool  # a direct pool, not an HTTP or SOCKS proxy pool
    finally:
        run.close()
    mock = Mock()
    run = build_model_run(model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={}, inner=mock.transport)
    try:
        run.provider.step(StepRequest((Message("user", "hello"),), (), False, 1000, 5.0))
    finally:
        run.close()
    assert [str(r.url) for r in mock.requests] == [ENDPOINT]


def test_a_redirect_is_never_followed(key_file) -> None:  # type: ignore[no-untyped-def]
    from tracewise.investigate.http_adapter import ProviderRequestError

    seen: list[str] = []

    def redirect(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(307, headers={"location": "https://evil.example/v1/responses"})

    run = build_model_run(
        model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={}, inner=httpx.MockTransport(redirect)
    )
    try:
        with pytest.raises(ProviderRequestError):
            run.provider.step(StepRequest((Message("user", "hello"),), (), False, 1000, 5.0))
    finally:
        run.close()
    assert seen == [ENDPOINT] and run.transport.sent == 1  # one request, never to the redirect target


def test_a_transport_error_carrying_the_key_never_exposes_it(key_file, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    from tracewise.investigate.provider import ProviderError

    key = key_file[1]

    def fail(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection to the endpoint failed; credential {key}")

    run = build_model_run(
        model="m-1", key_file=key_file[0], authorization_ref=REF, max_requests=5, env={}, inner=httpx.MockTransport(fail)
    )
    try:
        with pytest.raises(ProviderError) as ei:
            run.provider.step(StepRequest((Message("user", "hello"),), (), False, 1000, 5.0))
    finally:
        run.close()
    # No chain back to the original error: a traceback of this exception cannot print the original message.
    assert key not in str(ei.value) and ei.value.__cause__ is None and ei.value.__context__ is None
    out = tmp_path / "out"
    assert main(args(key_file[0], out), env={}, inner=httpx.MockTransport(fail)) in (0, 1)  # runs end provider_failed
    captured = capsys.readouterr()
    assert key not in outputs(out) + captured.out + captured.err
