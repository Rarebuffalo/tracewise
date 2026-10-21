"""Lane history foundation (T-901; FS-ATR-2; AT-ATR-04, AT-ATR-05, AT-ATR-06). P2: computed, NOT yet published.

A lane is `(repo_id, workflow_id, event_class, branch, head_repo_id)`. For a failed run, the lane history names the
last green run before it and the first red run of the current failing streak, so a later report can say "this job
and step were already failing before this push" (job/step level only), instead of blaming the push. ADR-13: lane
logic is a signal, never proof, and is surfaced in reports only after benchmark validation. Nothing here writes to
GitHub or changes a published report.

Inputs are untrusted GitHub run objects. Malformed entries are skipped, never guessed. A history is `known=False`
when the current run is not in the fetched window, and `complete=False` when no green run was found within it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from tracewise.github import errors as gh_err
from tracewise.prepass.envelope import JobInfo

if TYPE_CHECKING:
    from tracewise.github.client import RepoClient

# Event names that share one lane: a PR's runs belong together whichever PR event triggered them.
_PR_EVENTS = frozenset({"pull_request", "pull_request_target"})
_RED = frozenset({"failure", "timed_out", "startup_failure"})
_GREEN = frozenset({"success"})
# cancelled / skipped / neutral / action_required / stale / null (in progress) neither start nor break a streak.


def event_class(event: str) -> str:
    return "pull_request" if event in _PR_EVENTS else event


@dataclass(frozen=True)
class Lane:
    repo_id: int
    workflow_id: int
    event_class: str
    branch: str
    head_repo_id: int


@dataclass(frozen=True)
class LaneRun:
    run_id: int
    attempt: int
    head_sha: str
    conclusion: str | None
    created_at: str
    lane: Lane


@dataclass(frozen=True)
class LaneHistory:
    lane: Lane | None
    known: bool
    complete: bool
    last_green: LaneRun | None = None
    first_red: LaneRun | None = None
    failing_runs: int = 0  # red runs in the current streak, the current run included
    reason: str | None = None
    current_run_id: int | None = None


def lane_run(repo_id: int, doc: Any) -> LaneRun | None:
    """A validated view of one GitHub workflow-run object, or None when any field we rely on is missing or typed
    wrongly (fork runs need `head_repository.id`; without it the lane cannot be told apart, so the run is skipped)."""
    if not isinstance(doc, dict):
        return None
    head_repo = doc.get("head_repository")
    fields = (doc.get("id"), doc.get("workflow_id"), doc.get("run_attempt", 1))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in fields):
        return None
    if not isinstance(head_repo, dict) or not isinstance(head_repo.get("id"), int):
        return None
    event, branch, sha, created = doc.get("event"), doc.get("head_branch"), doc.get("head_sha"), doc.get("created_at")
    if not all(isinstance(v, str) and v for v in (event, branch, sha, created)):
        return None
    conclusion = doc.get("conclusion")
    if conclusion is not None and not isinstance(conclusion, str):
        return None
    lane = Lane(repo_id, int(doc["workflow_id"]), event_class(str(event)), str(branch), int(head_repo["id"]))
    return LaneRun(int(doc["id"]), int(fields[2]), str(sha), conclusion, str(created), lane)


def compute_history(repo_id: int, current_run_id: int, runs: list[Any]) -> LaneHistory:
    """Last green and first red for the current run's lane, from a window of run objects (any order)."""
    parsed = [r for r in (lane_run(repo_id, d) for d in runs) if r is not None]
    current = next((r for r in parsed if r.run_id == current_run_id), None)
    if current is None:
        return LaneHistory(None, known=False, complete=False, reason="current run not in the fetched window")
    same = [r for r in parsed if r.lane == current.lane and r.run_id != current.run_id]
    # Newest first; run ids break timestamp ties (they increase with creation).
    older = sorted(
        (r for r in same if (r.created_at, r.run_id) < (current.created_at, current.run_id)),
        key=lambda r: (r.created_at, r.run_id),
        reverse=True,
    )
    first_red = current if current.conclusion in _RED else None
    streak = 1 if first_red else 0
    for r in older:
        if r.conclusion in _GREEN:
            return LaneHistory(
                current.lane, True, True, last_green=r, first_red=first_red, failing_runs=streak, current_run_id=current.run_id
            )
        if r.conclusion in _RED:
            first_red, streak = r, streak + 1
    return LaneHistory(
        current.lane,
        True,
        False,
        first_red=first_red,
        failing_runs=streak,
        reason="no green run in the fetched window",
        current_run_id=current.run_id,
    )


def same_failing_steps(current: set[tuple[str, str]], earlier: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """AT-ATR-05 (job/step level only): the (job, step) pairs failing now that were already failing at the start of
    the streak. Never an error-level or causal claim."""
    return current & earlier


LANE_WINDOW = 200  # most recent runs on the branch examined for one history (at most 2 list requests)


def fetch_history(rc: RepoClient, *, run_id: int, workflow_id: int, branch: str, event: str, head_repo_id: int) -> LaneHistory:
    """Lane history from the repository's recent runs on the branch (Actions: read). The workflow and the fork are
    filtered here, because the list endpoint cannot filter them. Read-only."""
    query: dict[str, Any] = {"branch": branch, "per_page": 100}
    if event_class(event) != "pull_request":
        query["event"] = event  # PR lanes merge pull_request and pull_request_target, so no event filter
    runs = rc.paginate_limited("list_workflow_runs", "workflow_runs", LANE_WINDOW, query=query)
    history = compute_history(rc.repo_id, run_id, runs)
    if history.lane is not None and (history.lane.workflow_id, history.lane.head_repo_id) != (workflow_id, head_repo_id):
        return LaneHistory(None, known=False, complete=False, reason="run does not match the job's lane")
    return history


def failing_steps(rc: RepoClient, run_id: int, attempt: int) -> set[tuple[str, str]]:
    """(job name, failed step name) pairs of one run attempt, from the jobs API."""
    try:
        jobs = [JobInfo.model_validate(j) for j in rc.failed_jobs(run_id, attempt)]
    except ValidationError:
        raise gh_err.GitHubPermanent("list_jobs_for_attempt: unexpected job shape") from None
    out: set[tuple[str, str]] = set()
    for j in jobs:
        step = j.failed_step()
        out.add((j.name, step.name if step else ""))
    return out


def pre_existing_steps(rc: RepoClient, history: LaneHistory, current: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """AT-ATR-05: the failing (job, step) pairs that already failed at the start of this streak. Empty when the
    history is unknown or the current run itself started the streak."""
    first = history.first_red
    if not history.known or first is None or not current or first.run_id == history.current_run_id:
        return set()  # unknown, or this run started the streak: nothing was failing before it
    earlier = failing_steps(rc, first.run_id, first.attempt)
    return same_failing_steps(current, earlier)
