"""Worker loop (T-105): claim → handle → complete/fail, with lease heartbeats.

Handlers must be idempotent: a job can run more than once (lease expiry after a crash,
or a lost `complete` because the database failed). Publication uniqueness (T-104) is what
makes re-runs safe for GitHub side effects.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from psycopg_pool import ConnectionPool

from tracewise.db.session import Conn, DatabaseUnavailable, transaction
from tracewise.jobs import queue
from tracewise.jobs.queue import Job, PermanentError
from tracewise.logging import correlation_id

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
        beat.start()
        try:
            self._execute(ctx)
        finally:
            ctx.finished.set()
            beat.join(timeout=5)
            correlation_id.reset(token)
        return True

    def _execute(self, ctx: JobContext) -> None:
        job = ctx.job
        handler = self.handlers.get(job.kind)
        try:
            if handler is None:
                raise PermanentError(f"no handler for job kind {job.kind!r}")
            result = handler(ctx)
        except LeaseLost:
            log.warning("job abandoned: lease lost", extra={"tw": {"job_id": job.id}})
            return
        except Exception as e:
            self._record_failure(job, e)
            return
        try:
            with transaction(self.pool) as conn:
                ok = queue.complete(conn, job.id, self.worker_id, result)
            if not ok:
                log.warning("completion ignored: job no longer owned", extra={"tw": {"job_id": job.id}})
        except DatabaseUnavailable:
            # The job stays `running` until its lease expires, then it is retried. Safe because handlers are idempotent.
            log.error("could not record completion; job will be retried after lease expiry", extra={"tw": {"job_id": job.id}})

    def _record_failure(self, job: Job, err: Exception) -> None:
        try:
            with transaction(self.pool) as conn:
                status = queue.fail(conn, job.id, self.worker_id, err)
            log.warning("job failed", extra={"tw": {"job_id": job.id, "error_type": type(err).__name__, "new_status": status}})
        except DatabaseUnavailable:
            log.error("could not record failure; job will be retried after lease expiry", extra={"tw": {"job_id": job.id}})

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
                log.error("database unavailable; backing off", extra={"tw": {"sleep_s": backoff}})
                self._stop.wait(backoff)
                backoff = min(max_db_backoff_s, backoff * 2)
