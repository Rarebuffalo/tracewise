"""T-901 lane history foundation (FS-ATR-2): AT-ATR-04, AT-ATR-05 (job/step level), AT-ATR-06. Synthetic runs and the
in-process fake GitHub only; nothing is published (ADR-13: surfaced only after benchmark validation)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.unit.test_github_client import setup
from tracewise.analysis.lane import (
    LANE_WINDOW,
    compute_history,
    event_class,
    fetch_history,
    lane_run,
    pre_existing_steps,
)
from tracewise.github import errors as err

REPO = 7
C0, C1, C2, C3 = ("0" * 40, "1" * 40, "2" * 40, "3" * 40)


def run(rid: int, sha: str, conclusion: str | None, minute: int, **over: Any) -> dict[str, Any]:
    doc = {
        "id": rid,
        "workflow_id": 3,
        "run_attempt": 1,
        "event": "push",
        "head_branch": "main",
        "head_sha": sha,
        "conclusion": conclusion,
        "created_at": f"2026-10-17T10:{minute:02d}:00Z",
        "head_repository": {"id": REPO},
    }
    doc.update(over)
    return doc


def test_at_atr_04_last_green_and_first_red() -> None:
    runs = [run(12, C2, "failure", 3), run(11, C1, "failure", 2), run(10, C0, "success", 1)]
    h = compute_history(REPO, 12, runs)
    assert h.known and h.complete
    assert h.last_green is not None and h.last_green.head_sha == C0
    assert h.first_red is not None and h.first_red.head_sha == C1 and h.failing_runs == 2


def test_the_current_run_starting_the_streak_is_its_own_first_red() -> None:
    h = compute_history(REPO, 11, [run(11, C1, "failure", 2), run(10, C0, "success", 1)])
    assert h.first_red is not None and h.first_red.run_id == 11 and h.failing_runs == 1


def test_at_atr_06_forks_from_the_same_branch_name_are_separate_lanes() -> None:
    runs = [
        run(22, C2, "failure", 3, event="pull_request", head_repository={"id": 501}),
        run(21, C1, "success", 2, event="pull_request", head_repository={"id": 502}),  # another fork's "main"
        run(20, C0, "failure", 1, event="pull_request", head_repository={"id": 501}),
    ]
    h = compute_history(REPO, 22, runs)
    assert h.lane is not None and h.lane.head_repo_id == 501
    assert h.last_green is None and h.first_red is not None and h.first_red.run_id == 20  # 502's green does not count


def test_other_workflows_events_and_branches_are_other_lanes() -> None:
    runs = [
        run(30, C3, "failure", 4),
        run(29, C2, "success", 3, workflow_id=99),
        run(28, C2, "success", 3, event="schedule"),
        run(27, C2, "success", 3, head_branch="dev"),
        run(26, C1, "success", 2),
    ]
    h = compute_history(REPO, 30, runs)
    assert h.last_green is not None and h.last_green.run_id == 26


def test_pull_request_and_pull_request_target_share_a_lane() -> None:
    assert event_class("pull_request_target") == event_class("pull_request") == "pull_request"
    runs = [run(41, C1, "failure", 2, event="pull_request"), run(40, C0, "success", 1, event="pull_request_target")]
    assert compute_history(REPO, 41, runs).last_green is not None


def test_cancelled_skipped_and_in_progress_runs_neither_start_nor_break_a_streak() -> None:
    runs = [
        run(55, C3, "failure", 5),
        run(54, C2, "cancelled", 4),
        run(53, C2, None, 4),
        run(52, C1, "failure", 3),
        run(51, C1, "skipped", 2),
        run(50, C0, "success", 1),
    ]
    h = compute_history(REPO, 55, runs)
    assert h.last_green is not None and h.last_green.run_id == 50
    assert h.first_red is not None and h.first_red.run_id == 52 and h.failing_runs == 2


def test_ties_in_time_are_ordered_by_run_id_and_newer_runs_are_ignored() -> None:
    runs = [run(63, C3, "success", 9), run(62, C2, "failure", 5), run(61, C1, "success", 5), run(60, C0, "failure", 1)]
    h = compute_history(REPO, 62, runs)
    assert h.last_green is not None and h.last_green.run_id == 61  # the later green (63) is after the current run


def test_unknown_and_incomplete_histories_are_explicit() -> None:
    assert not compute_history(REPO, 999, [run(10, C0, "success", 1)]).known
    h = compute_history(REPO, 12, [run(12, C2, "failure", 3), run(11, C1, "failure", 2)])
    assert h.known and not h.complete and h.last_green is None and "no green" in (h.reason or "")
    assert not compute_history(REPO, 1, []).known


@pytest.mark.parametrize(
    "bad",
    [
        5,
        {"id": "x"},
        run(70, C0, "success", 1, head_repository=None),
        run(70, C0, "success", 1, workflow_id=True),
        run(70, C0, 7, 1),
        run(70, "", "success", 1),
    ],
    ids=["not-an-object", "id-not-int", "no-head-repo", "bool-workflow", "conclusion-not-str", "empty-sha"],
)
def test_malformed_runs_are_skipped_never_guessed(bad: Any) -> None:
    assert lane_run(REPO, bad) is None
    h = compute_history(REPO, 72, [run(72, C2, "failure", 3), bad, run(71, C1, "success", 2)])
    assert h.last_green is not None and h.last_green.run_id == 71


# ------------------------------------------------------------------ fetching through the client (fake GitHub)

RUNS = r"^/repos/pallets/flask/actions/runs$"


def test_fetch_filters_the_branch_and_event_and_bounds_the_window() -> None:
    gh, rc = setup()
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            200, json={"total_count": 2, "workflow_runs": [run(12, C2, "failure", 3), run(10, C0, "success", 1)]}
        )

    gh.route("GET", RUNS, handler)
    h = fetch_history(rc, run_id=12, workflow_id=3, branch="main", event="push", head_repo_id=REPO)
    assert h.last_green is not None and h.last_green.run_id == 10
    q = seen[0].url.params
    assert q["branch"] == "main" and q["event"] == "push" and LANE_WINDOW <= 200


def test_fetch_for_a_pull_request_does_not_filter_the_event() -> None:
    gh, rc = setup()
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"total_count": 0, "workflow_runs": []})

    gh.route("GET", RUNS, handler)
    h = fetch_history(rc, run_id=5, workflow_id=3, branch="feat", event="pull_request", head_repo_id=REPO)
    assert not h.known and "event" not in seen[0].url.params


def test_a_lane_mismatch_with_the_job_is_unknown() -> None:
    gh, rc = setup()
    gh.route("GET", RUNS, httpx.Response(200, json={"total_count": 1, "workflow_runs": [run(12, C2, "failure", 3)]}))
    h = fetch_history(rc, run_id=12, workflow_id=4, branch="main", event="push", head_repo_id=REPO)  # job says wf 4
    assert not h.known


@pytest.mark.parametrize("body", [[], {"workflow_runs": None}], ids=["array", "null-list"])
def test_malformed_run_lists_are_permanent_github_errors(body: Any) -> None:
    gh, rc = setup()
    gh.route("GET", RUNS, httpx.Response(200, json=body))
    with pytest.raises(err.GitHubPermanent):
        fetch_history(rc, run_id=1, workflow_id=3, branch="main", event="push", head_repo_id=REPO)


# ------------------------------------------------------------------ AT-ATR-05: same job and step already failing


def jobs(name: str, step: str) -> dict[str, Any]:
    return {
        "jobs": [
            {
                "id": 1,
                "name": name,
                "conclusion": "failure",
                "steps": [{"name": step, "number": 3, "conclusion": "failure"}],
            }
        ]
    }


def test_at_atr_05_same_job_and_step_already_failing_before_this_push() -> None:
    gh, rc = setup()
    gh.route("GET", r"/actions/runs/11/attempts/1/jobs$", httpx.Response(200, json=jobs("Tests", "tox run")))
    h = compute_history(REPO, 12, [run(12, C2, "failure", 3), run(11, C1, "failure", 2), run(10, C0, "success", 1)])
    assert pre_existing_steps(rc, h, {("Tests", "tox run")}) == {("Tests", "tox run")}
    assert pre_existing_steps(rc, h, {("Lint", "ruff")}) == set()  # a different job/step is not pre-existing


def test_no_pre_existing_steps_when_the_current_run_started_the_streak_or_history_is_unknown() -> None:
    gh, rc = setup()
    started_here = compute_history(REPO, 11, [run(11, C1, "failure", 2), run(10, C0, "success", 1)])
    assert pre_existing_steps(rc, started_here, {("Tests", "tox run")}) == set()  # never "already failing" vs itself
    unknown = compute_history(REPO, 99, [])
    assert pre_existing_steps(rc, unknown, {("Tests", "tox run")}) == set()
    assert not any("/jobs" in r.url.path for r in gh.requests)  # no jobs API call is needed for either
