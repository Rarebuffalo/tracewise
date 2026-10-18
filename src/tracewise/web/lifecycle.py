"""Installation lifecycle webhooks (T-701; FS-INS-3, FS-INS-4, AT-INS-03, AT-INS-04; DECISIONS D-9).

`installation`:  created | unsuspend → active (repositories in the payload are granted);
                 suspend → suspended; deleted → deleted + purge scheduled (7 days, T-704 executes it).
                 deleted, suspend → queued/retry_wait jobs of the installation are cancelled.
`installation_repositories`: added → access granted (removed_at cleared); removed → removed_at set and that
                 repository's pending jobs cancelled. Only repositories owned by the installation are touched.

Rules: the payload is HMAC-authenticated (GitHub-authored) and still schema-validated; each event is applied
in the same transaction as its delivery record, so a duplicate delivery is a no-op; `deleted` is terminal
(installation ids are never reused, so a late `created`/`unsuspend` cannot resurrect it). Out-of-order
suspend/unsuspend cannot be ordered from payloads; GitHub's token mint stays authoritative for in-flight
work (a suspended or uninstalled installation's mint is refused → `cancelled_uninstalled`). Nothing is
published for lifecycle events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field

from tracewise.db import repositories as repo
from tracewise.db.session import Conn, transaction
from tracewise.jobs import queue

FULL_NAME = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class RepoRef(_M):
    id: int = Field(gt=0)
    full_name: str = Field(pattern=FULL_NAME)


class Account(_M):
    login: str = Field(min_length=1, max_length=100)


class InstallationRef(_M):
    id: int = Field(gt=0)
    account: Account | None = None


class InstallationEvent(_M):
    action: Literal["created", "deleted", "suspend", "unsuspend", "new_permissions_accepted"]
    installation: InstallationRef
    repositories: list[RepoRef] = Field(default_factory=list, max_length=5000)


class InstallationRepositoriesEvent(_M):
    action: Literal["added", "removed"]
    installation: InstallationRef
    repositories_added: list[RepoRef] = Field(default_factory=list, max_length=5000)
    repositories_removed: list[RepoRef] = Field(default_factory=list, max_length=5000)


@dataclass
class LifecycleResult:
    outcome: Literal["processed", "duplicate_delivery", "ignored"]
    cancelled_jobs: int = 0
    changes: list[str] = field(default_factory=list)


def process_installation(
    pool: ConnectionPool[Conn], delivery_id: str, ev: InstallationEvent, timeout_s: float = 3.0
) -> LifecycleResult:
    inst = ev.installation.id
    with transaction(pool, timeout_s) as conn:
        if not repo.insert_delivery(conn, delivery_id, "installation", ev.action, inst, "processed"):
            return LifecycleResult("duplicate_delivery")
        res = LifecycleResult("processed")
        login = ev.installation.account.login if ev.installation.account else None
        if ev.action in ("created", "unsuspend"):
            if repo.set_installation_status(conn, inst, "active", login):
                res.changes.append(f"installation:{ev.action}")
                for r in ev.repositories:
                    repo.repository_added(conn, r.id, inst, r.full_name)
                res.changes.extend(f"repo_added:{r.id}" for r in ev.repositories)
            else:
                res.changes.append("ignored:installation_deleted")  # no resurrection
        elif ev.action == "suspend":
            if repo.set_installation_status(conn, inst, "suspended", login):
                res.changes.append("installation:suspended")
            res.cancelled_jobs = queue.cancel_pending(conn, installation_id=inst, reason="installation_suspended")
        elif ev.action == "deleted":
            repo.mark_installation_deleted(conn, inst)
            res.changes.append("installation:deleted;purge_scheduled")
            res.cancelled_jobs = queue.cancel_pending(conn, installation_id=inst, reason="cancelled_uninstalled")
        else:
            repo.set_delivery_outcome(conn, delivery_id, "ignored", None)
            return LifecycleResult("ignored")
        repo.audit(
            conn,
            "github",
            f"installation.{ev.action}",
            inst,
            cancelled_jobs=res.cancelled_jobs,
            repositories=len(ev.repositories),
        )
        return res


def process_installation_repositories(
    pool: ConnectionPool[Conn], delivery_id: str, ev: InstallationRepositoriesEvent, timeout_s: float = 3.0
) -> LifecycleResult:
    inst = ev.installation.id
    with transaction(pool, timeout_s) as conn:
        if not repo.insert_delivery(conn, delivery_id, "installation_repositories", ev.action, inst, "processed"):
            return LifecycleResult("duplicate_delivery")
        res = LifecycleResult("processed")
        status = repo.installation_status(conn, inst)
        if status == "deleted":
            res.changes.append("ignored:installation_deleted")
        elif ev.action == "added":
            if status is None:
                repo.set_installation_status(conn, inst, "active", None)
            for r in ev.repositories_added:
                repo.repository_added(conn, r.id, inst, r.full_name)
                res.changes.append(f"repo_added:{r.id}")
        else:
            for r in ev.repositories_removed:
                if repo.repository_removed(conn, r.id, inst):
                    res.changes.append(f"repo_removed:{r.id}")
                    res.cancelled_jobs += queue.cancel_pending(
                        conn, installation_id=inst, repo_id=r.id, reason="repo_not_in_scope"
                    )
        repo.audit(
            conn,
            "github",
            f"installation_repositories.{ev.action}",
            inst,
            cancelled_jobs=res.cancelled_jobs,
            repositories=len(ev.repositories_added) + len(ev.repositories_removed),
        )
        return res
