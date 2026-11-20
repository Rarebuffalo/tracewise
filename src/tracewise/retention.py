"""Retention and tenant purge driver (T-704; FS-SEC-3, FS-INS-3).

`python -m tracewise.retention [--batch-limit N] [--max-batches M] [--dry-run]` runs bounded batches of the
database's fixed-policy `tracewise_purge()` (migrations 0008, 0009, 0017) as the system role. Each batch is one
transaction. The run stops when nothing more is due, or after `max_batches`, in which case it reports
`completed: false` and the next run continues where this one stopped (idempotent: what was deleted is gone, what
is due is found again). A database error stops the run, is logged as `retention.failed`, and gives a non-zero
exit: a failed purge is never reported as success.

Every real run writes one content-free `audit_event` (`system:retention`, `retention.run`): counts per class,
batches, completed, and the error type if any. Never a deleted value.

`--dry-run` runs the same batches inside ONE transaction that is then rolled back, so it reports exactly what a
run would delete now, and changes nothing (no audit row either). While it runs it holds the same row locks as a
real run, for at most `max_batches` batches. Keep it small on a busy database.

Scheduling is the deployment's job (OPERATIONS §6): one run per hour is enough; exit 3 means "run again".
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from psycopg_pool import ConnectionPool

from tracewise.db import repositories as repo
from tracewise.db.session import Conn, transaction
from tracewise.observe import event

log = logging.getLogger(__name__)

_COUNTERS = (
    "analysis_content",
    "analysis",
    "publication",
    "webhook_delivery",
    "failure_signature",
    "workflow_run",
    "job",
    "usage_event",
    "audit_event",
    "redelivery_request",
    "tenant_rows",
)


@dataclass
class PurgeSummary:
    batches: int = 0
    deleted: Counter[str] = field(default_factory=Counter)
    tenants_purged: list[int] = field(default_factory=list)
    tenants_waiting_for_jobs: int = 0
    tenants_without_purge_after: int = 0
    locked: bool = False
    completed: bool = False
    error: str | None = None
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "batches": self.batches,
            "deleted": dict(self.deleted),
            "tenants_purged": self.tenants_purged,
            "tenants_waiting_for_jobs": self.tenants_waiting_for_jobs,
            "tenants_without_purge_after": self.tenants_without_purge_after,
            "locked": self.locked,
            "completed": self.completed,
            "error": self.error,
            "dry_run": self.dry_run,
        }


class _RollBack(Exception):
    """Ends a dry run's transaction without committing."""


def purge(pool: ConnectionPool[Conn], *, batch_limit: int = 1000, max_batches: int = 50, dry_run: bool = False) -> PurgeSummary:
    if not 1 <= batch_limit <= 10_000 or not 1 <= max_batches <= 10_000:
        raise ValueError("batch_limit and max_batches must be within 1..10000")
    s = PurgeSummary(dry_run=dry_run)
    if dry_run:
        try:
            with transaction(pool) as conn:
                _batches(s, lambda: conn.execute("SELECT tracewise_purge(%s) AS r", (batch_limit,)).fetchone(), max_batches)
                raise _RollBack
        except _RollBack:
            pass
        except Exception as e:
            s.error = type(e).__name__
            event(log, "retention.failed", logging.ERROR, error_type=s.error, batches=s.batches, dry_run=True)
            return s
        event(log, "retention.dry_run", **{k: v for k, v in s.as_dict().items() if k != "deleted"}, would_delete=dict(s.deleted))
        return s

    def one() -> Any:
        with transaction(pool) as conn:
            return conn.execute("SELECT tracewise_purge(%s) AS r", (batch_limit,)).fetchone()

    try:
        _batches(s, one, max_batches)
    except Exception as e:  # recorded and re-signalled through the summary; the CLI exits non-zero
        s.error = type(e).__name__
        event(log, "retention.failed", logging.ERROR, error_type=s.error, batches=s.batches)
        _audit(pool, s)
        return s
    level = logging.INFO if s.completed else logging.WARNING
    event(log, "retention.finished", level, **{k: v for k, v in s.as_dict().items() if k != "deleted"}, deleted=dict(s.deleted))
    _audit(pool, s)
    return s


def _audit(pool: ConnectionPool[Conn], s: PurgeSummary) -> None:
    """One content-free record per real run: counts and flags only. A failure to write it fails the run."""
    try:
        with transaction(pool) as conn:
            repo.audit(
                conn,
                "system:retention",
                "retention.run",
                None,
                batches=s.batches,
                completed=s.completed,
                locked=s.locked,
                error=s.error,
                tenants_purged=len(s.tenants_purged),
                **{f"deleted_{k}": int(s.deleted[k]) for k in _COUNTERS},
            )
    except Exception as e:
        s.error = s.error or type(e).__name__
        event(log, "retention.audit_failed", logging.ERROR, error_type=type(e).__name__)


def _batches(s: PurgeSummary, call: Callable[[], Any], max_batches: int) -> None:
    while s.batches < max_batches:
        row = call()
        r: dict[str, Any] = row["r"] if row else {}
        s.batches += 1
        if r.get("locked"):
            s.locked = True
            break
        for k in _COUNTERS:
            s.deleted[k] += int(r.get(k) or 0)
        if r.get("tenant_purged") is not None:
            s.tenants_purged.append(int(r["tenant_purged"]))
        s.tenants_waiting_for_jobs = int(r.get("tenants_waiting_for_jobs") or 0)
        s.tenants_without_purge_after = int(r.get("tenants_without_purge_after") or 0)
        event(log, "retention.batch", **{k: int(r.get(k) or 0) for k in _COUNTERS}, tenant=r.get("tenant"), dry_run=s.dry_run)
        if not r.get("more"):
            s.completed = True
            break


def build_from_settings() -> ConnectionPool[Conn]:
    from tracewise.config import get_settings
    from tracewise.db.session import make_pool

    st = get_settings()
    if not st.database_url_system:
        raise SystemExit("retention needs DATABASE_URL_SYSTEM (the system role may execute tracewise_purge)")
    return make_pool(st.database_url_system.get_secret_value())


def main(argv: list[str] | None = None, build: Callable[[], ConnectionPool[Conn]] = build_from_settings) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.retention")
    ap.add_argument("--batch-limit", type=int, default=1000)
    ap.add_argument("--max-batches", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true", help="report what would be deleted now; change nothing")
    a = ap.parse_args(argv)
    pool = build()
    try:
        s = purge(pool, batch_limit=a.batch_limit, max_batches=a.max_batches, dry_run=a.dry_run)
    finally:
        pool.close()
    print(json.dumps(s.as_dict(), sort_keys=True))
    if s.error:
        return 1
    return 0 if s.completed else 3


if __name__ == "__main__":  # pragma: no cover
    from tracewise.logging import configure_cli

    configure_cli()
    sys.exit(main())
