"""The `analyze` job handler: the connected product flow (flow steps 1-11, T-502/T-503).

  validated job → collect_evidence → (PR association) → diagnose → persist analysis → render
  → publish (PR comment | commit comment, + neutral Check Run) → result for the queue

Outcome → job state (FS-ERR-1, FS-ERR-3, FS-LOG-3, FS-INS-3; DECISIONS D-4, D-8, D-9):
  diagnosed / inconclusive          publish report; succeeded
  provider timeout/failure          RetryableError while attempts remain (≤2 retries); on the last attempt
                                    publish "could not complete" (Check Run + PR comment on PRs; no commit
                                    comment); succeeded with outcome `could_not_complete`
  logs unavailable                  publish metadata-only report (Check Run + PR comment on PRs); succeeded
  permission denied (read)          publish "missing permission" (Check Run + PR comment on PRs); succeeded, no retry
  403 on a publication surface      that surface → `unpublished_permission`; other surfaces still published;
                                    the Check Run names the missing permission
  transient GitHub/DB errors        propagate → retry with backoff (honours retry-after; 10-min deadline)
  installation unavailable / repo disabled → JobCancelled (no-op, no GitHub write)
  App JWT rejected (401 on the token mint) → AppAuthenticationFailed, a PermanentError: dead, no retry, no
                                    further GitHub write (no token), counted as a failure; never an uninstall
  invalid payload / repo or installation mismatch → PermanentError (dead, no GitHub write)
  unexpected exception              re-raised (retry; never reported as success). On the last attempt a
                                    best-effort "could not complete" notice is published first.
  lease lost                        LeaseLost propagates; nothing further is written
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from tracewise.analysis.attempt import AttemptDeadline
from tracewise.analysis.collect import collect_evidence
from tracewise.analysis.diagnose import diagnose
from tracewise.context.gitfetch import GitFetcher
from tracewise.contracts import AnalysisJob, Diagnosis, Status
from tracewise.db import repositories as repo
from tracewise.db.session import Conn, DatabaseUnavailable, require_tenant_plane, transaction
from tracewise.github import errors as gh_err
from tracewise.github.auth import TokenProvider
from tracewise.github.client import MIN_REQUEST_S, GitHubHTTP, RepoClient
from tracewise.github.publish import Publisher, PublishResult, PublishTarget, marker
from tracewise.github.pulls import PRAssociation, associate_pr
from tracewise.investigate.loop import InvestigationLimits
from tracewise.investigate.provider import Provider
from tracewise.investigate.replay import ReplayContext
from tracewise.investigate.validate import SOURCE_UNAVAILABLE, ValidatedDiagnosis, ValidationUnavailable
from tracewise.jobs.queue import Fence, JobCancelled, PermanentError, RetryableError, StaleAttempt, retry_fits
from tracewise.jobs.worker import Handler, JobContext, LeaseLost
from tracewise.observe import Stages, bind, event
from tracewise.prepass.envelope import DEFAULT_MAX_BYTES as DEFAULT_LOG_RETAIN_BYTES
from tracewise.report.render import (
    DEFAULT_MAX_CHARS,
    CheckOutput,
    check_output,
    publication_notes,
    render,
    render_could_not_complete,
)

log = logging.getLogger(__name__)
PROVIDER_FAILURES = frozenset({"provider_timeout", "provider_failed"})
# Infrastructure, not evidence: retried, then "could not complete" (never a completed inconclusive analysis).
RETRIED_REASONS = PROVIDER_FAILURES | {SOURCE_UNAVAILABLE}


@dataclass
class AnalyzeDeps:
    pool: ConnectionPool[Conn]  # TENANT role (tracewise_app): every transaction runs with the job's installation
    http: GitHubHTTP
    tokens: TokenProvider
    app_id: int
    provider_factory: Callable[[], Provider]
    fetcher_factory: Callable[[], GitFetcher | None]
    limits: InvestigationLimits = field(default_factory=InvestigationLimits)
    report_max_chars: int = DEFAULT_MAX_CHARS
    bot_login: str | None = None
    price_input_per_mtok: Decimal | None = None  # T-706: unset → cost_usd NULL ("unpriced")
    price_output_per_mtok: Decimal | None = None
    log_max_bytes: int = DEFAULT_LOG_RETAIN_BYTES  # FS-LOG-4 per-job retention budget (LOG_MAX_BYTES_PER_JOB)
    analysis_quota: int | None = None  # T-703 (ANALYSIS_QUOTA_MONTHLY); None: no quota


def cost_usd(deps: AnalyzeDeps, tokens_in: int, tokens_out: int, cached_input_tokens: int | None = None) -> Decimal | None:
    """Cost calculated from configured prices only; None when it cannot be calculated (never estimated):
    either price is unknown, or part of the input was cached. Providers price cached input differently, and no
    cached-input price is configured, so pricing it at the full input rate would overstate the cost."""
    if deps.price_input_per_mtok is None or deps.price_output_per_mtok is None:
        return None
    if cached_input_tokens:
        return None
    m = Decimal(1_000_000)
    return (Decimal(tokens_in) * deps.price_input_per_mtok + Decimal(tokens_out) * deps.price_output_per_mtok) / m


def _load(ctx: JobContext, deps: AnalyzeDeps) -> AnalysisJob:
    try:
        job = AnalysisJob.model_validate(ctx.job.payload)
    except ValidationError:
        raise PermanentError("invalid analysis job payload") from None
    if job.installation_id != ctx.job.installation_id:
        raise PermanentError("job installation does not match its payload")
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        scope = repo.repository_scope(conn, job.repo_id)
    if scope is None or scope["installation_id"] != job.installation_id or scope["full_name"].lower() != job.repo.lower():
        raise PermanentError("repository is not part of the job's installation")
    _check_scope(scope)
    return job


def _check_scope(scope: dict[str, Any]) -> None:
    if scope["installation_status"] == "deleted":
        raise JobCancelled("cancelled_uninstalled")  # FS-INS-3
    if scope["installation_status"] != "active":
        raise JobCancelled("installation_suspended")
    if scope["removed_at"] is not None:
        raise JobCancelled("repo_not_in_scope")  # FS-INS-4
    if not scope["enabled"]:
        raise JobCancelled("repo_disabled")


def _recheck(deps: AnalyzeDeps, job: AnalysisJob) -> None:
    """T-701 / D-10(a): authorisation may change while a job runs; re-read it right before persisting and before
    EVERY publication surface. Revocation raises JobCancelled: earlier surfaces stay, later ones never start."""
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        scope = repo.repository_scope(conn, job.repo_id)
    if scope is None or scope["installation_id"] != job.installation_id:
        raise JobCancelled("repo_not_in_scope")
    _check_scope(scope)


def _associate(rc_p: RepoClient, job: AnalysisJob) -> tuple[PRAssociation, str | None]:
    """PR association by API only (FS-PUB-7). A 403 here means no Pull requests access (AT-REL-05)."""
    is_fork = job.head_repo_id is not None and job.head_repo_id != job.repo_id
    try:
        # G-PLAT-11: association reads pull requests, so it uses the PR surface's token, never a bundled one.
        return associate_pr(
            rc_p.for_scope("publish_pr"),
            head_sha=job.head_sha,
            head_branch=job.head_branch,
            head_repo_full_name=job.head_repo,
            is_fork=is_fork,
        ), None
    except gh_err.PermissionDenied as e:
        return PRAssociation("error", detail="permission"), e.permission or "pull_requests"


def make_analyze_handler(deps: AnalyzeDeps) -> Handler:
    require_tenant_plane(deps.pool)  # T-705: a misconfigured DATABASE_URL must not silently bypass RLS

    def handle(ctx: JobContext) -> dict[str, Any]:
        job = _load(ctx, deps)
        with bind(repo_id=job.repo_id, run_id=job.run_id):
            event(log, "analysis.started", job_attempt=ctx.job.attempts, run_attempt=job.attempt, run_event=job.event)
            return _handle(ctx, deps, job)

    return handle


def _handle(ctx: JobContext, deps: AnalyzeDeps, job: AnalysisJob) -> dict[str, Any]:
    # C-4 / O-2: the attempt's two deadlines, derived once from the job's durable deadline. Work (collection, tools,
    # validation; the analysis client) stops PUBLISH_RESERVE_S early; publication (the publish client) may use it.
    now = datetime.now(UTC)
    work = AttemptDeadline.for_job(ctx.job.deadline_at, now)
    publish = AttemptDeadline.for_publication(ctx.job.deadline_at, now)
    rc_a = RepoClient(
        deps.http,
        deps.tokens,
        installation_id=job.installation_id,
        repo_id=job.repo_id,
        full_name=job.repo,
        scope="analysis",
        deadline=work,
    )
    rc_p = RepoClient(
        deps.http,
        deps.tokens,
        installation_id=job.installation_id,
        repo_id=job.repo_id,
        full_name=job.repo,
        scope="publish",
        deadline=publish,
    )
    target = PublishTarget(job.installation_id, job.repo_id, job.repo, job.head_sha, job.run_id, job.attempt, job.workflow_id)
    publisher = Publisher(deps.pool, rc_p, app_id=deps.app_id, check_lease=ctx.check, bot_login=deps.bot_login, fence=ctx.fence)

    def is_final() -> bool:
        """Decided when a failure happens: no attempts left, or no retry can finish before the deadline (FS-ERR-2).
        O-2: also once the work deadline has passed: a retry has the same absolute deadline, so it could do no work."""
        return not retry_fits(ctx.job, datetime.now(UTC)) or work.remaining() < MIN_REQUEST_S

    if ctx.job.deadline_at is not None and datetime.now(UTC) >= ctx.job.deadline_at:
        # Claimed after its deadline (it already ran and failed once): no new investigation. If an earlier attempt
        # left a validated analysis unpublished, publish it within the reserve; otherwise tell the user (FS-ERR-1),
        # but never overwrite a recorded analysis with a notice (F1: that used to erase a valid diagnosis). Then end.
        try:
            resumed = _resume_publication(deps, job, target, publisher, rc_p, ctx.job.attempts)
            if resumed is not None:
                return resumed
            if not _analysis_recorded(deps, job):
                _publish_notice(deps, job, target, publisher, rc_p, "could_not_complete", None)
        except (LeaseLost, StaleAttempt, JobCancelled):
            raise
        except Exception as e:
            event(log, "analysis.notice_failed", logging.WARNING, error_type=type(e).__name__)
        raise PermanentError("job deadline passed before a final attempt")
    try:
        resumed = _resume_publication(deps, job, target, publisher, rc_p, ctx.job.attempts)
        if resumed is not None:
            return resumed
        if deps.analysis_quota is not None:
            over = _quota_gate(deps, job, target, publisher, deps.analysis_quota)
            if over is not None:
                return over
        return _run(ctx, deps, job, rc_a, rc_p, target, publisher, is_final, work)
    except gh_err.InstallationUnavailable:
        raise JobCancelled("cancelled_uninstalled") from None  # FS-INS-3: token mint refused
    except gh_err.DeadlineExhausted:
        # O-2: a work-stage request could not start before the work deadline (job deadline less the publication
        # reserve). Nothing more can be read in this job, and a retry would face the same deadline: tell the user
        # within the reserve and end. Once an analysis is recorded, publication itself ran out of time: retryable.
        if _analysis_recorded(deps, job):
            raise
        event(log, "analysis.deadline_exhausted", logging.WARNING, stage="work")
        res = _publish_notice(deps, job, target, publisher, rc_p, "could_not_complete", None)
        return {"outcome": "could_not_complete", "publications": res}
    except gh_err.PermissionDenied as e:
        # Must precede PermanentError (its base class). Reading the run itself is forbidden
        # (e.g. Actions: read missing): say so on the remaining surfaces, do not retry (FS-ERR-3).
        res = _publish_notice(deps, job, target, publisher, rc_p, "permission_denied", e.permission)
        return {"outcome": "permission_denied", "publications": res}
    except RetryableError:
        # A GitHub retryable error (or similar) on the genuine final attempt. FS-ERR-1 asks for a notice, but only
        # when nothing could already be visible: once a surface was attempted, a 5xx/timeout may have been applied
        # and a notice could contradict a published report (owner decision D-14 for that partial case).
        if is_final() and not _analysis_recorded(deps, job):
            try:
                _publish_notice(deps, job, target, publisher, rc_p, "could_not_complete", None)
            except (LeaseLost, StaleAttempt, JobCancelled):
                raise
            except Exception:
                event(log, "analysis.notice_failed", logging.WARNING)
        raise
    except (LeaseLost, StaleAttempt, JobCancelled):
        raise
    except Exception as e:
        # FS-ERR-1: tell the user, then still fail the job (never reported as success). Same guard as the
        # RetryableError branch: once an analysis was recorded a surface may be visible, so no notice (D-14).
        # D-A: a PermanentError is always final (the queue ends the job `dead` without a retry), so it gets the
        # notice on any attempt; before, it was re-raised first and the job died with nothing shown to the user.
        # A credential fault (App key refused, token scope wrong) cannot publish anything either: no notice attempt,
        # which would only repeat the refused token mint.
        credential = isinstance(e, gh_err.AppAuthenticationFailed | gh_err.TokenScopeError)
        final = (isinstance(e, PermanentError) and not credential) or is_final()
        if isinstance(e, PermanentError):
            event(log, "analysis.permanent_failure", logging.WARNING, error_type=type(e).__name__)
        if final and not _analysis_recorded(deps, job):
            try:
                _publish_notice(deps, job, target, publisher, rc_p, "could_not_complete", None)
            except Exception:
                # Best effort only: the original error is what gets recorded and retried/failed.
                event(log, "analysis.notice_failed", logging.WARNING)
        raise


QUOTA_TITLE = "Analysis quota reached"


def _quota_lock_key(installation_id: int, repo_id: int) -> int:
    digest = hashlib.sha256(f"tracewise:quota:{installation_id}:{repo_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _quota_gate(
    deps: AnalyzeDeps, job: AnalysisJob, target: PublishTarget, publisher: Publisher, quota: int
) -> dict[str, Any] | None:
    """T-703 / FS-QTA-1: before any log download or investigation, stop when the installation has used its monthly
    quota. Over quota: record the run as `quota_exceeded` (never counted) and publish ONE neutral "quota reached"
    Check Run per repository per UTC day; never a comment. Count, today's-notice check and the insert run under one
    per-repository advisory lock, so concurrent jobs cannot both publish."""
    _recheck(deps, job)
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_quota_lock_key(job.installation_id, job.repo_id),))
        existing = repo.find_workflow_run(conn, job.installation_id, job.repo_id, job.run_id, job.attempt)
        if existing is not None and repo.counted_analysis_exists(conn, existing):
            return None  # a retry of a run already analysed (and counted): finish it, never re-label it
        used = repo.count_monthly_analyses(conn, job.installation_id)
        if used < quota:
            return None
        run_pk = repo.find_workflow_run(
            conn, job.installation_id, job.repo_id, job.run_id, job.attempt
        ) or repo.insert_workflow_run(
            conn,
            installation_id=job.installation_id,
            repo_id=job.repo_id,
            run_id=job.run_id,
            attempt=job.attempt,
            workflow_id=job.workflow_id,
            head_sha=job.head_sha,
            head_branch=job.head_branch,
            head_repo_id=job.head_repo_id,
            event=job.event,
            conclusion=job.conclusion,
        )
        noticed = repo.quota_notice_today(conn, job.installation_id, job.repo_id, excluding_run_pk=run_pk)
        if publisher.fence is not None:
            publisher.fence.verify(conn, "persist_quota_notice")  # D-1
        analysis_id = repo.upsert_analysis(
            conn,
            installation_id=job.installation_id,
            run_pk=run_pk,
            status="quota_exceeded",
            category=None,
            confidence_band=None,
            diagnosis=None,
        )
    event(log, "analysis.quota_exceeded", quota=quota, used=used, notice_already_today=noticed)
    results: dict[str, str] = {}
    if not noticed:
        _recheck(deps, job)  # D-10(a): before the surface
        summary = f"This installation has used its monthly quota of {quota} analyses. Tracewise did not analyse this run."
        text = (
            f"{summary} Analyses resume at the start of next month (UTC). This notice appears at most once per "
            "repository per day; later runs today are not analysed and get no notice."
        )
        _note(results, {}, publisher.check_run(target, analysis_id, CheckOutput(QUOTA_TITLE, summary, text)))
    _record_ops(deps, job, analysis_id, {}, results, publisher.fence)
    return {
        "outcome": "quota_exceeded",
        "quota": quota,
        "notice": "published" if not noticed else "already_today",
        "publications": results,
    }


def _analysis_recorded(deps: AnalyzeDeps, job: AnalysisJob) -> bool:
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        return repo.analysis_recorded(conn, job.installation_id, job.repo_id, job.run_id, job.attempt)


def _run(
    ctx: JobContext,
    deps: AnalyzeDeps,
    job: AnalysisJob,
    rc_a: RepoClient,
    rc_p: RepoClient,
    target: PublishTarget,
    publisher: Publisher,
    is_final: Callable[[], bool],
    deadline: AttemptDeadline,
) -> dict[str, Any]:
    stages = Stages()
    t0 = time.monotonic()
    with collect_evidence(job, rc_a, fetcher=deps.fetcher_factory(), log_max_bytes=deps.log_max_bytes, deadline=deadline) as ev:
        stages.ms["collect"] = int((time.monotonic() - t0) * 1000)
        ctx.check()
        with stages.time("associate"):
            # A work-stage read through the publish client: it runs under the work deadline, so it can never take
            # time from the publication reserve (O-2). Publication afterwards uses the client's own job deadline.
            publish_deadline, rc_p.deadline = rc_p.deadline, deadline
            try:
                assoc, assoc_permission = _associate(rc_p, job)
            finally:
                rc_p.deadline = publish_deadline
        pr_number = assoc.number if assoc.outcome == "matched" else None
        with stages.time("diagnose"):
            try:
                provider = deps.provider_factory()
                # O-5: provider continuation state is bound to this tenant, job and job attempt (and, inside the loop,
                # to this one investigation); it can never be replayed into another.
                rctx = ReplayContext(
                    provider.name,
                    provider.model,
                    installation_id=job.installation_id,
                    job_id=ctx.job.id,
                    attempt=ctx.job.attempts,
                )
                vd = diagnose(ev, provider, limits=deps.limits, pr_number=pr_number, deadline=deadline, replay_context=rctx)
            except ValidationUnavailable:
                # D-B: validation infrastructure, not the answer, failed (after in-place read retries). Retry the
                # attempt (or, on the last one, publish "could not complete"); never judge the answer on it.
                event(log, "analysis.validation_unavailable", logging.WARNING)
                raise RetryableError("validation could not read the code (temporary GitHub failure)") from None
    ctx.check()
    _recheck(deps, job)  # before persisting or publishing anything
    d = vd.diagnosis
    event(
        log,
        "analysis.diagnosed",
        evidence_status=ev.status,
        status=d.status.value,
        category=d.category.value if d.status is Status.diagnosed else None,
        confidence_band=d.confidence.band.value,
        inconclusive_reason=d.inconclusive_reason,
        abstained=d.status is not Status.diagnosed,
        validation_flags=sorted(set(d.validation_flags)),
        validation_flag_count=len(d.validation_flags),
        tool_calls=d.usage.tool_calls,
        tokens_in=d.usage.input_tokens,
        tokens_out=d.usage.output_tokens,
        model_ms=d.usage.latency_ms,
    )
    if d.inconclusive_reason == SOURCE_UNAVAILABLE:
        event(log, "analysis.source_unavailable", logging.WARNING, final=is_final())
    if d.inconclusive_reason in RETRIED_REASONS and not is_final():
        kind = "provider failure" if d.inconclusive_reason in PROVIDER_FAILURES else "infrastructure failure"
        raise RetryableError(f"{kind} ({d.inconclusive_reason})")  # FS-ERR-1: retry ≤2
    if d.inconclusive_reason in RETRIED_REASONS:
        outcome = "could_not_complete"
    elif d.status is Status.logs_unavailable:
        outcome = "logs_unavailable"
    elif d.status is Status.permission_denied:
        outcome = "permission_denied"
    else:
        outcome = d.status.value  # diagnosed | inconclusive

    with stages.time("persist"):
        analysis_id = _persist(deps, job, vd, outcome, publisher.fence)
    return _publish_report(
        deps,
        job,
        target,
        publisher,
        vd,
        outcome,
        analysis_id,
        pr_number,
        assoc_permission,
        stages,
        t0,
        {"association": assoc.outcome, "candidates": list(assoc.candidates)},
    )


def _publish_report(
    deps: AnalyzeDeps,
    job: AnalysisJob,
    target: PublishTarget,
    publisher: Publisher,
    vd: ValidatedDiagnosis,
    outcome: str,
    analysis_id: int,
    pr_number: int | None,
    assoc_permission: str | None,
    stages: Stages,
    t0: float,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Publish a persisted, validated analysis on its surfaces, then write the ops record that marks the publication
    complete. Shared by a fresh analysis and a resumed publication (`_resume_publication`)."""
    t = dataclasses.replace(target, pr_number=pr_number)
    t_pub = time.monotonic()
    missing: dict[str, str | None] = {}
    results: dict[str, str] = {}
    completed = outcome in ("diagnosed", "inconclusive")

    if pr_number is not None:
        _recheck(deps, job)  # D-10(a): before EVERY publication surface
        r = publisher.pr_comment(
            t, analysis_id, render(vd, max_chars=deps.report_max_chars, marker=marker("pr_comment", job.workflow_id))
        )
        _note(results, missing, r)
    elif completed:
        # Push (or D-4: ambiguous/errored association) → the one write-once commit comment (FS-PUB-1).
        _recheck(deps, job)  # D-10(a)
        r = publisher.commit_comment(
            t, analysis_id, render(vd, max_chars=deps.report_max_chars, marker=marker("commit_comment", job.workflow_id))
        )
        _note(results, missing, r)
    if assoc_permission:
        missing["pr_comment"] = assoc_permission
        results["pr_comment"] = "unpublished_permission"
    # Rule 8 (publish.py): a write-once commit comment holding an earlier attempt's report is named on the Check Run.
    superseded = results.get("commit_comment") == "superseded"
    text = publication_notes(render(vd, max_chars=deps.report_max_chars), missing, superseded=superseded)
    _recheck(deps, job)  # D-10(a)
    r = publisher.check_run(t, analysis_id, check_output(vd, text, superseded=superseded))
    _note(results, missing, r)
    stages.ms["publish"] = int((time.monotonic() - t_pub) * 1000)
    stages.ms["total"] = int((time.monotonic() - t0) * 1000)
    _record_ops(deps, job, analysis_id, stages.ms, results, publisher.fence)
    event(log, "analysis.finished", outcome=outcome, stage_ms=stages.ms, publications=results, **extra)
    return {"outcome": outcome, "analysis_id": analysis_id, **extra, "publications": results}


