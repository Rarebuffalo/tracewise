"""Postgres job queue (T-105; FS-EVT-2, FS-EVT-4, FS-EVT-6, FS-ERR-1, FS-ERR-2).

State machine (enforced by guarded UPDATEs and table CHECKs):

    queued ──claim──▶ running ──complete──▶ succeeded
                        │ ├──fail(retryable, attempts left, before deadline)──▶ retry_wait ──claim──▶ running
                        │ └──fail(permanent | attempts/deadline exhausted)──────▶ dead
                        └──lease expired──▶ retry_wait | dead   (reaped at the next claim)
    queued | retry_wait ──cancel──▶ cancelled
    running ──cancel_running (owner only; JobCancelled no-op)──▶ cancelled

Every transition out of `running` is guarded by `locked_by = <worker>`, so a worker that
lost its lease can never overwrite the outcome of the worker that reclaimed the job.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from psycopg.types.json import Jsonb

from tracewise.db.repositories import short_error
from tracewise.db.session import Conn

JobStatus = Literal["queued", "running", "retry_wait", "succeeded", "dead", "cancelled"]
TERMINAL: frozenset[str] = frozenset({"succeeded", "dead", "cancelled"})

DEFAULT_LEASE_S = 120
PER_INSTALLATION_CAP = 2  # FS-EVT-6
JOB_DEADLINE_S = 600  # FS-ERR-2: 10 minutes from the first claim
BACKOFF_BASE_S = 30.0
BACKOFF_MAX_S = 300.0
_CLAIM_LOCK = 0x7472_6163  # advisory lock id serialising claims, so the per-installation cap is exact


class RetryableError(Exception):
    """Transient failure: retried with backoff while attempts and the deadline allow.
    `retry_after_s` honours `retry-after` / `x-ratelimit-reset` (FS-ERR-2)."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class PermanentError(Exception):
    """Failure that retrying cannot fix (e.g. 403 missing permission, invalid payload)."""


class JobCancelled(Exception):
    """Controlled no-op: the job must not run (e.g. app uninstalled, repository disabled). Not a failure."""


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    installation_id: int
    run_key: str | None
    dedupe_key: str
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    locked_by: str | None
    locked_until: datetime | None
    deadline_at: datetime | None
    last_error: str | None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> Job:
        return cls(**{k: r[k] for k in cls.__dataclass_fields__})


def backoff_s(attempts: int, retry_after_s: float | None = None, rnd: random.Random | None = None) -> float:
    """Exponential (30 s, 120 s, ...) with ±20% jitter, capped; never shorter than the server's retry-after."""
    base = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 4 ** max(0, attempts - 1))
    jitter = (rnd or random).uniform(0.8, 1.2)
    return float(max(base * jitter, retry_after_s or 0.0))


def enqueue(
    conn: Conn,
    *,
    kind: str,
    installation_id: int,
    dedupe_key: str,
    payload: dict[str, Any],
    run_key: str | None = None,
    max_attempts: int = 3,
    delay_s: float = 0,
) -> int | None:
    """Insert a job unless `dedupe_key` exists. Returns the new id, or None for a duplicate."""
    row = conn.execute(
        """INSERT INTO job (kind, installation_id, run_key, dedupe_key, payload, max_attempts, run_after)
           VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(secs => %s))
           ON CONFLICT (dedupe_key) DO NOTHING RETURNING id""",
        (kind, installation_id, run_key, dedupe_key, Jsonb(payload), max_attempts, delay_s),
    ).fetchone()
    return int(row["id"]) if row else None


def reap_expired(conn: Conn) -> int:
    """Running jobs whose lease expired (crashed or partitioned worker) go back to retry_wait,
    or to dead when attempts or the deadline are exhausted."""
    cur = conn.execute(
        """UPDATE job SET
               status = CASE WHEN attempts >= max_attempts OR deadline_at <= now() THEN 'dead' ELSE 'retry_wait' END,
               finished_at = CASE WHEN attempts >= max_attempts OR deadline_at <= now() THEN now() END,
               last_error = 'lease expired', locked_by = NULL, locked_until = NULL, run_after = now(), updated_at = now()
           WHERE status = 'running' AND locked_until < now()"""
    )
    return cur.rowcount


