"""GitHub publication: commit comment, PR comment, neutral Check Run (T-502; FS-PUB-1..5, FS-ERR-3).

Identity (one row in `publication`, UNIQUE (surface, target_key)):
  commit_comment  repo:head_sha:workflow   write-once (DB trigger); never edited (no Contents write)
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
from tracewise.observe import event
from tracewise.report.render import CheckOutput

log = logging.getLogger(__name__)

CHECK_NAME = "Tracewise"
Surface = Literal["commit_comment", "pr_comment", "check_run"]
State = Literal["published", "updated", "adopted", "unchanged", "stale", "already_published", "unpublished_permission"]


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


class Publisher:
    def __init__(
        self,
        pool: ConnectionPool[Conn],
        rc: RepoClient,
        *,
        app_id: int,
        check_lease: Callable[[], None],
        bot_login: str | None = None,
    ) -> None:
        self.pool, self.rc, self.app_id, self.check_lease, self.bot_login = pool, rc, app_id, check_lease, bot_login

    # ------------------------------------------------------------ surfaces

    def commit_comment(self, t: PublishTarget, analysis_id: int, body: str) -> PublishResult:
        t.check(self.rc)
        key = repo.commit_comment_key(t.repo_id, t.head_sha, t.workflow_id)
        tag = marker("commit_comment", t.workflow_id)
        with self._row(t, "commit_comment", key, analysis_id) as (conn, row):
            if row["state"] == "published":
                return PublishResult("commit_comment", "already_published", row["github_id"])  # FS-PUB-1/4
            try:
                found = self._find_comment("list_commit_comments", tag, sha=t.head_sha)
                if found is not None:
                    state: State = "adopted"
                    gid = found
                else:
                    self.check_lease()
                    gid = self._id(self.rc.request("create_commit_comment", sha=t.head_sha, json_body={"body": body}))
                    state = "published"
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "commit_comment", e)
            repo.mark_published(
                conn, row["id"], analysis_id, gid, source_run_id=t.run_id, source_attempt=t.attempt, content_digest=_digest(body)
            )
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
                    gid = self._find_comment("list_pr_comments", tag, number=t.pr_number)
                    adopted = gid is not None
                state: State
                if gid is not None:
                    try:
                        self.check_lease()
                        self.rc.request("update_pr_comment", comment_id=gid, json_body={"body": body})
                        state = "adopted" if adopted else "updated"
                    except gh_err.NotFound:  # deleted by a person: recreate
                        gid = None
                if gid is None:
                    self.check_lease()
                    gid = self._id(self.rc.request("create_pr_comment", number=t.pr_number, json_body={"body": body}))
                    state = "published"
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "pr_comment", e)
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
                        self.check_lease()
                        self.rc.request("update_check_run", check_run_id=gid, json_body=fields)
                        state = "adopted" if adopted else "updated"
                    except gh_err.NotFound:
                        gid = None
                if gid is None:
                    self.check_lease()
                    gid = self._id(
                        self.rc.request(
                            "create_check_run", json_body={**fields, "head_sha": t.head_sha, "external_id": str(t.run_id)}
                        )
                    )
                    state = "published"
            except gh_err.PermissionDenied as e:
                return self._unpublished(conn, row, "check_run", e)
            repo.mark_published(
                conn, row["id"], analysis_id, gid, source_run_id=t.run_id, source_attempt=t.attempt, content_digest=digest
            )
            return PublishResult("check_run", state, gid)

    # ------------------------------------------------------------ internals

    @contextmanager
    def _row(self, t: PublishTarget, surface: Surface, key: str, analysis_id: int) -> Iterator[tuple[Conn, dict[str, Any]]]:
        with transaction(self.pool, tenant=t.installation_id) as conn:  # T-705: tenant plane
            row = repo.reserve_publication(
                conn, installation_id=t.installation_id, analysis_id=analysis_id, surface=surface, target_key=key
            )
            yield conn, row

    @staticmethod
    def _skip(row: dict[str, Any], t: PublishTarget, digest: str, surface: Surface) -> PublishResult | None:
        if row["source_run_id"] is not None and (row["source_run_id"], row["source_attempt"] or 0) > (t.run_id, t.attempt):
            return PublishResult(surface, "stale", row["github_id"])  # a newer attempt already wrote this surface
        if row["state"] == "published" and row["content_digest"] == digest:
            return PublishResult(surface, "unchanged", row["github_id"])
        return None

    def _unpublished(self, conn: Conn, row: dict[str, Any], surface: Surface, e: gh_err.PermissionDenied) -> PublishResult:
        repo.mark_unpublished_permission(conn, row["id"], e.permission)
        event(log, "publication.permission_refused", logging.WARNING, surface=surface, permission=e.permission)
        return PublishResult(surface, "unpublished_permission", None, e.permission)

    def _ours(self, obj: dict[str, Any]) -> bool:
        app = obj.get("performed_via_github_app") or obj.get("app") or {}
        if isinstance(app, dict) and app.get("id") == self.app_id:
            return True
        user = obj.get("user") or {}
        return bool(self.bot_login) and isinstance(user, dict) and user.get("login") == self.bot_login

    def _find_comment(self, endpoint: str, tag: str, **params: Any) -> int | None:
        needle = f"<!-- tracewise:{tag} -->"
        for c in self.rc.paginate(endpoint, None, **params):
            if isinstance(c, dict) and needle in str(c.get("body") or "") and self._ours(c) and isinstance(c.get("id"), int):
                return int(c["id"])
        return None

    def _find_check_run(self, t: PublishTarget) -> int | None:
        for c in self.rc.paginate("list_check_runs_for_ref", "check_runs", ref=t.head_sha, query={"check_name": CHECK_NAME}):
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
