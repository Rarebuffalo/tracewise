"""Phase 51: held-out checks for the A-04 primary-grouping change (BENCHMARK §8 requires held-out confirmation).

These logs were written for this file, modelled on the installers' documented output formats. They do not reuse
the benchmark case, its log or its truth file, and they are not part of the benchmark or its truth lock. They test
the underlying behaviour: one installer failure must be one primary, while genuinely independent failures must not
be collapsed into one.

Counterexamples the A-04 change does NOT handle are kept as strict xfails. They document the limitation and will
fail loudly (XPASS) if a later change fixes them, so the record cannot silently drift.
"""

from __future__ import annotations

import pytest

from tests.helpers import build_job
from tracewise.prepass.primary import run_prepass

PIP = "pip install -r requirements.txt"


def primaries(*jobs: tuple[str, str]) -> list[str]:
    built = [build_job(i + 1, f"job{i + 1}", "Install", cmd, out) for i, (cmd, out) in enumerate(jobs)]
    return [g.primary.message for g in run_prepass(built).primaries]


def log(*lines: str) -> str:
    return "\n".join(lines)


# ------------------------------------------------------------------ successes: one failure stays one primary


@pytest.mark.parametrize(
    "requirement",
    ["requests==99.0", "Django>=9.0,<10", "torch==3.0.0+cu999", "pkg-name_with.dots==1.2.3"],
    ids=["exact", "range", "local-version", "punctuated-name"],
)
def test_one_unresolvable_requirement_is_one_primary(requirement: str) -> None:
    out = log(
        f"Collecting {requirement.split('=')[0].split('>')[0]}",
        f"ERROR: Could not find a version that satisfies the requirement {requirement} (from versions: 0.1, 0.2)",
        f"ERROR: No matching distribution found for {requirement}",
    )
    got = primaries((PIP, out))
    assert len(got) == 1 and "Could not find a version" in got[0]


def test_pip_notice_line_between_the_two_messages_still_folds() -> None:
    out = log(
        "ERROR: Could not find a version that satisfies the requirement leftpadx==2.0 (from versions: none)",
        "[notice] A new release of pip is available: 23.0 -> 24.0",
        "ERROR: No matching distribution found for leftpadx==2.0",
    )
    assert len(primaries((PIP, out))) == 1


def test_the_follow_up_line_alone_is_still_reported() -> None:
    out = log("ERROR: No matching distribution found for onlyline==1.0")
    assert primaries((PIP, out)) == ["ERROR: No matching distribution found for onlyline==1.0"]


# ------------------------------------------------------------------ no over-collapse: independent causes stay apart


def test_different_requirements_are_not_folded() -> None:
    out = log(
        "ERROR: Could not find a version that satisfies the requirement alpha==1.0 (from versions: none)",
        "ERROR: No matching distribution found for beta==2.0",
    )
    assert len(primaries((PIP, out))) == 2


def test_same_name_but_different_specifier_is_not_folded() -> None:
    out = log(
        "ERROR: Could not find a version that satisfies the requirement gamma==1.0 (from versions: 0.9)",
        "ERROR: No matching distribution found for gamma==2.0",
    )
    assert len(primaries((PIP, out))) == 2


def test_independent_failures_in_two_jobs_stay_two_primaries() -> None:
    pip_out = log(
        "ERROR: Could not find a version that satisfies the requirement delta==9.9 (from versions: 1.0)",
        "ERROR: No matching distribution found for delta==9.9",
    )
    tsc_out = log("src/app.ts(3,7): error TS2322: Type 'string' is not assignable to type 'number'.")
    built = [build_job(1, "deps", "Install", PIP, pip_out), build_job(2, "types", "Typecheck", "npx tsc --noEmit", tsc_out)]
    groups = run_prepass(built).primaries
    assert [(g.primary.tool, g.primary.code) for g in groups] == [("installer", "install"), ("tsc", "TS2322")]


def test_a_far_away_follow_up_is_not_folded_into_an_unrelated_lead() -> None:
    out = log(
        "ERROR: Could not find a version that satisfies the requirement eps==1.0 (from versions: none)",
        *[f"  build output line {i}" for i in range(10)],
        "ERROR: No matching distribution found for eps==1.0",
    )
    assert len(primaries((PIP, out))) == 2  # only an immediate follow-up (≤2 lines) is treated as the same failure


def test_install_failure_then_missing_module_cascade_still_one_root() -> None:
    out = log(
        "ERROR: Could not find a version that satisfies the requirement zeta==5.0 (from versions: 4.0)",
        "ERROR: No matching distribution found for zeta==5.0",
        "Traceback (most recent call last):",
        '  File "/home/runner/work/r/r/main.py", line 2, in <module>',
        "ModuleNotFoundError: No module named 'zeta'",
    )
    res = run_prepass([build_job(1, "t", "Install and run", PIP + " && python main.py", out)])
    assert len(res.primaries) == 1 and [c.module for c in res.cascades] == ["zeta"]


# ------------------------------------------------------------------ counterexamples (not handled by the A-04 change)


@pytest.mark.xfail(strict=True, reason="npm prints `code ERESOLVE` and an ERESOLVE summary line: two primaries today")
def test_npm_eresolve_block_is_one_primary() -> None:
    out = log(
        "npm error code ERESOLVE",
        "npm error ERESOLVE unable to resolve dependency tree",
        "npm error While resolving: app@1.0.0",
    )
    assert len(primaries(("npm ci", out))) == 1


@pytest.mark.xfail(strict=True, reason="pip ResolutionImpossible prints its own pair of lines; not folded by A-04")
def test_pip_resolution_impossible_pair_is_one_primary() -> None:
    out = log(
        "ERROR: Cannot install theta==1.0 and iota==2.0 because these package versions have conflicting dependencies.",
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/",
    )
    assert len(primaries((PIP, out))) == 1


def test_uv_resolution_failure_is_not_recognised_as_an_installer_error() -> None:
    """Recorded, not asserted as desired: uv's "No solution found" block yields no installer candidate."""
    out = log("  × No solution found when resolving dependencies:", "  ╰─▶ Because kappa==9 was not found, …")
    assert all("install" not in m.lower() for m in primaries(("uv sync", out)))