def _resume_publication(
    deps: AnalyzeDeps, job: AnalysisJob, target: PublishTarget, publisher: Publisher, rc_p: RepoClient, job_attempt: int
) -> dict[str, Any] | None:
    """F1/D-14: an earlier attempt of this run attempt (this job, a job it took over, or a dead job an operator
    requeued) persisted a validated analysis whose publication did not complete (no ops record). Publish THAT analysis
    instead of investigating again: no repeated model spend, no divergent second report, and no dependence on the
    work deadline, which a retry after a publication failure has usually passed. None: nothing to resume."""
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        row = repo.pending_publication(conn, job.installation_id, job.repo_id, job.run_id, job.attempt)
    if row is None:
        return None
    try:
        vd = ValidatedDiagnosis.from_record(Diagnosis.model_validate(row["diagnosis"]))
    except (ValidationError, ValueError):
        event(log, "analysis.resume_refused", logging.WARNING, reason="unreadable_record")
        return None  # never published from a record that no longer validates: investigate afresh
    run = vd.diagnosis.run
    if (run.repo_id, run.run_id, run.attempt, run.head_sha) != (job.repo_id, job.run_id, job.attempt, job.head_sha):
        event(log, "analysis.resume_refused", logging.WARNING, reason="record_mismatch")
        return None
    # The report names its PR; publish it only where it still belongs. Association is re-read (publish client, which
    # is this path's only work); a different target than at diagnosis means the stored report is not reused.
    assoc, assoc_permission = _associate(rc_p, job)
    now_pr = assoc.number if assoc.outcome == "matched" else None
    if now_pr != run.pr_number:
        event(log, "analysis.resume_refused", logging.WARNING, reason="association_changed")
        return None
    event(log, "analysis.publication_resumed", logging.WARNING, status=row["status"], job_attempt=job_attempt)
    _recheck(deps, job)
    return _publish_report(
        deps,
        job,
        target,
        publisher,
        vd,
        str(row["status"]),
        int(row["id"]),
        run.pr_number,
        assoc_permission,
        Stages(),
        time.monotonic(),
        {"resumed": True},
    )


