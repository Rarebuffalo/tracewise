"""Deterministic evidence collection: analysis-flow steps 2-6 (T-307).

Retrieval only, no reasoning: failed jobs (jobs API) → their logs → pre-pass → trigger diff →
code context → read-only tool box. The result is an explicit, bounded `Evidence` bundle that the
investigator (T-402) and the validator (T-403) consume. Everything runs with the **analysis-scope**
token of the run's repository. The code workspace lives exactly as long as the `with` block.

Status rules (FS-LOG-1, FS-LOG-3):
* only jobs whose conclusion is failure/timed_out are downloaded (≤ `max_jobs`);
* 404/410 on every failed job's log → `logs_unavailable` (metadata only, no guessed cause);
* 403 → `permission_denied` (FS-ERR-3); some logs missing → `ok` with `logs_missing` listed.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from tracewise.analysis.attempt import AttemptDeadline
from tracewise.context.gitfetch import GitFetcher
from tracewise.context.paths import UnsafePath, validate_repo_path
from tracewise.context.provider import open_code_context
from tracewise.context.source import CodeSource, Limits
from tracewise.context.tools import ToolBox, ToolLimits
from tracewise.context.trigger import TriggerDiff, compute_trigger_diff
from tracewise.contracts import AnalysisJob
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient
from tracewise.prepass.envelope import DEFAULT_MAX_BYTES, JobInfo
from tracewise.prepass.primary import PrepassResult, run_prepass

log = logging.getLogger(__name__)

Status = Literal["ok", "logs_unavailable", "permission_denied", "no_failed_jobs"]
MAX_JOBS = 5


@dataclass
class Evidence:
    job: AnalysisJob
    status: Status
    failed_jobs: list[JobInfo]
    prepass: PrepassResult | None
    trigger: TriggerDiff
    source: CodeSource
    tools: ToolBox
    logs_missing: list[int] = field(default_factory=list)
    jobs_not_downloaded: list[int] = field(default_factory=list)
    missing_permission: str | None = None
    deadline_exhausted: bool = False  # C-4: the attempt deadline cut collection short (logs or jobs incomplete)

    @property
    def implicated_paths(self) -> set[str]:
        """Pre-pass locations only. The validated diagnosis location must be added before `relevance()`."""
        out: set[str] = set()
        for g in self.prepass.primaries if self.prepass else []:
            for c in g.members:
                if c.path:
                    with contextlib.suppress(UnsafePath):
                        out.add(validate_repo_path(c.path))
        return out

    @property
    def log_truncated(self) -> bool:
        return bool(self.prepass and self.prepass.log_truncated) or bool(self.logs_missing) or self.deadline_exhausted


# A signed log URL is valid for about a minute (FS-LOG-1). Streams are opened together but read one after another, so a
# slow first log could let the later URLs expire (C-7): a URL older than this is re-requested just before reading.
_URL_FRESH_S = 30.0


class _LogStream:
    """Iterates one job's log lines; records (instead of raising) a log that vanished mid-way."""

    def __init__(
        self, rc: RepoClient, job_id: int, clock: Callable[[], float] = time.monotonic, deadline: AttemptDeadline | None = None
    ) -> None:
        self.rc, self.job_id, self._clock, self._deadline = rc, job_id, clock, deadline
        self.truncated = False
        self.deadline_cut = False
        self.error: Exception | None = None
        self.lines: Iterator[str] | None = None
        self._opened_at = 0.0

    def open(self) -> None:
        self.lines = self.rc.job_log_lines(self.job_id)  # API call + redirect check happen here
        self._opened_at = self._clock()

    def __iter__(self) -> Iterator[str]:
        assert self.lines is not None
        try:
            if self._clock() - self._opened_at > _URL_FRESH_S:
                self.lines = self.rc.job_log_lines(self.job_id)  # nothing was read from the old URL
            for line in self.lines:
                if self._deadline is not None and self._deadline.expired:
                    # C-4: the attempt's time is up. Keep what was read, mark the log incomplete, release the stream.
                    self.truncated = self.deadline_cut = True
                    close = getattr(self.lines, "close", None)
                    if close is not None:
                        close()
                    return
                yield line
            self.truncated = bool(getattr(self.lines, "truncated", False))
        except (gh_err.NotFound, gh_err.Gone, gh_err.GitHubRetryable, gh_err.UnsafeRedirect, gh_err.PermissionDenied) as e:
            self.error = e  # PermissionDenied only from a re-request: access was revoked while earlier logs were read


