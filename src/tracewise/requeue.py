"""Operator re-run of one dead analysis job (I-6), narrow, authenticated and audited.

A dead job blocks its run attempt for good: its UNIQUE dedupe key makes webhook redelivery and the recovery sweep
report `duplicate_run`. A requeue inserts a NEW job row for the same run, linked by its key (`<key>:rerun:<k>`). The
dead row is never modified, so failure history and metrics keep it. The new row has its own id and starts at
attempt 0, so it gets a fresh ownership generation and job deadline; the dead job has no owner, and the attempt
fence (migration 0012) refuses any write from a worker still holding it.

Everything is decided in the database by `tracewise_requeue` (migration 0013), in one transaction:
  * who: the caller must connect with a **personal** login that is a member of `tracewise_operator`; the audit actor
    is `operator:<session_user>` (the authenticated login), never a name typed on the command line;
  * the job exists, is `dead` and of kind `analyze`; its installation is `active`; its repository is enabled, not
    removed and of the same installation;
  * no job for the same run is queued, waiting to retry or running (requeues of one run are serialised by an
    advisory lock, so concurrent operators get one new job and `live_job_exists`);
  * fewer than `tracewise_requeue_max_reruns()` re-runs exist (default 2, PROVISIONAL; changeable only by the schema
    owner, by replacing that function; the value in force is returned and audited);
  * the new job and its content-free `audit_event` commit together, or neither does. A dry run writes nothing.

Not bypassed: the monthly quota gate and publication reconcile run as for any job; an existing commit comment is
never replaced (write-once; the Check Run says so if it differs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import psycopg
from psycopg_pool import ConnectionPool

from tracewise.db.session import Conn, transaction

DEFAULT_MAX_RERUNS = 2  # the function's default; the value in force comes back in every result
REASONS = ("transient_outage", "fixed_configuration", "fixed_permission", "operator_request")

Outcome = Literal[
    "requeued",
    "would_requeue",
    "not_found",
    "not_dead",
    "unsupported_kind",
    "installation_inactive",
    "repository_unavailable",
    "live_job_exists",
    "rerun_limit",
]


class NotAuthorised(Exception):
    """The connection is not a personal `tracewise_operator` login. Carries no job information."""


class OperatorMismatch(Exception):
    """`--operator` named someone other than the authenticated login: refused before anything is read."""


@dataclass(frozen=True)
class RequeueResult:
    outcome: Outcome
    job_id: int
    actor: str
    max_reruns: int
    new_job_id: int | None = None
    rerun: int | None = None

    @property
    def ok(self) -> bool:
        return self.outcome in ("requeued", "would_requeue")

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "job_id": self.job_id,
            "new_job_id": self.new_job_id,
            "rerun": self.rerun,
            "actor": self.actor,
            "max_reruns": self.max_reruns,
        }


def requeue(
    pool: ConnectionPool[Conn], job_id: int, *, reason: str, dry_run: bool = False, operator: str | None = None
) -> RequeueResult:
    """`pool` must connect as the operator's own login. `operator`, when given, is only checked against it."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    try:
        with transaction(pool) as conn:
            if operator is not None:
                who = conn.execute("SELECT session_user AS u").fetchone()
                if who is None or who["u"] != operator:
                    raise OperatorMismatch("--operator does not match the authenticated database login")
            row = conn.execute("SELECT tracewise_requeue(%s, %s, %s) AS r", (job_id, reason, dry_run)).fetchone()
    except psycopg.errors.InsufficientPrivilege:
        raise NotAuthorised("requeue requires a personal database login in tracewise_operator") from None
    assert row is not None
    r = row["r"]
    return RequeueResult(r["outcome"], int(r["job_id"]), r["actor"], int(r["max_reruns"]), r.get("new_job_id"), r.get("rerun"))
