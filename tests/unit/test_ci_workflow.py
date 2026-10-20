"""Phase 51: the CI workflow is an offline quality gate and nothing more. Parsed locally; never executed here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "ci.yml"


def workflow() -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load(WF.read_text())
    return doc


def run_lines() -> str:
    return "\n".join(s.get("run", "") for s in workflow()["jobs"]["check"]["steps"])


def test_ci_is_read_only_and_uses_no_secrets_or_deployments() -> None:
    text = WF.read_text()
    assert workflow()["permissions"] == {"contents": "read"}
    assert "secrets." not in text and "environment:" not in text and "deploy" not in text.lower().replace("deployment,", "")
    assert all(
        s.get("with", {}).get("persist-credentials", False) is False
        for s in workflow()["jobs"]["check"]["steps"]
        if str(s.get("uses", "")).startswith("actions/checkout")
    )


def test_ci_runs_every_offline_gate() -> None:
    runs = run_lines()
    for gate in ("make lint", "make type", "make docs", "tracewise.bench verify", "-p tests.netguard", '-m "not live"'):
        assert gate in runs, gate
    assert "uv sync --locked" in runs  # the lock file, never a fresh resolution


def test_ci_cannot_pass_by_skipping_the_database_tests() -> None:
    runs = run_lines()
    assert "initdb" in runs and "skipped" in runs and "exit 1" in runs


def test_ci_never_runs_live_tests_or_the_model_smoke_harness() -> None:
    runs = run_lines()
    assert "-m live" not in runs and "openai_smoke" not in WF.read_text() and "OPENAI" not in WF.read_text()


def test_make_ci_reproduces_the_workflow_test_gate() -> None:
    """`make ci` must run the same pytest arguments, the same skip rule and the same gates as the workflow."""
    make = (ROOT / "Makefile").read_text()
    target = make.split("\nci:", 1)[1]
    pytest_line = next(line for line in run_lines().splitlines() if "uv run pytest" in line)
    args = pytest_line.split("uv run pytest", 1)[1].split("|", 1)[0].strip()
    assert args in target
    for gate in (
        "lint",
        "type",
        "docs",
        "tracewise.bench verify",
        "skipped",
        "set -eo pipefail",
    ):  # errexit: a failure is never masked
        assert gate in target, gate
