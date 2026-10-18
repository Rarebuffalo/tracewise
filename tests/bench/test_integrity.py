"""T-602 ground-truth integrity: every required case exists, is valid, resolves against its fixture, and
is locked. These tests never run a provider."""

from __future__ import annotations

import shutil

import pytest

from tracewise.bench import harness
from tracewise.bench.generate import generate
from tracewise.bench.integrity import check_all, check_case
from tracewise.bench.model import CASES_DIR, REQUIRED_CASES, load_case


def test_no_integrity_problems() -> None:
    assert check_all() == []


def test_required_cases_exactly_present_and_loadable() -> None:
    assert len(REQUIRED_CASES) == 26
    present = sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())
    assert present == sorted(REQUIRED_CASES)
    for cid in REQUIRED_CASES:
        spec, truth, _ = load_case(cid)
        assert spec.id == truth.case == cid


def test_p2_cases_are_explicit_not_silent() -> None:
    for cid in ("B-15", "B-16"):
        spec, truth, _ = load_case(cid)
        assert spec.phase == truth.phase == "p2" and spec.p2_reason and "P2" in spec.p2_reason


def test_truth_lock_detects_changes(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    copy = tmp_path / "cases"
    shutil.copytree(CASES_DIR, copy)
    monkeypatch.setattr(harness, "CASES_DIR", copy)
    monkeypatch.setattr(harness, "LOCK_FILE", copy / "TRUTH.lock")
    assert harness.verify_lock() == []
    t = copy / "B-02" / "truth.yaml"
    t.write_text(t.read_text().replace("line: 41", "line: 40", 1))
    assert harness.verify_lock() == ["B-02: truth.yaml changed since it was locked"]


def test_integrity_catches_bad_evidence_and_locations(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tracewise.bench import fixture, integrity, model

    copy = tmp_path / "cases"
    shutil.copytree(CASES_DIR, copy)
    for mod in (model, integrity):
        monkeypatch.setattr(mod, "CASES_DIR", copy, raising=False)
    monkeypatch.setattr(model, "case_dir", lambda cid: copy / cid)
    monkeypatch.setattr(integrity, "case_dir", lambda cid: copy / cid)
    monkeypatch.setattr(fixture, "case_dir", lambda cid: copy / cid)
    monkeypatch.setattr(harness, "case_dir", lambda cid: copy / cid)
    import yaml

    t = copy / "B-07" / "truth.yaml"
    doc = yaml.safe_load(t.read_text())
    doc["runs"]["C1"]["evidence"][0]["contains"] = "KeyError: 'NOT_IN_LOG'"
    doc["runs"]["C1"]["location"][0]["line"] = 500
    t.write_text(yaml.safe_dump(doc, sort_keys=False))
    problems = check_case("B-07")
    assert any("not in the log" in p for p in problems) and any("beyond EOF" in p for p in problems)


@pytest.mark.slow
def test_logs_regenerate_identically_from_real_tool_runs() -> None:
    """T-601: committed logs are reproducible from the local tools (pytest, ruff, mypy, tsc)."""
    assert [d for cid in REQUIRED_CASES for d in generate(cid, check=True)] == []
