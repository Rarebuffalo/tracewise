"""GitHub publication: commit comment, PR comment, neutral Check Run (T-502; FS-PUB-1..5, FS-ERR-3).

Identity (one row in `publication`, UNIQUE (surface, target_key)):
  commit_comment  repo:head_sha:workflow   write-once (DB trigger); never edited: GitHub allows editing a commit
                                           comment only with Contents **write**, which the App does not request
  pr_comment      repo:pr<N>:workflow      upserted; found by hidden marker + our App as author
  check_run       repo:run_id              upserted; `external_id=run_id`, looked up by name, always `neutral`

Idempotency, concurrency and reconciliation (per call):
  1. `SELECT … FOR UPDATE` on the publication row inside one DB transaction that spans the GitHub call,
     so two workers publishing the same target serialise; the second sees the first's result.
  2. Stale guard: a row written by a newer (run_id, attempt) is never overwritten by an older one.
  3. Unchanged content (same digest, already published) → no write.
  4. The job's lease is checked immediately before every external write.
  5. **Reconcile before create:** if the row has no GitHub id, list the surface on GitHub and adopt our
     own existing object (marker + App id, or `external_id` for check runs). This covers a crash or DB
     failure after GitHub accepted a write but before the row committed.
  6. 403 → `unpublished_permission` (+ the permission) is committed and returned; other surfaces go on.
     Transient errors propagate (the transaction rolls back) and the job retries with backoff.
  7. Reconcile to the latest attempt (job takeover or retry, i.e. ownership generation > 1): a request of an older
     generation may have reached GitHub after its last ownership check without being recorded, so the stored
     digest no longer proves what GitHub shows. On such an attempt PR comments and Check Runs are rewritten even
     when the digest is unchanged (`reconciled`).
  8. The commit comment cannot be rewritten. If the existing one (recorded, or adopted from GitHub) carries text
     other than this attempt's report, it is kept, the row records what GitHub actually shows, the result is
     `superseded`, and the caller says so on the Check Run, which always carries the current report.
  9. (O-2) Every request runs within the publish client's deadline: the job deadline. A write that cannot start in
     time is `publication.not_started` (nothing sent, row unpublished); one cut mid-flight is `outcome_uncertain`.
Remaining window (documented, not "exactly once"): between the check in (4)/(5) and GitHub applying the
write, a concurrent writer outside this row lock (e.g. a person, or a second deployment against another
database) could still create a duplicate. Within one database, duplicates are prevented by (1) + (5).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from psycopg_pool import ConnectionPool

from tracewise.context.paths import validate_owner_repo, validate_sha
from tracewise.db import repositories as repo
from tracewise.db.session import Conn, transaction
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient
from tracewise.jobs.queue import Fence, PermanentError
from tracewise.observe import event
from tracewise.report.render import CheckOutput

log = logging.getLogger(__name__)

CHECK_NAME = "Tracewise"
Surface = Literal["commit_comment", "pr_comment", "check_run"]
SURFACE_SCOPE: dict[Surface, str] = {
    "commit_comment": "publish_commit",
    "pr_comment": "publish_pr",
    "check_run": "publish_checks",
}
State = Literal[
    "published",
    "updated",
    "adopted",
    "reconciled",
    "unchanged",
    "stale",
    "already_published",
    "superseded",
    "unpublished_permission",
]


@dataclass(frozen=True)
class PublishTarget:
    installation_id: int
    repo_id: int
    repo: str
    head_sha: str
    run_id: int
    attempt: int
    workflow_id: int | None
    pr_number: int | None = None

    def check(self, rc: RepoClient) -> None:
        """Refuse any target outside the client's installation/repository binding."""
        validate_owner_repo(self.repo)
        validate_sha(self.head_sha)
        if rc.scope != "publish":
            raise ValueError("publication needs the publish-scope client")
        if (rc.installation_id, rc.repo_id, rc.full_name.lower()) != (self.installation_id, self.repo_id, self.repo.lower()):
            raise ValueError("publication target does not match the client's installation and repository")
        if self.run_id <= 0 or self.attempt <= 0 or (self.pr_number is not None and self.pr_number <= 0):
            raise ValueError("invalid publication identifiers")


