"""Held-out pre-pass checks for two failure shapes the benchmark has no case for: a container image build that
fails inside a RUN step, and a registry or Git authentication refusal. The logs were written for this file, modelled
on the tools' documented output. They are not benchmark cases or truth (TRUTH.lock is untouched), and they check only
deterministic facts: the pre-pass anchors on the line that states the failure, and never on runner noise. Whether a
model then names the right cause is a real-model evaluation question, not tested here."""

from __future__ import annotations

import pytest

from tests.helpers import build_job
from tracewise.prepass.primary import run_prepass


def primaries(cmd: str, out: str) -> list[str]:
    return [g.primary.message for g in run_prepass([build_job(1, "build", "Build", cmd, out)]).primaries]


DOCKER = "\n".join(
    [
        "#8 [build 4/6] RUN npm ci",
        "#8 1.204 npm ERR! code ERESOLVE",
        "#8 1.205 npm ERR! ERESOLVE unable to resolve dependency tree",
        "#8 1.206 npm ERR! Found: react@18.2.0",
        '#8 ERROR: process "/bin/sh -c npm ci" did not complete successfully: exit code: 1',
        'ERROR: failed to solve: process "/bin/sh -c npm ci" did not complete successfully: exit code: 1',
        "##[error]Process completed with exit code 1.",
    ]
)

REGISTRY = "\n".join(
    [
        "The push refers to repository [ghcr.io/acme/app]",
        "5f70bf18a086: Preparing",
        "denied: permission_denied: write_package",
        "##[error]Process completed with exit code 1.",
    ]
)

GIT_AUTH = "\n".join(
    [
        "remote: Permission to acme/app.git denied to github-actions[bot].",
        "fatal: unable to access 'https://github.com/acme/app/': The requested URL returned error: 403",
        "##[error]Process completed with exit code 128.",
    ]
)


def test_a_container_build_failure_is_anchored_on_the_failing_step_not_the_runner_exit() -> None:
    got = primaries("docker build .", DOCKER)
    assert got and not any("Process completed with exit code" in m for m in got)
    assert any("ERESOLVE" in m or "failed to solve" in m or "did not complete successfully" in m for m in got)


def test_a_registry_refusal_is_reported_as_the_failure_line() -> None:
    got = primaries("docker push ghcr.io/acme/app", REGISTRY)
    assert any("denied" in m for m in got) and not any("Process completed with exit code" in m for m in got)


def test_a_git_permission_refusal_is_reported_as_the_failure_line() -> None:
    got = primaries("git push origin main", GIT_AUTH)
    assert any("Permission to" in m or "403" in m for m in got)
    assert not any("Process completed with exit code" in m for m in got)


@pytest.mark.parametrize(
    "line",
    [
        "denied: requested access to the resource is denied",
        "denied: permission_denied: write_package",
        "unauthorized: authentication required",
    ],
)
def test_registry_refusals_in_the_docker_cli_format_are_error_lines(line: str) -> None:
    got = run_prepass(
        [build_job(1, "build", "Push", "docker push x", f"Pushing\n{line}\n##[error]Process completed with exit code 1.")]
    )
    (g,) = got.primaries
    assert g.primary.message == line and g.primary.kind == "generic"  # observed text only: no inferred cause


@pytest.mark.parametrize(
    "line",
    [
        "ls: cannot open directory '/root': Permission denied",  # "denied" inside a sentence
        "Access denied: see the deployment guide",  # another tool's wording: not a registry code
        "denied: 3",  # a counter in a summary table
        "unauthorized: 0",
        "    denied: requested access to the resource is denied (quoted in a doc)",  # indented echo still counts?
    ],
    ids=["sentence", "other-wording", "counter", "counter-unauthorized", "indented-echo"],
)
def test_unrelated_or_counter_denied_lines_are_not_registry_refusals(line: str) -> None:
    out = f"step\n{line}\n##[error]Process completed with exit code 1."
    got = [g.primary for g in run_prepass([build_job(1, "build", "Run", "./run.sh", out)]).primaries]
    if line.startswith("    denied:"):
        # Leading whitespace is stripped before matching (as for every generic pattern): an indented copy of the
        # exact registry line is indistinguishable from the real one. Reported as observed; never as a cause.
        assert [c.message for c in got] == [line.strip()]
        return
    assert all(c.message != line.strip() for c in got)


def test_a_registry_line_does_not_hide_a_real_test_failure_in_the_same_job() -> None:
    """Misleading log: a stale `denied:` printed by a cleanup step after the real failure. Both are kept as observed
    candidates for the investigation; nothing is ranked as the cause by the pre-pass."""
    out = "\n".join(
        [
            "FAILED tests/test_pricing.py::test_total - assert 0.21 == 1.21",
            "denied: requested access to the resource is denied",
            "##[error]Process completed with exit code 1.",
        ]
    )
    msgs = [g.primary.message for g in run_prepass([build_job(1, "test", "Test", "pytest", out)]).primaries]
    assert any("test_total" in m or "0.21" in m for m in msgs)
