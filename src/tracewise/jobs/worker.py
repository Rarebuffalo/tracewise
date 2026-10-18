"""Worker loop (T-105): claim → handle → complete/fail, with lease heartbeats.

Handlers must be idempotent: a job can run more than once (lease expiry after a crash,
or a lost `complete` because the database failed). Publication uniqueness (T-104) is what
makes re-runs safe for GitHub side effects.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from psycopg_pool import ConnectionPool

from tracewise.db.session import Conn, DatabaseUnavailable, transaction
from tracewise.jobs import queue
from tracewise.jobs.queue import Job, JobCancelled, PermanentError
from tracewise.logging import correlation_id
from tracewise.observe import bind, event

log = logging.getLogger(__name__)


@dataclass
class JobContext:
    job: Job
    lease_lost: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)

    def check(self) -> None:
        """Handlers call this before side effects (e.g. publishing); raises if the lease was lost."""
        if self.lease_lost.is_set():
            raise LeaseLost(f"job {self.job.id}: lease lost")


class LeaseLost(Exception):
    pass


Handler = Callable[[JobContext], dict[str, Any] | None]


class Worker:
    def __init__(
        self,
        pool: ConnectionPool[Conn],
        handlers: dict[str, Handler],
        worker_id: str,
        *,
        lease_s: int = queue.DEFAULT_LEASE_S,
        heartbeat_s: float | None = None,
        per_installation: int = queue.PER_INSTALLATION_CAP,
    ) -> None:
        self.pool, self.handlers, self.worker_id = pool, handlers, worker_id
        self.lease_s, self.per_installation = lease_s, per_installation
        self.heartbeat_s = heartbeat_s if heartbeat_s is not None else lease_s / 3
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> bool:
        """Process at most one job. Returns True if a job was claimed."""
        with transaction(self.pool) as conn:
            job = queue.claim(conn, self.worker_id, lease_s=self.lease_s, per_installation=self.per_installation)
        if job is None:
            return False
        token = correlation_id.set(f"job-{job.id}-a{job.attempts}")
        ctx = JobContext(job)
        beat = threading.Thread(target=self._heartbeat, args=(ctx,), daemon=True, name=f"hb-{job.id}")
        with bind(job_id=job.id, installation_id=job.installation_id, attempt=job.attempts):
            event(log, "job.claimed", kind=job.kind, max_attempts=job.max_attempts, worker=self.worker_id)
            beat.start()
            t0 = time.monotonic()
            try:
                self._execute(ctx)
            finally:
                ctx.finished.set()
                beat.join(timeout=5)
                correlation_id.reset(token)
                event(log, "job.processed", duration_ms=int((time.monotonic() - t0) * 1000))
        return True

    def _execute(self, ctx: JobContext) -> None:
        job = ctx.job
        handler = self.handlers.get(job.kind)
        try:
            if handler is None:
                raise PermanentError(f"no handler for job kind {job.kind!r}")
            result = handler(ctx)
        except LeaseLost:
            event(log, "job.lease_lost", logging.WARNING)
            return
        except JobCancelled as e:
            try:
                with transaction(self.pool) as conn:
                    queue.cancel_running(conn, job.id, self.worker_id, str(e))
                event(log, "job.cancelled", reason=str(e)[:64])
            except DatabaseUnavailable:
                event(log, "job.record_failed", logging.ERROR, transition="cancelled")
            return
        except Exception as e:  # every handler failure is classified (retry/dead) and recorded, never swallowed
            self._record_failure(job, e)
            return
        try:
            with transaction(self.pool) as conn:
                ok = queue.complete(conn, job.id, self.worker_id, result)
            if ok:
                event(log, "job.succeeded", outcome=(result or {}).get("outcome"))
            else:
                event(log, "job.completion_ignored", logging.WARNING)
        except DatabaseUnavailable:
            # The job stays `running` until its lease expires, then it is retried. Safe because handlers are idempotent.
            event(log, "job.record_failed", logging.ERROR, transition="succeeded")

    def _record_failure(self, job: Job, err: Exception) -> None:
        try:
            with transaction(self.pool) as conn:
                status = queue.fail(conn, job.id, self.worker_id, err)
            event(
                log,
                "job.retry_scheduled" if status == "retry_wait" else "job.failed",
                logging.WARNING if status == "retry_wait" else logging.ERROR,
                error_type=type(err).__name__,
                new_status=status,
            )
        except DatabaseUnavailable:
            event(log, "job.record_failed", logging.ERROR, transition="failed")

    def _heartbeat(self, ctx: JobContext) -> None:
        """Extend the lease every `heartbeat_s` until the job finishes; flag a lost lease."""
        while not ctx.finished.wait(self.heartbeat_s):
            try:
                with transaction(self.pool) as conn:
                    if not queue.heartbeat(conn, ctx.job.id, self.worker_id, self.lease_s):
                        ctx.lease_lost.set()
                        return
            except DatabaseUnavailable:
                continue  # the lease may still be valid; the next beat retries

    def run_forever(self, idle_sleep_s: float = 1.0, max_db_backoff_s: float = 30.0) -> None:
        backoff = idle_sleep_s
        while not self._stop.is_set():
            try:
                if not self.run_once():
                    self._stop.wait(idle_sleep_s)
                backoff = idle_sleep_s
            except DatabaseUnavailable:
                event(log, "worker.db_unavailable", logging.ERROR, sleep_s=backoff)
                self._stop.wait(backoff)
                backoff = min(max_db_backoff_s, backoff * 2)
