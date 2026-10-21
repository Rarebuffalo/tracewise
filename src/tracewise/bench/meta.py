"""META benchmark runner (T-604; FS-ATR-2; AT-ATR-05, AT-SEC-14). Public-metadata cases, reported separately from the
synthetic benchmark (BENCHMARK §6) and never merged with it.

Each case is evaluated from anonymous, read-only GitHub metadata only (lane run lists, run jobs, a commit). A `Source`
supplies the documents:

* `RecordedSource` serves responses recorded earlier, read in place from a directory, through an index that names each
  file's original endpoint and fetch time (offline; tests and reruns). `RECORDED_INDEX` describes the anonymous fetch
  of 2026-10-17 (docs/BENCHMARK.md §3.2).
* `AnonymousSource` wraps `github.client.AnonymousGitHub` (live, anonymous; separate approval). An operation outside
  that client's allowlist is reported as missing evidence, never fetched another way.

Statuses: `pass` / `fail` (evaluated), `missing_evidence` (a document the case needs is not available; `requires`
names it), `error` (a document exists but is malformed or contradicts the case's identifiers). The label is derived
from metadata by the lane logic (analysis/lane.py), never copied from the truth table.

Cases (docs/BENCHMARK.md §3.2):
- P-01: the same job and step already failed at the first red run of the current streak → pre-existing.
- P-02: a job fails for the first time at this run (it passed in the previous lane run), and the next lane run is green.
- P-03: a push edited one file and the run failed without logs → no unsupported causal claim (false-blame guard).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from tracewise.analysis.lane import LaneHistory, compute_history, lane_run, same_failing_steps
from tracewise.context.trigger import _parse_compare, relevance
from tracewise.github import errors as gh_err
from tracewise.github.client import AnonymousGitHub
from tracewise.prepass.envelope import JobInfo

_CAUSAL = re.compile(r"(?i)\bcaus|introduc|broke|responsible|fault of")
_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.json")
REPO = "pallets/flask"
TESTS_WORKFLOW = 1367898  # pallets/flask "Tests"


class MissingEvidence(Exception):
    """A document the case needs is not available from this source (not recorded, or not allowlisted)."""


class Source(Protocol):
    kind: str

    def get(self, name: str, *, repo: str, **params: Any) -> Any: ...

    def provenance(self, name: str, *, repo: str, **params: Any) -> dict[str, str]: ...


def key_for(name: str, repo: str, params: dict[str, Any]) -> str:
    return f"{name}|{repo}|" + ",".join(f"{k}={params[k]}" for k in sorted(params))


# The anonymous fetch of 2026-10-17 (research/final-evidence-review/evidence/FETCH-LOG.tsv). Job lists were fetched
# from /runs/{id}/jobs (latest attempt); every job in them is attempt 1, which `_jobs` checks before use.
RECORDED_INDEX: tuple[dict[str, Any], ...] = (
    {
        "name": "get_commit",
        "params": {"sha": "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35"},
        "file": "flask-commit-d73fa1cdcb.json",
        "endpoint": "/repos/pallets/flask/commits/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35",
        "fetched_at": "2026-10-17",
    },
    {
        "name": "list_jobs_for_attempt",
        "params": {"run_id": 37632626982, "attempt": 1},
        "file": "flask-run-37632626982-jobs.json",
        "endpoint": "/repos/pallets/flask/actions/runs/37632626982/jobs?per_page=100",
        "fetched_at": "2026-10-17",
    },
    {
        "name": "list_jobs_for_attempt",
        "params": {"run_id": 34252544596, "attempt": 1},
        "file": "flask-run-34252544596-jobs.json",
        "endpoint": "/repos/pallets/flask/actions/runs/34252544596/jobs?per_page=100",
        "fetched_at": "2026-10-17T17:26:38Z",
    },
    {
        "name": "list_jobs_for_attempt",
        "params": {"run_id": 37633292268, "attempt": 1},
        "file": "flask-run-37633292268-jobs.json",
        "endpoint": "/repos/pallets/flask/actions/runs/37633292268/jobs?per_page=100",
        "fetched_at": "2026-10-17T17:26:42Z",
    },
    {
        "name": "list_lane_runs",
        "params": {"workflow_id": TESTS_WORKFLOW, "branch": "main", "event": "push"},
        "file": "flask-tests-main-runs.json",
        "endpoint": "/repos/pallets/flask/actions/workflows/1367898/runs?branch=main&event=push&per_page=40",
        "fetched_at": "2026-10-17T17:26:27Z",
    },
)


class RecordedSource:
    """Serves recorded anonymous responses read in place from `root`. `index` entries name the operation, its
    parameters, a plain file name inside `root`, and the original endpoint and fetch time."""

    kind = "recorded"

    def __init__(self, root: Path, index: tuple[dict[str, Any], ...] | list[dict[str, Any]] = RECORDED_INDEX) -> None:
        self.root = root
        self.entries: dict[str, dict[str, Any]] = {}
        for e in index:
            if not isinstance(e.get("file"), str) or not _FILE.fullmatch(e["file"]):
                raise ValueError("recorded index: file must be a plain .json name")  # no paths, no traversal
            self.entries[key_for(e["name"], e.get("repo", REPO), e["params"])] = e

    def _entry(self, name: str, repo: str, params: dict[str, Any]) -> dict[str, Any]:
        e = self.entries.get(key_for(name, repo, params))
        if e is None:
            raise MissingEvidence(f"{name} {key_for(name, repo, params)} was not recorded")
        return e

    def get(self, name: str, *, repo: str, **params: Any) -> Any:
        e = self._entry(name, repo, params)
        f = self.root / e["file"]
        if not f.is_file():
            raise MissingEvidence(f"recorded file {e['file']} is not present")
        try:
            return json.loads(f.read_text())
        except (ValueError, RecursionError):
            raise gh_err.GitHubPermanent(f"recorded file {e['file']} is not valid JSON") from None

    def provenance(self, name: str, *, repo: str, **params: Any) -> dict[str, str]:
        e = self._entry(name, repo, params)
        return {"endpoint": str(e.get("endpoint", "")), "fetched_at": str(e.get("fetched_at", "")), "file": e["file"]}


class AnonymousSource:
    kind = "anonymous_live"

    def __init__(self, gh: AnonymousGitHub, clock: Callable[[], datetime] | None = None) -> None:
        self.gh, self._clock = gh, clock or (lambda: datetime.now(UTC))

    def get(self, name: str, *, repo: str, **params: Any) -> Any:
        if not AnonymousGitHub.allows(name):
            raise MissingEvidence(f"{name} is not in the anonymous allowlist (needs an approved change)")
        return self.gh.get(name, repo=repo, **params)

    def provenance(self, name: str, *, repo: str, **params: Any) -> dict[str, str]:
        path = self.gh.requests[-1] if self.gh.requests else ""
        return {"endpoint": path, "fetched_at": self._clock().isoformat()}


@dataclass
class MetaResult:
    case: str
    status: str  # pass | fail | missing_evidence | error
    label: str
    expected: str
    requires: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


class _Ctx:
    """Fetches through the source and records the provenance of every document a case used."""

    def __init__(self, src: Source) -> None:
        self.src = src
        self.used: list[dict[str, str]] = []

    def get(self, name: str, **params: Any) -> Any:
        doc = self.src.get(name, repo=REPO, **params)
        self.used.append({"operation": name, **self.src.provenance(name, repo=REPO, **params)})
        return doc


def _failing(doc: Any, attempt: int | None = None) -> set[tuple[str, str]]:
    """(job, failed step) pairs; with `attempt`, every job must belong to that attempt."""
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), list):
        raise gh_err.GitHubPermanent("unexpected jobs response")
    out: set[tuple[str, str]] = set()
    for item in doc["jobs"]:
        if attempt is not None and isinstance(item, dict) and item.get("run_attempt", attempt) != attempt:
            raise gh_err.GitHubPermanent("jobs response is for another attempt")
        try:
            j = JobInfo.model_validate(item)
        except ValueError:
            raise gh_err.GitHubPermanent("unexpected job shape") from None
        if j.conclusion in ("failure", "timed_out"):
            step = j.failed_step()
            out.add((j.name, step.name if step else ""))
    return out


def _lane(ctx: _Ctx, current: int) -> tuple[LaneHistory, list[Any]]:
    doc = ctx.get("list_lane_runs", workflow_id=TESTS_WORKFLOW, branch="main", event="push")
    if not isinstance(doc, dict) or not isinstance(doc.get("workflow_runs"), list):
        raise gh_err.GitHubPermanent("unexpected run list")
    runs = doc["workflow_runs"]
    cur = next((r for r in runs if isinstance(r, dict) and r.get("id") == current), None)
    repo_id = cur.get("repository", {}).get("id") if isinstance(cur, dict) and isinstance(cur.get("repository"), dict) else None
    if not isinstance(repo_id, int):
        raise MissingEvidence(f"run {current} is not in the recorded lane window")
    history = compute_history(repo_id, current, runs)
    if not history.known:
        raise MissingEvidence(f"run {current} is not in the recorded lane window")
    return history, runs


def p01(ctx: _Ctx) -> MetaResult:
    current, expected = 37632626982, "pre-existing at job/step level (Development Versions / tox run)"
    history, _ = _lane(ctx, current)
    first = history.first_red
    if first is None or first.run_id == current:
        return MetaResult("P-01", "fail", "this run starts the failing streak: not pre-existing", expected)
    now = _failing(ctx.get("list_jobs_for_attempt", run_id=current, attempt=1), 1)
    before = _failing(ctx.get("list_jobs_for_attempt", run_id=first.run_id, attempt=first.attempt), first.attempt)
    shared = sorted(same_failing_steps(now, before))
    ok = any(j == "Development Versions" and "tox run" in s for j, s in shared)
    label = (
        f"pre-existing at job/step level: {', '.join(f'{j} / {s}' for j, s in shared)} already failed at run {first.run_id}"
        if shared
        else f"not pre-existing (first red of the streak: run {first.run_id})"
    )
    return MetaResult("P-01", "pass" if ok else "fail", label, expected)


def p02(ctx: _Ctx) -> MetaResult:
    current, job, expected = 37633292268, "typing", "job 'typing' first fails here; the next lane run is green"
    history, runs = _lane(ctx, current)
    parsed = sorted(
        (r for r in (lane_run(history.lane.repo_id if history.lane else 0, d) for d in runs) if r),
        key=lambda r: (r.created_at, r.run_id),
    )
    same = [r for r in parsed if history.lane is not None and r.lane == history.lane]
    idx = next(i for i, r in enumerate(same) if r.run_id == current)
    prev = same[idx - 1] if idx > 0 else None
    nxt = next((r for r in same[idx + 1 :] if r.conclusion in ("success", "failure", "timed_out", "startup_failure")), None)
    if prev is None or nxt is None:
        raise MissingEvidence("the lane window lacks the run before or after this one")
    now_jobs = {j for j, _ in _failing(ctx.get("list_jobs_for_attempt", run_id=current, attempt=1), 1)}
    if job not in now_jobs:
        return MetaResult("P-02", "fail", f"job '{job}' does not fail at this run", expected)
    if prev.conclusion == "success":
        first_here = True
    else:
        prev_jobs = {
            j for j, _ in _failing(ctx.get("list_jobs_for_attempt", run_id=prev.run_id, attempt=prev.attempt), prev.attempt)
        }
        first_here = job not in prev_jobs
    fixed_next = nxt.conclusion == "success"
    label = (
        f"job '{job}' {'first fails here' if first_here else 'was already failing'} (previous lane run {prev.run_id}); "
        f"next lane run {nxt.run_id} is {nxt.conclusion}"
    )
    return MetaResult("P-02", "pass" if first_here and fixed_next else "fail", label, expected)


def p03(ctx: _Ctx) -> MetaResult:
    sha, expected = "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35", "no causal claim about the trigger"
    doc = ctx.get("get_commit", sha=sha)
    if not isinstance(doc, dict) or doc.get("sha") not in (None, sha):
        raise gh_err.GitHubPermanent("commit response is for another commit")
    parents = doc.get("parents")
    first = parents[0] if isinstance(parents, list) and parents else None
    if not isinstance(first, dict) or not isinstance(first.get("sha"), str):
        raise gh_err.GitHubPermanent("unexpected commit response")
    diff = _parse_compare(doc, sha, first["sha"])
    rel = relevance(diff, set())  # no logs, so nothing is implicated
    ok = rel.touches_implicated is None and not _CAUSAL.search(rel.statement)
    return MetaResult("P-03", "pass" if ok else "fail", rel.statement, expected)


CASES: tuple[tuple[str, Callable[[_Ctx], MetaResult]], ...] = (("P-01", p01), ("P-02", p02), ("P-03", p03))


def run(src: Source, *, clock: Callable[[], datetime] | None = None) -> list[MetaResult]:
    """Evaluate every case. Missing documents give `missing_evidence`, malformed ones `error` (never a pass); the
    other cases still run."""
    evaluated_at = (clock() if clock else datetime.now(UTC)).isoformat()
    out: list[MetaResult] = []
    for case_id, case in CASES:
        ctx = _Ctx(src)
        try:
            res = case(ctx)
        except MissingEvidence as e:
            res = MetaResult(case_id, "missing_evidence", "not evaluated", "", requires=str(e))
        except (gh_err.GitHubPermanent, gh_err.GitHubRetryable, ValueError) as e:
            res = MetaResult(case_id, "error", type(e).__name__, "")
        res.provenance = {
            "source": src.kind,
            "anonymous": True,
            "evaluated_at": evaluated_at,
            "documents": ctx.used,
            "granularity": "job/step",
        }
        out.append(res)
    return out


def report(results: list[MetaResult]) -> dict[str, Any]:
    """The META report: separate from the synthetic benchmark, never merged with its scores or truth."""
    counts = {s: sum(r.status == s for r in results) for s in ("pass", "fail", "missing_evidence", "error")}
    return {
        "track": "META (public metadata; reported separately from the synthetic benchmark, never merged)",
        "summary": counts,
        "results": [
            {
                "case": r.case,
                "status": r.status,
                "label": r.label,
                "expected": r.expected,
                "requires": r.requires,
                "provenance": r.provenance,
            }
            for r in results
        ],
    }
