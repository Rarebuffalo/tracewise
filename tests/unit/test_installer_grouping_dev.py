"""Phase 52 DEVELOPMENT set for installer-failure grouping (the implementation was built against these cases).

The separate, frozen evaluation set is tests/unit/test_installer_eval_phase52.py. The Phase 51 held-out file
(test_prepass_heldout.py) found the npm and pip ResolutionImpossible counterexamples, so it informed this work and
is no longer independent evidence for it.

Contract: one installer failure report is one primary (the report's first error line, spanning its continuation
lines). Independent failures, and blocks separated by other output, stay separate. Warnings, progress and success
lines are not failures.
"""

from __future__ import annotations

from tests.helpers import build_job
from tracewise.prepass.primary import run_prepass


def prepass(*jobs: tuple[str, str]):  # type: ignore[no-untyped-def]
    return run_prepass([build_job(i + 1, f"d{i + 1}", "Deps", cmd, out) for i, (cmd, out) in enumerate(jobs)])


def L(*lines: str) -> str:
    return "\n".join(lines)


def no_error_primary(res) -> bool:  # type: ignore[no-untyped-def]
    """Only the runner's `exit code N` fallback may remain: not an error line, so the outcome stays inconclusive."""
    return all(g.primary.kind == "exit" for g in res.primaries)


# ------------------------------------------------------------------ npm blocks


def test_npm_eresolve_block_new_prefix_is_one_primary_spanning_the_block() -> None:
    out = L(
        "npm error code ERESOLVE",
        "npm error ERESOLVE unable to resolve dependency tree",
        "npm error",
        "npm error While resolving: dash@0.1.0",
        "npm error Found: vue@2.7.0",
    )
    res = prepass(("npm install", out))
    (g,) = res.primaries
    assert g.primary.message == "npm error code ERESOLVE" and g.primary.span[1] - g.primary.span[0] == 4


def test_npm_old_prefix_etarget_block_is_one_primary() -> None:
    out = L("npm ERR! code ETARGET", "npm ERR! notarget No matching version found for is-odd@42.0.0.", "npm ERR! notarget")
    assert len(prepass(("npm ci", out)).primaries) == 1


def test_two_npm_blocks_separated_by_other_output_stay_two() -> None:
    out = L(
        "npm error code E404",
        "npm error 404 Not Found - GET https://registry.npmjs.org/ghost-pkg",
        "> running second install",
        "npm error code ETARGET",
        "npm error notarget No matching version found for real-pkg@9.9.9.",
    )
    assert len(prepass(("npm i ghost-pkg; npm i real-pkg@9.9.9", out)).primaries) == 2


def test_npm_warnings_and_summary_are_not_failures() -> None:
    out = L(
        "npm warn deprecated inflight@1.0.6: not supported", "npm warn ERESOLVE overriding peer dependency", "up to date in 2s"
    )
    assert no_error_primary(prepass(("npm ci", out)))


# ------------------------------------------------------------------ pip conflict reports


def test_pip_conflict_and_resolution_impossible_are_one_primary() -> None:
    out = L(
        "ERROR: Cannot install alpha==2.0 and beta==3.0 because these package versions have conflicting dependencies.",
        "The conflict is caused by:",
        "    alpha 2.0 depends on gamma<1",
        "    beta 3.0 depends on gamma>=1",
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/",
    )
    (g,) = prepass(("pip install alpha==2.0 beta==3.0", out)).primaries
    assert g.primary.message.startswith("ERROR: Cannot install alpha==2.0") and g.primary.span[1] > g.primary.span[0]


def test_resolution_impossible_far_from_any_conflict_is_reported_on_its_own() -> None:
    out = L(*[f"Collecting dep{i}" for i in range(20)], "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/")
    (g,) = prepass(("pip install -r r.txt", out)).primaries
    assert "ResolutionImpossible" in g.primary.message


def test_a_resolution_impossible_line_is_not_folded_into_an_unrelated_pip_error() -> None:
    out = L(
        "ERROR: No matching distribution found for delta==4.0",
        *[f"    log line {i}" for i in range(30)],
        "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/",
    )
    assert len(prepass(("pip install", out)).primaries) == 2


# ------------------------------------------------------------------ uv


def test_uv_cross_marked_no_solution_is_an_installer_primary() -> None:
    out = L("  × No solution found when resolving dependencies:", "  ╰─▶ Because zed>=5 is unavailable, …")
    (g,) = prepass(("uv lock", out)).primaries
    assert g.primary.kind == "install" and "No solution found" in g.primary.message


def test_uv_error_prefixed_no_solution_is_an_installer_primary() -> None:
    out = L("error: No solution found when resolving dependencies:", "  Because omega was not found in the package registry …")
    (g,) = prepass(("uv pip install omega", out)).primaries
    assert g.primary.kind == "install"


def test_uv_resolved_and_installed_lines_are_not_failures() -> None:
    assert no_error_primary(prepass(("uv sync", L("Resolved 3 packages in 9ms", "Audited 3 packages in 1ms"))))


# ------------------------------------------------------------------ independence and cascades


def test_installer_failure_still_makes_a_later_missing_module_a_cascade() -> None:
    out = L(
        "  × No solution found when resolving dependencies:",
        "  ╰─▶ Because sigma==2 was not found …",
        "Traceback (most recent call last):",
        '  File "/home/runner/work/x/x/run.py", line 1, in <module>',
        "ModuleNotFoundError: No module named 'sigma'",
    )
    res = prepass(("uv sync && python run.py", out))
    assert len(res.primaries) == 1 and [c.module for c in res.cascades] == ["sigma"]


def test_npm_and_uv_failures_in_two_jobs_stay_two() -> None:
    npm = L("npm error code E404", "npm error 404 Not Found - GET https://registry.npmjs.org/nope")
    uv = L("  × No solution found when resolving dependencies:")
    assert len(prepass(("npm ci", npm), ("uv sync", uv)).primaries) == 2
