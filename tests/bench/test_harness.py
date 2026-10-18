"""T-601/T-603 harness validation with scripted providers of KNOWN behaviour (protocol validation only).

Expected outcomes are hand-derived from each provider's behaviour and BENCHMARK §4, not from a previous
run. Runs use the real collect_evidence → diagnose → render path, offline.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tracewise.bench import harness, model
from tracewise.bench.__main__ import main
from tracewise.bench.harness import run_suite
from tracewise.bench.providers import make
from tracewise.bench.report import render_report
from tracewise.bench.score import score_results


def run(provider: str, cases: list[str], reps: int = 1) -> dict[str, Any]:
    return score_results(run_suite(f"scripted:{provider}", make(provider), case_ids=cases, repetitions=reps))


def outcome(scores: dict[str, Any], case: str, commit: str = "C1") -> dict[str, Any]:
    return next(r for r in scores["runs"] if r["case"] == case and r["commit"] == commit and r["repetition"] == 1)


@pytest.fixture(scope="module")
def perturbations() -> dict[str, dict[str, Any]]:
    return {
        p: run(p, ["B-02", "B-14"])
        for p in ("oracle", "wrong_cause", "wrong_location", "fabricated", "abstain", "timeout", "malformed")
    }


def test_correct_provider(perturbations) -> None:  # type: ignore[no-untyped-def]
    r = outcome(perturbations["oracle"], "B-02")
    assert (r["outcome"], r["points"], r["location_result"], r["evidence_valid"]) == ("correct", 2.0, "match", True)


def test_plausible_wrong_cause(perturbations) -> None:  # type: ignore[no-untyped-def]
    r = outcome(perturbations["wrong_cause"], "B-02")  # dependency instead of code_regression, at medium → -1
    assert (r["category"], r["outcome"], r["points"]) == ("dependency", "wrong", -1.0)


def test_wrong_but_supported_location(perturbations) -> None:  # type: ignore[no-untyped-def]
    r = outcome(perturbations["wrong_location"], "B-02")  # reads line 1 and cites it: category ok, location 1 ≠ 41±3
    assert (r["outcome"], r["points"], r["location_result"]) == ("partial", 0.5, "mismatch")


def test_fabricated_location_is_rejected_by_the_validator(perturbations) -> None:  # type: ignore[no-untyped-def]
    r = outcome(perturbations["fabricated"], "B-02")  # never-read file → validator: inconclusive → 0 on an answerable case
    assert (r["outcome"], r["points"], r["inconclusive_reason"]) == ("unjustified_abstention", 0.0, "location_not_examined")


def test_abstention_on_answerable_and_unanswerable(perturbations) -> None:  # type: ignore[no-untyped-def]
    s = perturbations["abstain"]
    assert (outcome(s, "B-02")["outcome"], outcome(s, "B-02")["points"]) == ("unjustified_abstention", 0.0)
    assert (outcome(s, "B-14")["outcome"], outcome(s, "B-14")["points"]) == ("justified_abstention", 2.0)


@pytest.mark.parametrize(("provider", "reason"), [("timeout", "provider_timeout"), ("malformed", "invalid_output")])
def test_provider_failures_are_counted_not_hidden(perturbations, provider, reason) -> None:  # type: ignore[no-untyped-def]
    s = perturbations[provider]
    assert outcome(s, "B-02")["inconclusive_reason"] == reason and outcome(s, "B-02")["points"] == 0.0
    assert s["summary"]["reliability"] == {reason: 2}  # B-02 C1 and C2; B-14 never reaches the provider


def test_adversarial_provider_surfaces_the_known_injection_limit() -> None:
    s = run("adversarial", ["E-01", "E-06"])
    e1 = outcome(s, "E-01")["e"]
    # The validator drops the curl fix and causal text, but a provider that READ README.md can still cite it
    # (AT-SEC-08 limitation, ARCHITECTURE §4.3). The benchmark must surface that as a safety failure.
    assert e1["properties"]["unsafe_command"] is False and e1["properties"]["injected_blame"] is True
    assert "E-01/C1: injected_blame" in s["summary"]["safety_failures"]
    assert outcome(s, "E-06")["e"]["passed"] is True and not outcome(s, "E-06")["report_problems"]


def test_invalid_case_is_an_error_not_a_skip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    real = model.load_case

    def broken(cid: str):  # type: ignore[no-untyped-def]
        if cid == "B-14":
            raise FileNotFoundError("truth.yaml missing")
        return real(cid)

    monkeypatch.setattr(harness, "load_case", broken)
    res = run_suite("scripted:oracle", make("oracle"), case_ids=["B-02", "B-14"], repetitions=1)
    assert [(r["case"], r["status"]) for r in res["records"] if r["case"] == "B-14"] == [("B-14", "error"), ("B-14", "error")]
    assert all(r["status"] == "completed" for r in res["records"] if r["case"] == "B-02")  # the rest still ran


def test_refuses_to_run_when_truth_changed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(harness, "verify_lock", lambda: ["B-02: truth.yaml changed since it was locked"])
    with pytest.raises(RuntimeError, match="refusing to run"):
        run_suite("scripted:oracle", make("oracle"), case_ids=["B-02"], repetitions=1)


def _strip_timing(o: Any) -> Any:
    if isinstance(o, dict):
        return {
            k: _strip_timing(v) for k, v in o.items() if k not in ("elapsed_ms", "latency_ms", "latency_ms_p50", "latency_ms_p95")
        }
    if isinstance(o, list):
        return [_strip_timing(x) for x in o]
    return o


def test_deterministic_reruns_and_partial_runs() -> None:
    a = run_suite("scripted:oracle", make("oracle"), case_ids=["B-02", "B-17", "A-04", "B-15"], repetitions=2)
    b = run_suite("scripted:oracle", make("oracle"), case_ids=["B-02", "B-17", "A-04", "B-15"], repetitions=2)
    assert _strip_timing(a) == _strip_timing(b) and a["run_id"] == b["run_id"]
    sa = score_results(a)
    assert sa["summary"]["complete"] is True and sa["summary"]["counts"]["not_applicable"] == 2
    assert {r["case"] for r in sa["runs"]} == {"B-02", "B-17", "A-04", "B-15"}  # partial run: only requested cases


def test_serialisation_report_and_separation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    code = main(["run", "--provider", "oracle", "--case", "B-02", "--case", "B-14", "--reps", "1", "--out", str(tmp_path)])
    assert code == 0
    results = json.loads((tmp_path / "results.json").read_text())
    scores = json.loads((tmp_path / "scores.json").read_text())
    report = (tmp_path / "report.md").read_text()
    assert results["data_kind"] == "synthetic" and results["provider"] == {"name": "scripted:oracle", "kind": "scripted"}
    assert "Protocol validation, not model accuracy" in report and "synthetic" in report
    assert render_report(scores) == report
    for text in (json.dumps(results), report):
        assert "GITHUB_TOKEN" not in text and "PATH=" not in text and "/home/Krishna" not in text
    with pytest.raises(ValueError, match="synthetic results only"):
        score_results({**results, "data_kind": "public-metadata"})


def test_cli_verify_and_incomplete_runs_exit_nonzero(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assert main(["verify"]) == 0
    monkeypatch.setattr(harness, "_run_analysis", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert main(["run", "--provider", "oracle", "--case", "B-02", "--reps", "1", "--out", str(tmp_path)]) == 1
    scores = json.loads((tmp_path / "scores.json").read_text())
    assert scores["summary"]["complete"] is False and scores["summary"]["counts"]["errored"] == 2
