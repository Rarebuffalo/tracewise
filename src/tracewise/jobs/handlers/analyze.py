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
  invalid payload / repo or installation mismatch → PermanentError (dead, no GitHub write)
  unexpected exception              re-raised (retry; never reported as success). On the last attempt a
                                    best-effort "could not complete" notice is published first.
  lease lost                        LeaseLost propagates; nothing further is written
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from tracewise.analysis.collect import collect_evidence
from tracewise.analysis.diagnose import diagnose
from tracewise.context.gitfetch import GitFetcher
from tracewise.contracts import AnalysisJob, Status
from tracewise.db import repositories as repo
from tracewise.db.session import Conn, DatabaseUnavailable, require_tenant_plane, transaction
from tracewise.github import errors as gh_err
from tracewise.github.auth import TokenProvider
from tracewise.github.client import GitHubHTTP, RepoClient
from tracewise.github.publish import Publisher, PublishResult, PublishTarget, marker
from tracewise.github.pulls import PRAssociation, associate_pr
from tracewise.investigate.loop import InvestigationLimits
from tracewise.investigate.provider import Provider
from tracewise.investigate.validate import ValidatedDiagnosis
from tracewise.jobs.queue import JobCancelled, PermanentError, RetryableError
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


def cost_usd(deps: AnalyzeDeps, tokens_in: int, tokens_out: int) -> Decimal | None:
    """Cost from configured prices only; None when either price is unknown (never estimated)."""
    if deps.price_input_per_mtok is None or deps.price_output_per_mtok is None:
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
        return associate_pr(
            rc_p, head_sha=job.head_sha, head_branch=job.head_branch, head_repo_full_name=job.head_repo, is_fork=is_fork
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
    rc_a = RepoClient(
        deps.http, deps.tokens, installation_id=job.installation_id, repo_id=job.repo_id, full_name=job.repo, scope="analysis"
    )
    rc_p = RepoClient(
        deps.http, deps.tokens, installation_id=job.installation_id, repo_id=job.repo_id, full_name=job.repo, scope="publish"
    )
    last_attempt = ctx.job.attempts >= ctx.job.max_attempts
    target = PublishTarget(job.installation_id, job.repo_id, job.repo, job.head_sha, job.run_id, job.attempt, job.workflow_id)
    publisher = Publisher(deps.pool, rc_p, app_id=deps.app_id, check_lease=ctx.check, bot_login=deps.bot_login)
    try:
        return _run(ctx, deps, job, rc_a, rc_p, target, publisher, last_attempt)
    except gh_err.InstallationUnavailable:
        raise JobCancelled("cancelled_uninstalled") from None  # FS-INS-3: token mint refused
    except gh_err.PermissionDenied as e:
        # Must precede PermanentError (its base class). Reading the run itself is forbidden
        # (e.g. Actions: read missing): say so on the remaining surfaces, do not retry (FS-ERR-3).
        res = _publish_notice(deps, job, target, publisher, rc_p, "permission_denied", e.permission)
        return {"outcome": "permission_denied", "publications": res}
    except (LeaseLost, JobCancelled, PermanentError, RetryableError):
        raise
    except Exception:
        if last_attempt:  # FS-ERR-1: tell the user, then still fail the job (never reported as success)
            try:
                _publish_notice(deps, job, target, publisher, rc_p, "could_not_complete", None)
            except Exception:
                # Best effort only: the original error is what gets recorded and retried/failed.
                event(log, "analysis.notice_failed", logging.WARNING)
        raise


def _run(
    ctx: JobContext,
    deps: AnalyzeDeps,
    job: AnalysisJob,
    rc_a: RepoClient,
    rc_p: RepoClient,
    target: PublishTarget,
    publisher: Publisher,
    last_attempt: bool,
) -> dict[str, Any]:
    stages = Stages()
    t0 = time.monotonic()
    with collect_evidence(job, rc_a, fetcher=deps.fetcher_factory(), log_max_bytes=deps.log_max_bytes) as ev:
        stages.ms["collect"] = int((time.monotonic() - t0) * 1000)
        ctx.check()
        with stages.time("associate"):
            assoc, assoc_permission = _associate(rc_p, job)
        pr_number = assoc.number if assoc.outcome == "matched" else None
        with stages.time("diagnose"):
            vd = diagnose(ev, deps.provider_factory(), limits=deps.limits, pr_number=pr_number)
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
    if d.inconclusive_reason in PROVIDER_FAILURES and not last_attempt:
        raise RetryableError(f"provider failure ({d.inconclusive_reason})")  # FS-ERR-1: retry ≤2
    if d.inconclusive_reason in PROVIDER_FAILURES:
        outcome = "could_not_complete"
    elif d.status is Status.logs_unavailable:
        outcome = "logs_unavailable"
    elif d.status is Status.permission_denied:
        outcome = "permission_denied"
    else:
        outcome = d.status.value  # diagnosed | inconclusive

    with stages.time("persist"):
        analysis_id = _persist(deps, job, vd, outcome)
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
    text = publication_notes(render(vd, max_chars=deps.report_max_chars), missing)
    _recheck(deps, job)  # D-10(a)
    r = publisher.check_run(t, analysis_id, check_output(vd, text))
    _note(results, missing, r)
    stages.ms["publish"] = int((time.monotonic() - t_pub) * 1000)
    stages.ms["total"] = int((time.monotonic() - t0) * 1000)
    _record_ops(deps, job, analysis_id, stages.ms, results)
    event(log, "analysis.finished", outcome=outcome, association=assoc.outcome, stage_ms=stages.ms, publications=results)
    return {
        "outcome": outcome,
        "analysis_id": analysis_id,
        "association": assoc.outcome,
        "candidates": list(assoc.candidates),
        "publications": results,
    }


def _note(results: dict[str, str], missing: dict[str, str | None], r: PublishResult) -> None:
    results[r.surface] = r.state
    event(log, "publication.result", surface=r.surface, state=r.state, missing_permission=r.missing_permission)
    if r.state == "unpublished_permission":
        missing[r.surface] = r.missing_permission


def _persist(deps: AnalyzeDeps, job: AnalysisJob, vd: ValidatedDiagnosis | None, status: str) -> int:
    with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
        run_pk = repo.find_workflow_run(conn, job.repo_id, job.run_id, job.attempt) or repo.insert_workflow_run(
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
            cost_usd=cost_usd(deps, d.usage.input_tokens, d.usage.output_tokens) if d else None,
        )


def _record_ops(deps: AnalyzeDeps, job: AnalysisJob, analysis_id: int, stage_ms: dict[str, int], results: dict[str, str]) -> None:
    """AT-OPS-01 record. Publication already happened; a DB fault here must not re-run it, so it is reported, not raised."""
    try:
        with transaction(deps.pool, tenant=job.installation_id) as conn:  # T-705: tenant plane
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
    analysis_id = _persist(deps, job, None, status)
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
    _record_ops(deps, job, analysis_id, {}, results)
    event(log, "analysis.finished", outcome=status, stage_ms={}, publications=results)
    return results