@contextlib.contextmanager
def collect_evidence(
    job: AnalysisJob,
    rc: RepoClient,
    *,
    fetcher: GitFetcher | None,
    base_sha: str | None = None,
    max_jobs: int = MAX_JOBS,
    code_limits: Limits | None = None,
    tool_limits: ToolLimits | None = None,
    log_max_bytes: int = DEFAULT_MAX_BYTES,
    deadline: AttemptDeadline | None = None,
) -> Iterator[Evidence]:
    if rc.scope != "analysis" or rc.repo_id != job.repo_id:
        raise ValueError("evidence collection needs the analysis-scope client of the run's repository")
    try:
        failed = [JobInfo.model_validate(j) for j in rc.failed_jobs(job.run_id, job.attempt)]
    except ValidationError:  # a job without the fields we rely on: retrying cannot repair GitHub's answer
        raise gh_err.GitHubPermanent("list_jobs_for_attempt: unexpected job shape") from None
    selected, skipped = failed[:max_jobs], [j.id for j in failed[max_jobs:]]

    status: Status = "ok" if selected else "no_failed_jobs"
    missing: list[int] = []
    permission: str | None = None
    streams: list[tuple[JobInfo, _LogStream]] = []
    out_of_time = False
    for j in selected:
        if deadline is not None and deadline.expired:
            out_of_time = True  # C-4: jobs not reached in time are reported as not downloaded, never as clean
            skipped.append(j.id)
            continue
        s = _LogStream(rc, j.id, deadline=deadline)
        try:
            s.open()
        except (gh_err.NotFound, gh_err.Gone, gh_err.UnsafeRedirect):
            missing.append(j.id)
            continue
        except gh_err.PermissionDenied as e:
            permission = e.permission or "actions:read"
            status = "permission_denied"
            break
        streams.append((j, s))
    prepass: PrepassResult | None = None
    if status == "ok" and streams:
        prepass = run_prepass(((j, s) for j, s in streams), max_bytes=log_max_bytes)  # FS-LOG-4 retention budget
        for _, s in streams:  # FS-LOG-4: a download cut by the cap must be flagged, whatever was retained
            if s.truncated and s.job_id in prepass.logs:
                prepass.logs[s.job_id].truncated = True
        missing += [s.job_id for _, s in streams if s.error is not None]
        out_of_time = out_of_time or any(s.deadline_cut for _, s in streams)
    if status == "ok" and len(missing) == len(selected) and selected:
        status, prepass = "logs_unavailable", None  # metadata only; never a guessed cause (FS-LOG-3)

    trigger = compute_trigger_diff(rc, job.head_sha, base_sha=base_sha)
    if fetcher is not None and deadline is not None:
        # The git fetch's own timeout, never beyond what the attempt has left. With almost nothing left the fetch is
        # skipped; the contents API source reads lazily, and each read is bounded by the client and the tool loop.
        left = deadline.cap(fetcher.flimits.fetch_timeout_s)
        if left < 1.0:
            fetcher, out_of_time = None, True
        else:
            fetcher.flimits = dataclasses.replace(fetcher.flimits, fetch_timeout_s=left)
    with open_code_context(rc, job.head_sha, fetcher=fetcher, limits=code_limits) as source:
        if deadline is not None:
            source.time_left = deadline.remaining  # transient-read retries stop at the attempt deadline (C-4, I-3)
        tools = ToolBox(source, diff_text=trigger.render(), limits=tool_limits or ToolLimits())
        ev = Evidence(job, status, failed, prepass, trigger, source, tools, missing, skipped, permission, out_of_time)
        log.info(
            "evidence collected",
            extra={
                "tw": {
                    "status": status,
                    "failed_jobs": len(failed),
                    "logs_missing": len(missing),
                    "source": source.kind,
                    "primaries": len(prepass.primaries) if prepass else 0,
                    "trigger_known": trigger.known,
                }
            },
        )
        yield ev