def claim(
    conn: Conn, worker_id: str, *, lease_s: int = DEFAULT_LEASE_S, per_installation: int = PER_INSTALLATION_CAP
) -> Job | None:
    """Claim the oldest ready job, respecting ≤N running per installation and one running job per run.
    Must be called inside a transaction; the job is `running` once it commits."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_CLAIM_LOCK,))
    reap_expired(conn)
    conn.execute(
        """UPDATE job SET status = 'dead', finished_at = now(), last_error = 'deadline exceeded', updated_at = now()
           WHERE status IN ('queued', 'retry_wait') AND deadline_at <= now()"""
    )
    row = conn.execute(
        """SELECT j.id FROM job j
           WHERE j.status IN ('queued', 'retry_wait') AND j.run_after <= now()
             AND (SELECT count(*) FROM job r WHERE r.status = 'running' AND r.installation_id = j.installation_id) < %s
             AND (j.run_key IS NULL OR NOT EXISTS (
                     SELECT 1 FROM job r WHERE r.status = 'running' AND r.run_key = j.run_key))
           ORDER BY j.run_after, j.id
           LIMIT 1 FOR UPDATE SKIP LOCKED""",
        (per_installation,),
    ).fetchone()
    if row is None:
        return None
    claimed = conn.execute(
        """UPDATE job SET status = 'running', attempts = attempts + 1, locked_by = %s,
               locked_until = now() + make_interval(secs => %s),
               deadline_at = COALESCE(deadline_at, now() + make_interval(secs => %s)), updated_at = now()
           WHERE id = %s RETURNING *""",
        (worker_id, lease_s, JOB_DEADLINE_S, row["id"]),
    ).fetchone()
    assert claimed is not None
    return Job.from_row(claimed)


def heartbeat(conn: Conn, job_id: int, worker_id: str, lease_s: int = DEFAULT_LEASE_S) -> bool:
    """Extend the lease. False means the lease was lost: the worker must stop and not publish."""
    cur = conn.execute(
        """UPDATE job SET locked_until = now() + make_interval(secs => %s), updated_at = now()
           WHERE id = %s AND status = 'running' AND locked_by = %s AND locked_until >= now()""",
        (lease_s, job_id, worker_id),
    )
    return cur.rowcount == 1


def complete(conn: Conn, job_id: int, worker_id: str, result: dict[str, Any] | None = None) -> bool:
    cur = conn.execute(
        """UPDATE job SET status = 'succeeded', result = %s, finished_at = now(), locked_by = NULL, locked_until = NULL,
               last_error = NULL, updated_at = now()
           WHERE id = %s AND status = 'running' AND locked_by = %s""",
        (Jsonb(result or {}), job_id, worker_id),
    )
    return cur.rowcount == 1


def fail(conn: Conn, job_id: int, worker_id: str, error: BaseException, *, rnd: random.Random | None = None) -> JobStatus | None:
    """Record a failure. Returns the new status, or None if this worker no longer owns the job."""
    row = conn.execute(
        "SELECT attempts, max_attempts, deadline_at, now() AS now FROM job"
        " WHERE id = %s AND status = 'running' AND locked_by = %s FOR UPDATE",
        (job_id, worker_id),
    ).fetchone()
    if row is None:
        return None
    msg = f"{type(error).__name__}: {short_error(error, 400)}"
    retryable = not isinstance(error, PermanentError)
    delay = backoff_s(row["attempts"], getattr(error, "retry_after_s", None), rnd)
    deadline_ok = row["deadline_at"] is None or (row["now"].timestamp() + delay) < row["deadline_at"].timestamp()
    if retryable and row["attempts"] < row["max_attempts"] and deadline_ok:
        conn.execute(
            """UPDATE job SET status = 'retry_wait', run_after = now() + make_interval(secs => %s), last_error = %s,
                   locked_by = NULL, locked_until = NULL, updated_at = now() WHERE id = %s""",
            (delay, msg, job_id),
        )
        return "retry_wait"
    reason = "permanent" if not retryable else ("attempts exhausted" if deadline_ok else "deadline exceeded")
    conn.execute(
        """UPDATE job SET status = 'dead', last_error = %s, finished_at = now(), locked_by = NULL, locked_until = NULL,
               updated_at = now() WHERE id = %s""",
        (f"{reason}; {msg}"[:500], job_id),
    )
    return "dead"


def cancel(conn: Conn, job_id: int) -> bool:
    cur = conn.execute(
        """UPDATE job SET status = 'cancelled', finished_at = now(), updated_at = now()
           WHERE id = %s AND status IN ('queued', 'retry_wait')""",
        (job_id,),
    )
    return cur.rowcount == 1


def cancel_pending(conn: Conn, *, installation_id: int, reason: str, repo_id: int | None = None) -> int:
    """Cancel queued/retry_wait jobs of an installation (or one of its repositories). Running jobs are left to
    their lease owner, which re-checks scope before any GitHub write (T-701)."""
    if repo_id is None:
        cur = conn.execute(
            """UPDATE job SET status = 'cancelled', finished_at = now(), last_error = %s, updated_at = now()
               WHERE installation_id = %s AND status IN ('queued', 'retry_wait')""",
            (short_error(reason, 200), installation_id),
        )
    else:
        cur = conn.execute(
            """UPDATE job SET status = 'cancelled', finished_at = now(), last_error = %s, updated_at = now()
               WHERE installation_id = %s AND status IN ('queued', 'retry_wait') AND (payload->>'repo_id')::bigint = %s""",
            (short_error(reason, 200), installation_id, repo_id),
        )
    return cur.rowcount


def cancel_running(conn: Conn, job_id: int, worker_id: str, reason: str) -> bool:
    """running → cancelled, only by the lease owner (FS-INS-3 `cancelled_uninstalled`, disabled repositories)."""
    cur = conn.execute(
        """UPDATE job SET status = 'cancelled', finished_at = now(), locked_by = NULL, locked_until = NULL,
               last_error = %s, updated_at = now()
           WHERE id = %s AND status = 'running' AND locked_by = %s""",
        (short_error(reason, 200), job_id, worker_id),
    )
    return cur.rowcount == 1


def get(conn: Conn, job_id: int) -> Job | None:
    row = conn.execute("SELECT * FROM job WHERE id = %s", (job_id,)).fetchone()
    return Job.from_row(row) if row else None


def counts(conn: Conn) -> dict[str, int]:
    return {r["status"]: int(r["n"]) for r in conn.execute("SELECT status, count(*) AS n FROM job GROUP BY status")}
