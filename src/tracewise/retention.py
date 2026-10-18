"""Retention and tenant purge driver (T-704; FS-SEC-3, FS-INS-3).

`python -m tracewise.retention [--batch-limit N] [--max-batches M]` runs bounded batches of the database's
fixed-policy `tracewise_purge()` (migration 0008) as the system role. Each batch is one transaction. The run
stops when nothing more is due, or after `max_batches`, in which case it reports `completed: false` and the
next run continues where this one stopped. A database error stops the run, is logged as `retention.failed`,
and gives a non-zero exit: a failed purge is never reported as success. Nothing is scheduled.
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
        }


def purge(pool: ConnectionPool[Conn], *, batch_limit: int = 1000, max_batches: int = 50) -> PurgeSummary:
    if not 1 <= batch_limit <= 10_000 or not 1 <= max_batches <= 10_000:
        raise ValueError("batch_limit and max_batches must be within 1..10000")
    s = PurgeSummary()
    try:
        while s.batches < max_batches:
            with transaction(pool) as conn:
                row = conn.execute("SELECT tracewise_purge(%s) AS r", (batch_limit,)).fetchone()
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
            event(log, "retention.batch", **{k: int(r.get(k) or 0) for k in _COUNTERS}, tenant=r.get("tenant"))
            if not r.get("more"):
                s.completed = True
                break
    except Exception as e:  # recorded and re-signalled through the summary; the CLI exits non-zero
        s.error = type(e).__name__
        event(log, "retention.failed", logging.ERROR, error_type=s.error, batches=s.batches)
        return s
    level = logging.INFO if s.completed else logging.WARNING
    event(log, "retention.finished", level, **{k: v for k, v in s.as_dict().items() if k != "deleted"}, deleted=dict(s.deleted))
    return s


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
    a = ap.parse_args(argv)
    pool = build()
    try:
        s = purge(pool, batch_limit=a.batch_limit, max_batches=a.max_batches)
    finally:
        pool.close()
    print(json.dumps(s.as_dict(), sort_keys=True))
    if s.error:
        return 1
    return 0 if s.completed else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