@dataclass(frozen=True)
class PublishResult:
    surface: Surface
    state: State
    github_id: int | None = None
    missing_permission: str | None = None


def marker(surface: Surface, workflow_id: int | None) -> str:
    return f"{'cc' if surface == 'commit_comment' else 'pr'}:wf{workflow_id or 0}"


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


def _same_text(a: str, b: str) -> bool:
    """GitHub may normalise line endings or trailing whitespace of a stored body."""
    return a.replace("\r\n", "\n").rstrip() == b.replace("\r\n", "\n").rstrip()


class Publisher:
    def __init__(
        self,
        pool: ConnectionPool[Conn],
        rc: RepoClient,
        *,
        app_id: int,
        check_lease: Callable[[], None],
        bot_login: str | None = None,
        fence: Fence | None = None,
    ) -> None:
        self.pool, self.rc, self.app_id, self.check_lease, self.bot_login = pool, rc, app_id, check_lease, bot_login
        # G-PLAT-11: each surface uses its own token (only the permission that surface needs), so a declined
        # permission blocks that surface alone; the others still publish and the Check Run names what is missing.
        self._clients: dict[Surface, RepoClient] = {s: rc.for_scope(scope) for s, scope in SURFACE_SCOPE.items()}
        # D-1/D-2: the job attempt this publisher acts for. None only outside a job (direct tests of the publisher).
        self.fence = fence

    def _owned(self, conn: Conn, stage: str, *, lock: bool) -> None:
        """Database ownership check in the publication transaction. `lock=False` right before a GitHub request (no
        row lock across the network call); `lock=True` right before the publication row is marked, held to commit,
        so a stale attempt can never record a publication even if its request reached GitHub."""
        if self.fence is not None:
            self.fence.verify(conn, stage, lock=lock)

    @property
    def _reconciling(self) -> bool:
        """A later generation of the job: an older one may have written to GitHub without recording it (rule 7)."""
        return self.fence is not None and self.fence.attempt > 1

    def _send(self, conn: Conn, surface: Surface, operation: str, **kw: Any) -> Any:
        """One external write: local lease flag, unlocked ownership check, then the request. A transient failure
        leaves the outcome unknown (GitHub may have applied it); the next attempt reconciles (rules 5, 7)."""
        self.check_lease()
        self._owned(conn, surface, lock=False)
        event(log, "publication.attempted", surface=surface, operation=operation)
        try:
            return self._clients[surface].request(operation, **kw)
        except gh_err.DeadlineExhausted as e:
            if e.sent:  # an earlier try of this call went out: as uncertain as a timeout
                event(log, "publication.outcome_uncertain", logging.WARNING, surface=surface, operation=operation)
            else:  # O-2: nothing was sent, so nothing can have been applied; the row stays unpublished
                event(log, "publication.not_started", logging.WARNING, surface=surface, operation=operation, reason="deadline")
            raise
        except gh_err.GitHubRetryable:
            event(log, "publication.outcome_uncertain", logging.WARNING, surface=surface, operation=operation)
            raise

    # ------------------------------------------------------------ surfaces

    def commit_comment(self, t: PublishTarget, analysis_id: int, body: str) -> PublishResult:
        t.check(self.rc)
        key = repo.commit_comment_key(t.repo_id, t.head_sha, t.workflow_id)
        tag = marker("commit_comment", t.workflow_id)
        digest = _digest(body)
        with self._row(t, "commit_comment", key, analysis_id) as (conn, row):
            if row["state"] == "published":  # FS-PUB-1/4: write-once
                if row["content_digest"] not in (None, digest):
                    return self._superseded(row["github_id"], adopted=False)  # rule 8: an earlier attempt's report
                return PublishResult("commit_comment", "already_published", row["github_id"])
            try:
                found = self._find_comment("commit_comment", "list_commit_comments", tag, sha=t.head_sha)
                if found is not None:
                    gid, shown = found
                    state: State = "adopted" if _same_text(shown, body) else "superseded"
                    shown_digest = digest if state == "adopted" else _digest(shown)  # what GitHub actually shows
                else:
                    gid = self._id(
                        self._send(conn, "commit_comment", "create_commit_comment", sha=t.head_sha, json_body={"body": body})
                    )
                    state, shown_digest = "published", digest
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "commit_comment", e)
            self._owned(conn, "mark_published", lock=True)
            repo.mark_published(
                conn, row["id"], analysis_id, gid, source_run_id=t.run_id, source_attempt=t.attempt, content_digest=shown_digest
            )
        if state == "superseded":
            return self._superseded(gid, adopted=True)
        return PublishResult("commit_comment", state, gid)

    def pr_comment(self, t: PublishTarget, analysis_id: int, body: str) -> PublishResult:
        t.check(self.rc)
        if t.pr_number is None:
            raise ValueError("pr_comment needs a validated PR number")
        key = repo.pr_comment_key(t.repo_id, t.pr_number, t.workflow_id)
        tag = marker("pr_comment", t.workflow_id)
        digest = _digest(body)
        with self._row(t, "pr_comment", key, analysis_id) as (conn, row):
            if (early := self._skip(row, t, digest, "pr_comment")) is not None:
                return early
            try:
                gid = row["github_id"] if row["state"] == "published" else None
                adopted = False
                if gid is None:
                    found = self._find_comment("pr_comment", "list_pr_comments", tag, number=t.pr_number)
                    gid, adopted = (found[0], True) if found is not None else (None, False)
                state: State
                if gid is not None:
                    try:
                        self._send(conn, "pr_comment", "update_pr_comment", comment_id=gid, json_body={"body": body})
                        state = self._updated_state(row, digest, adopted, "pr_comment")
                    except gh_err.NotFound:  # deleted by a person: recreate
                        gid = None
                if gid is None:
                    gid = self._id(
                        self._send(conn, "pr_comment", "create_pr_comment", number=t.pr_number, json_body={"body": body})
                    )
                    state = "published"
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "pr_comment", e)
            self._owned(conn, "mark_published", lock=True)
            repo.mark_published(
                conn, row["id"], analysis_id, gid, source_run_id=t.run_id, source_attempt=t.attempt, content_digest=digest
            )
            return PublishResult("pr_comment", state, gid)

    def check_run(self, t: PublishTarget, analysis_id: int, out: CheckOutput) -> PublishResult:
        t.check(self.rc)
        key = repo.check_run_key(t.repo_id, t.run_id)
        output = {"title": out.title, "summary": out.summary, "text": out.text, "annotations": list(out.annotations)}
        digest = _digest(out.title, out.summary, out.text, repr(out.annotations))
        fields = {"name": CHECK_NAME, "status": "completed", "conclusion": "neutral", "output": output}  # never gating
        with self._row(t, "check_run", key, analysis_id) as (conn, row):
            if (early := self._skip(row, t, digest, "check_run")) is not None:
                return early
            try:
                gid = row["github_id"] if row["state"] == "published" else None
                adopted = False
                if gid is None:
                    gid = self._find_check_run(t)
                    adopted = gid is not None
                state: State
                if gid is not None:
                    try:
                        self._send(conn, "check_run", "update_check_run", check_run_id=gid, json_body=fields)
                        state = self._updated_state(row, digest, adopted, "check_run")
                    except gh_err.NotFound:
                        gid = None
                if gid is None:
                    gid = self._id(
                        self._send(
                            conn,
                            "check_run",
                            "create_check_run",
                            json_body={**fields, "head_sha": t.head_sha, "external_id": str(t.run_id)},
                        )
                    )
                    state = "published"
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "check_run", e)
            self._owned(conn, "mark_published", lock=True)
            repo.mark_published(
                conn, row["id"], analysis_id, gid, source_run_id=t.run_id, source_attempt=t.attempt, content_digest=digest
            )
            return PublishResult("check_run", state, gid)

    # ------------------------------------------------------------ internals

    @contextmanager
    def _row(self, t: PublishTarget, surface: Surface, key: str, analysis_id: int) -> Iterator[tuple[Conn, dict[str, Any]]]:
        with transaction(self.pool, tenant=t.installation_id) as conn:  # T-705: tenant plane
            try:
                row = repo.reserve_publication(
                    conn, installation_id=t.installation_id, analysis_id=analysis_id, surface=surface, target_key=key
                )
            except repo.PublicationNotVisible:
                raise PermanentError(f"{surface} reservation is not visible to this installation") from None
            yield conn, row

    def _skip(self, row: dict[str, Any], t: PublishTarget, digest: str, surface: Surface) -> PublishResult | None:
        if row["source_run_id"] is not None and (row["source_run_id"], row["source_attempt"] or 0) > (t.run_id, t.attempt):
            return PublishResult(surface, "stale", row["github_id"])  # a newer attempt already wrote this surface
        if row["state"] == "published" and row["content_digest"] == digest and not self._reconciling:
            return PublishResult(surface, "unchanged", row["github_id"])  # rule 3; never trusted on a later generation
        return None

    def _updated_state(self, row: dict[str, Any], digest: str, adopted: bool, surface: Surface) -> State:
        state: State = "adopted" if adopted else ("reconciled" if row["content_digest"] == digest else "updated")
        if self._reconciling:
            event(
                log, "publication.reconciled", surface=surface, generation=self.fence.attempt if self.fence else None, state=state
            )
        return state

    def _superseded(self, gid: int | None, *, adopted: bool) -> PublishResult:
        """Rule 8: the write-once commit comment shows an earlier attempt's report and cannot be edited here."""
        event(log, "publication.superseded_retained", logging.WARNING, surface="commit_comment", adopted=adopted)
        return PublishResult("commit_comment", "superseded", gid)

    def _unpublished(self, conn: Conn, row: dict[str, Any], surface: Surface, e: gh_err.PermissionDenied) -> PublishResult:
        self._owned(conn, "mark_unpublished", lock=True)
        repo.mark_unpublished_permission(conn, row["id"], e.permission)
        event(log, "publication.permission_refused", logging.WARNING, surface=surface, permission=e.permission)
        return PublishResult(surface, "unpublished_permission", None, e.permission)

    def _ours(self, obj: dict[str, Any]) -> bool:
        app = obj.get("performed_via_github_app") or obj.get("app") or {}
        if isinstance(app, dict) and app.get("id") == self.app_id:
            return True
        user = obj.get("user") or {}
        return bool(self.bot_login) and isinstance(user, dict) and user.get("login") == self.bot_login

    def _find_comment(self, surface: Surface, endpoint: str, tag: str, **params: Any) -> tuple[int, str] | None:
        """Our existing comment as (id, body). Only the FIRST line identifies a report: the renderer writes the marker
        there, while log excerpts and snippets further down are untrusted and may contain any marker text (A4)."""
        needle = f"<!-- tracewise:{tag} -->"
        for c in self._clients[surface].paginate(endpoint, None, **params):
            body = str(c.get("body") or "") if isinstance(c, dict) else ""
            if body.split("\n", 1)[0] == needle and self._ours(c) and isinstance(c.get("id"), int):
                return int(c["id"]), body
        return None

    def _find_check_run(self, t: PublishTarget) -> int | None:
        checks = self._clients["check_run"]
        for c in checks.paginate("list_check_runs_for_ref", "check_runs", ref=t.head_sha, query={"check_name": CHECK_NAME}):
            if (
                isinstance(c, dict)
                and c.get("external_id") == str(t.run_id)
                and c.get("name") == CHECK_NAME
                and self._ours(c)
                and isinstance(c.get("id"), int)
            ):
                return int(c["id"])
        return None

    @staticmethod
    def _id(doc: Any) -> int:
        if not isinstance(doc, dict) or not isinstance(doc.get("id"), int) or isinstance(doc.get("id"), bool):
            raise gh_err.GitHubPermanent("publication response has no object id")
        return int(doc["id"])
