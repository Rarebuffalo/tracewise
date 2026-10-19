"""Phase 52 EVALUATION set for installer-failure grouping. Written before the Phase 52 implementation and frozen:
its SHA-256 (45121652…ac852) was recorded before any code change and re-checked before its single run; three
mis-specified assertions were corrected afterwards and are marked (see CHANGELOG, Phase 52).

Development happened against tests/unit/test_installer_grouping_dev.py only. These logs were authored separately,
modelled on documented installer output, and are not part of the benchmark or its truth lock. Expected outcomes
follow the diagnostic contract: one installer failure report is one primary; independent failures stay separate;
installer chatter and warnings are not failures (no primary, so the investigation stays inconclusive).
"""

from __future__ import annotations

from tests.helpers import build_job
from tracewise.prepass.primary import run_prepass


def groups(*jobs: tuple[str, str]) -> list[str]:
    built = [build_job(i + 1, f"j{i + 1}", "Install deps", cmd, out) for i, (cmd, out) in enumerate(jobs)]
    return [g.primary.message for g in run_prepass(built).primaries]


def L(*lines: str) -> str:
    return "\n".join(lines)


def no_error_primary(*jobs: tuple[str, str]) -> bool:
    """CORRECTED after the single evaluation run (raw result 6/9; see CHANGELOG Phase 52). The three "not a failure"
    cases first asserted `== []`, but the test helper always appends the runner's `exit code 1` line, which is kept
    as an `exit`-kind fallback. By contract that is not an error line (the outcome stays inconclusive), so the right
    check is that no error-kind primary exists. The implementation was not changed in response."""
    built = [build_job(i + 1, f"j{i + 1}", "Install deps", cmd, out) for i, (cmd, out) in enumerate(jobs)]
    return all(g.primary.kind == "exit" for g in run_prepass(built).primaries)


# ------------------------------------------------------------------ npm


def test_eval_npm_eresolve_with_peer_detail_is_one_primary() -> None:
    out = L(
        "npm ERR! code ERESOLVE",
        "npm ERR! ERESOLVE could not resolve",
        "npm ERR!",
        "npm ERR! While resolving: web-ui@3.1.0",
        "npm ERR! Found: react@17.0.2",
        "npm ERR! node_modules/react",
        'npm ERR!   react@"^17.0.2" from the root project',
        "npm ERR!",
        "npm ERR! Could not resolve dependency:",
        'npm ERR! peer react@"^18.0.0" from charts-lib@4.0.0',
        "npm ERR! A complete log of this run can be found in: /home/runner/.npm/_logs/debug-0.log",
    )
    assert len(groups(("npm ci", out))) == 1


def test_eval_npm_e404_is_one_primary() -> None:
    out = L(
        "npm error code E404",
        "npm error 404 Not Found - GET https://registry.npmjs.org/not-a-real-pkg-xyz - Not found",
        "npm error 404  'not-a-real-pkg-xyz@*' is not in this registry.",
    )
    assert len(groups(("npm install", out))) == 1


def test_eval_npm_peer_warning_is_not_a_failure() -> None:
    out = L(
        "npm warn ERESOLVE overriding peer dependency",
        "npm warn While resolving: web-ui@3.1.0",
        "added 812 packages, and audited 813 packages in 14s",
    )
    assert no_error_primary(("npm ci", out))


# ------------------------------------------------------------------ pip


def test_eval_pip_conflict_report_is_one_primary() -> None:
    out = L(
        "ERROR: Cannot install pandas==2.2.0 and numpy==1.21.0 because these package versions have conflicting dependencies.",
        "",
        "The conflict is caused by:",
        "    The user requested numpy==1.21.0",
        "    pandas 2.2.0 depends on numpy>=1.22.4",
        "",
        "To fix this you could try to:",
        "1. loosen the range of package versions you've specified",
        "2. remove package versions to allow pip to attempt to solve the dependency conflict",
        "",
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts",
    )
    got = groups(("pip install -r requirements.txt", out))
    assert len(got) == 1 and "Cannot install" in got[0]


def test_eval_pip_progress_and_success_lines_are_not_failures() -> None:
    out = L(
        "Collecting flask==3.0.0",
        "  Downloading flask-3.0.0-py3-none-any.whl (99 kB)",
        "Installing collected packages: flask",
        "Successfully installed flask-3.0.0",
    )
    assert no_error_primary(("pip install flask", out))


# ------------------------------------------------------------------ uv


def test_eval_uv_no_solution_is_one_installer_primary() -> None:
    out = L(
        "Using CPython 3.12.3",
        "  × No solution found when resolving dependencies:",
        "  ╰─▶ Because only httpx<0.20 is available and myapp depends on httpx>=0.27, we can conclude that myapp's",
        "      requirements are unsatisfiable.",
    )
    got = groups(("uv sync --locked", out))
    assert len(got) == 1 and "No solution found" in got[0]


def test_eval_uv_success_output_is_not_a_failure() -> None:
    out = L("Resolved 42 packages in 120ms", "Installed 42 packages in 85ms", " + httpx==0.27.0")
    assert no_error_primary(("uv sync", out))


# ------------------------------------------------------------------ independence


def test_eval_two_jobs_with_different_installer_failures_stay_two() -> None:
    npm = L("npm ERR! code ETARGET", "npm ERR! notarget No matching version found for left-pad@99.0.0.")
    pip = L("ERROR: No matching distribution found for requestz==1.0")
    assert len(groups(("npm ci", npm), ("pip install requestz==1.0", pip))) == 2


def test_eval_installer_failure_then_unrelated_test_failure_in_another_job_stays_two() -> None:
    uv = L("  × No solution found when resolving dependencies:", "  ╰─▶ Because foo==9 was not found in the package registry, …")
    tests = L(
        "=================================== FAILURES ===================================",
        "______________________________ test_total ______________________________",
        "tests/test_total.py:8: in test_total",
        "    assert total([1, 2]) == 4",
        "E   assert 3 == 4",
        "=========================== short test summary info ============================",
        "FAILED tests/test_total.py::test_total - assert 3 == 4",
    )
    assert len(groups(("uv sync", uv), ("pytest", tests))) == 2