def _note(results: dict[str, str], missing: dict[str, str | None], r: PublishResult) -> None:
    results[r.surface] = r.state
    event(log, "publication.result", surface=r.surface, state=r.state, missing_permission=r.missing_permission)
    if r.state == "unpublished_permission":
        missing[r.surface] = r.missing_permission


def _persist(deps: AnalyzeDeps, job: AnalysisJob, vd: ValidatedDiagnosis | None, status: str, fence: Fence | None) -> int:
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        if fence is not None:  # D-1: a stale attempt never overwrites the current attempt's analysis (lock to commit)
            fence.verify(conn, "persist_analysis")
        run_pk = repo.find_workflow_run(
            conn, job.installation_id, job.repo_id, job.run_id, job.attempt
        ) or repo.insert_workflow_run(
            conn,
            installation_id=job.installation_id,
            repo_id=job.repo_id,
            run_id=job.run_id,
            attempt=job.attempt,
            workflow_id=job.workflow_id,
            head_sha=job.head_sha,
            head_branch=job.head_branch,
            head_repo_id=job.head_repo_id,
            event=job.event,
            conclusion=job.conclusion,
        )
        d = vd.verify() if vd else None
        return repo.upsert_analysis(
            conn,
            installation_id=job.installation_id,
            run_pk=run_pk,
            status=status,
            category=d.category.value if d and d.status is Status.diagnosed else None,
            confidence_band=d.confidence.band.value if d else None,
            diagnosis=d.model_dump(mode="json") if d else None,
            provider=d.usage.provider if d else None,
            model=d.usage.model if d else None,
            tokens_in=d.usage.input_tokens if d else None,
            tokens_out=d.usage.output_tokens if d else None,
            latency_ms=d.usage.latency_ms if d else None,
            cost_usd=cost_usd(deps, d.usage.input_tokens, d.usage.output_tokens, vd.usage.cached_input_tokens)
            if vd and d
            else None,
            cached_input_tokens=vd.usage.cached_input_tokens if vd else None,
            reasoning_output_tokens=vd.usage.reasoning_output_tokens if vd else None,
            usage_source=vd.usage.source if vd else None,
        )


