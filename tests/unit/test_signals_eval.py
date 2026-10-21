"""The offline P2 signal evaluation reads the frozen benchmark and changes nothing (truth, lock, files)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tracewise.bench import signals
from tracewise.bench.model import case_dir

CASES = case_dir("B-05").parent


def tree_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(CASES.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(CASES).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def test_evaluation_is_read_only_deterministic_and_splits_development_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = tree_hash()
    a, b = signals.report(), signals.report()
    assert a == b and tree_hash() == before
    dev = {r["case"] for r in a["runs"] if r["split"] == "development"}
    assert dev == {"B-05", "B-06"}
    assert a["separate_from_benchmark_scores"] is True
    from tracewise.bench.__main__ import main

    out = tmp_path / "signals.json"
    assert main(["signals", "--out", str(out)]) == 0 and json.loads(out.read_text())["unseen"] == a["unseen"]
    assert tree_hash() == before


def test_the_recorded_result_on_the_frozen_cases() -> None:
    """Pins the 2026-10-22 result (docs/benchmark-runs/2026-10-22-signals-dependency-drift.md); a change to the signal
    must update that record deliberately."""
    d = signals.report()
    assert d["development"]["true_positive"] == 1 and d["development"]["flagged_uncorroborated_on_dependency"] == 3
    u = d["unseen"]
    assert (u["true_positive"], u["false_positive"], u["false_negative"], u["true_negative"]) == (0, 0, 2, 28)
    assert u["flagged_uncorroborated_on_other"] == 0 and u["skipped"] == 1 and u["excluded_unlabelled"] == 9


def test_trigger_diff_matches_the_snapshots() -> None:
    from tracewise.bench.model import load_case

    spec, _, _ = load_case("B-06")
    d = signals.trigger_diff(spec, "C1")
    assert [f.path for f in d.files] == ["requirements.txt"] and d.files[0].patch and "+bar==2.0" in d.files[0].patch
