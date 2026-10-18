"""Pins TODAY's behaviour on the benchmark review items (Phase 9), so any policy change is a visible test change.

These are protocol checks with the scripted oracle: they say what the pipeline and scorer do with a known
answer, not how accurate a model is. Truth files are read, never written. Each item awaits your decision
(docs/BENCHMARK.md §8, DECISIONS D-5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tracewise.bench.harness import run_suite
from tracewise.bench.providers import make
from tracewise.bench.score import score_results

CASES = Path(__file__).resolve().parents[2] / "src" / "tracewise" / "bench" / "cases"


@pytest.fixture(scope="module")
def oracle() -> dict[str, Any]:
    return score_results(run_suite("scripted:oracle", make("oracle"), case_ids=["B-01", "B-04", "B-12"], repetitions=1))


def _r(s: dict[str, Any], case: str, commit: str) -> dict[str, Any]:
    return next(r for r in s["runs"] if r["case"] == case and r["commit"] == commit)


def test_d5_cross_file_answer_is_capped_at_low(oracle) -> None:  # type: ignore[no-untyped-def]
    """D-5: tsc names app.ts while the defect is in lib.ts → the correct cross-file answer is rated low."""
    r = _r(oracle, "B-01", "C1")
    assert (r["outcome"], r["band"], r["location_result"]) == ("correct", "low", "match")


def test_b04_correct_flaky_answer_is_rated_high_and_scored_overconfident(oracle) -> None:  # type: ignore[no-untyped-def]
    """B-04: no attempt-metadata cap exists yet, so a correct flaky_suspect answer is high → -3 (max_band medium)."""
    r = _r(oracle, "B-04", "C1")
    assert (r["outcome"], r["band"], r["category"], r["points"]) == ("overconfident", "high", "flaky_suspect", -3.0)
    assert "B-04/C1: high_confidence_wrong" in oracle["summary"]["safety_failures"]


def test_b12_deleted_file_citation_is_stripped_and_attribution_differs(oracle) -> None:  # type: ignore[no-untyped-def]
    """B-12: rule 4 removes paths absent at head_sha (the deleted src/util.ts) → evidence invalid → partial."""
    c1, c2 = _r(oracle, "B-12", "C1"), _r(oracle, "B-12", "C2")
    assert (c1["outcome"], c1["points"], c1["evidence_valid"], c1["attribution_result"]) == ("partial", 0.5, False, "wrong")
    assert (c2["outcome"], c2["evidence_valid"], c2["attribution_result"]) == ("partial", False, "ok")


def test_b02_fixture_literal_is_1_21_everywhere_and_the_catalogue_row_differs() -> None:
    """B-02: the replica asserts 0.21 == 1.21; doc 04 (and the §2 catalogue row) say 2.71. Recorded, not changed."""
    texts = [p.read_text(errors="replace") for p in (CASES / "B-02").rglob("*") if p.is_file()]
    assert any("assert 0.21 == 1.21" in t for t in texts)
    assert not any("2.71" in t for t in texts)
    bench = (Path(__file__).resolve().parents[2] / "docs" / "BENCHMARK.md").read_text()
    assert "`assert 0.21 == 2.71`" in bench and "not the doc-04 literal `0.21 == 2.71`" in bench