def _record_ops(
    deps: AnalyzeDeps,
    job: AnalysisJob,
    analysis_id: int,
    stage_ms: dict[str, int],
    results: dict[str, str],
    fence: Fence | None,
) -> None:
    """AT-OPS-01 record. Publication already happened; a DB fault here must not re-run it, so it is reported, not raised.
    A stale attempt (StaleAttempt) is raised: it must stop, and its numbers must not replace the owner's."""
    try:
        with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
            if fence is not None:
                fence.verify(conn, "record_ops")
            repo.record_analysis_ops(conn, analysis_id, stage_ms, results)
    except DatabaseUnavailable:
        event(log, "analysis.ops_record_failed", logging.ERROR, analysis_id=analysis_id)


def _publish_notice(
    deps: AnalyzeDeps,
    job: AnalysisJob,
    target: PublishTarget,
    publisher: Publisher,
    rc_p: RepoClient,
    status: str,
    permission: str | None,
) -> dict[str, str]:
    """could-not-complete / missing-permission notice: Check Run + PR comment on PRs; never a commit comment."""
    _recheck(deps, job)
    analysis_id = _persist(deps, job, None, status, publisher.fence)
    reason = "permission_denied" if status == "permission_denied" else "internal"

    def body(mark: str | None) -> str:
        return render_could_not_complete(
            job.repo, job.run_id, job.attempt, job.head_sha, reason, marker=mark, permission=permission
        )

    assoc, _ = _associate(rc_p, job)
    results: dict[str, str] = {}
    missing: dict[str, str | None] = {}
    t = target
    if assoc.outcome == "matched" and assoc.number is not None:
        t = dataclasses.replace(target, pr_number=assoc.number)
        _recheck(deps, job)  # D-10(a)
        _note(results, missing, publisher.pr_comment(t, analysis_id, body(marker("pr_comment", job.workflow_id))))
    title = "Missing permission" if status == "permission_denied" else "Could not complete the analysis"
    _recheck(deps, job)  # D-10(a)
    _note(
        results,
        missing,
        publisher.check_run(t, analysis_id, CheckOutput(title, title + ".", publication_notes(body(None), missing))),
    )
    _record_ops(deps, job, analysis_id, {}, results, publisher.fence)
    event(log, "analysis.finished", outcome=status, stage_ms={}, publications=results)
    return results
