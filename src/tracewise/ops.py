"""Operational report and failure-rate alert (T-706; FS-OPS-1, FS-OPS-2, AT-OPS-01, AT-OPS-02).

`python -m tracewise.ops report [--window-hours N]` prints one JSON document: outcomes, measured latency
percentiles, tokens and cost over the window. `python -m tracewise.ops alerts` evaluates the failure-rate rule,
emits `alert.failure_rate` when it fires, and exits 2. Nothing is scheduled: an operator or a future
deployment (T-1002) decides when to run these.

Aggregates only, across installations (system plane, `DATABASE_URL_SYSTEM`). No repository names, content or
per-tenant breakdown leave the database. Latency is reported with its sample size and as `null` when there is
no data: no latency figure exists without a measurement (FS-OPS-2).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from psycopg_pool import ConnectionPool

from tracewise.db.session import Conn, DatabaseUnavailable, WrongDatabaseRole, require_system_plane, transaction
from tracewise.observe import event

log = logging.getLogger(__name__)

DEADLINE_S = 600  # FS-OPS-2 target: p95 below the 10-minute job deadline (a target, not a claim)


@dataclass(frozen=True)
class AlertRule:
    """Failure rate = (dead analyze jobs + analyses that could not complete) / finished analyze jobs.

    Cancelled jobs (uninstalled, suspended, out of scope) are controlled no-ops and are excluded. The defaults are
    provisional operating values, not measured ones; tune them once real traffic exists.
    """

    threshold: float = 0.2  # PROVISIONAL: not a user-approved SLO (review queue)
    min_sample: int = 10

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= 1 or isinstance(self.min_sample, bool) or self.min_sample < 1:
            raise ValueError("threshold must be in (0, 1] and min_sample >= 1")


DEFAULT_RULE = AlertRule()


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile; None for no data."""
    if not values:
        return None
    s = sorted(values)
    k = max(1, math.ceil(p / 100 * len(s)))
    return float(s[k - 1])


def _dist(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95)}


def report(pool: ConnectionPool[Conn], *, window: timedelta = timedelta(hours=24), now: datetime | None = None) -> dict[str, Any]:
    end = now or datetime.now(UTC)
    start = end - window
    with transaction(pool) as conn:
        outcomes = {
            r["status"]: r["n"]
            for r in conn.execute(
                "SELECT status, count(*) AS n FROM analysis WHERE created_at >= %s AND created_at < %s GROUP BY status",
                (start, end),
            )
        }
        jobs = {
            r["status"]: r["n"]
            for r in conn.execute(
                """SELECT status, count(*) AS n FROM job WHERE kind = 'analyze' AND created_at >= %s AND created_at < %s
                   GROUP BY status""",
                (start, end),
            )
        }
        retried = conn.execute(
            "SELECT count(*) AS n FROM job WHERE kind = 'analyze' AND attempts > 1 AND created_at >= %s AND created_at < %s",
            (start, end),
        ).fetchone()
        e2e = [
            float(r["s"])
            for r in conn.execute(
                """SELECT extract(epoch FROM finished_at - created_at) AS s FROM job
                   WHERE kind = 'analyze' AND status = 'succeeded' AND finished_at >= %s AND finished_at < %s""",
                (start, end),
            )
        ]
        rows = conn.execute(
            """SELECT CASE WHEN jsonb_typeof(stage_ms->'total') = 'number' AND (stage_ms->>'total')::numeric >= 0
                           THEN (stage_ms->>'total')::numeric END AS total_ms, latency_ms, tokens_in, tokens_out, cost_usd,
                      publish_result IS NOT NULL AS recorded
               FROM analysis WHERE created_at >= %s AND created_at < %s""",
            (start, end),
        ).fetchall()
        publish = {
            f"{r['surface']}:{r['state']}": r["n"]
            for r in conn.execute(
                """SELECT p.surface, p.state, count(*) AS n FROM publication p
                   WHERE p.updated_at >= %s AND p.updated_at < %s GROUP BY 1, 2""",
                (start, end),
            )
        }
    priced = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    processing = [float(r["total_ms"]) for r in rows if r["total_ms"] is not None]
    model = [float(r["latency_ms"]) for r in rows if r["latency_ms"] is not None]
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "analyses": {"total": len(rows), "by_outcome": outcomes, "without_ops_record": sum(not r["recorded"] for r in rows)},
        "jobs": {"by_status": jobs, "retried": int(retried["n"]) if retried else 0},
        "latency": {
            "end_to_end_s": _dist(e2e) | {"within_deadline": sum(v <= DEADLINE_S for v in e2e), "deadline_s": DEADLINE_S},
            "processing_ms": _dist(processing),
            "model_ms": _dist(model),
        },
        "tokens": {"in": sum(r["tokens_in"] or 0 for r in rows), "out": sum(r["tokens_out"] or 0 for r in rows)},
        "cost_usd": {
            "total": str(sum(priced, Decimal(0))) if priced else None,
            "priced": len(priced),
            "unpriced": len(rows) - len(priced),
        },
        "publications": publish,
    }


def failure_rate(
    pool: ConnectionPool[Conn],
    rule: AlertRule = DEFAULT_RULE,
    *,
    window: timedelta = timedelta(hours=1),
    now: datetime | None = None,
) -> dict[str, Any]:
    end = now or datetime.now(UTC)
    start = end - window
    with transaction(pool) as conn:
        r = conn.execute(
            """SELECT count(*) FILTER (WHERE status = 'dead') AS dead,
                      count(*) FILTER (WHERE status = 'succeeded' AND result->>'outcome' = 'could_not_complete') AS cnc,
                      count(*) FILTER (WHERE status IN ('succeeded', 'dead')) AS finished
               FROM job WHERE kind = 'analyze' AND finished_at >= %s AND finished_at < %s""",
            (start, end),
        ).fetchone()
    assert r is not None
    failures, finished = int(r["dead"]) + int(r["cnc"]), int(r["finished"])
    rate = failures / finished if finished else None
    if finished < rule.min_sample:
        state = "insufficient_data"
    else:
        state = "firing" if rate is not None and rate >= rule.threshold else "ok"
    out = {
        "rule": "failure_rate",
        "state": state,
        "rate": rate,
        "failures": failures,
        "dead": int(r["dead"]),
        "could_not_complete": int(r["cnc"]),
        "finished": finished,
        "threshold": rule.threshold,
        "threshold_status": "provisional" if rule == DEFAULT_RULE else "operator_supplied",
        "min_sample": rule.min_sample,
        "window_s": int(window.total_seconds()),
    }
    if state == "firing":
        event(log, "alert.failure_rate", logging.ERROR, **{k: v for k, v in out.items() if k != "rule"})
    return out


def build_from_settings() -> ConnectionPool[Conn]:
    from tracewise.config import get_settings
    from tracewise.db.session import make_pool

    st = get_settings()
    if not st.database_url_system:
        raise SystemExit("ops needs DATABASE_URL_SYSTEM (cross-installation aggregates)")
    return make_pool(st.database_url_system.get_secret_value())


def main(argv: list[str] | None = None, build: Callable[[], ConnectionPool[Conn]] = build_from_settings) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.ops")
    ap.add_argument("command", choices=["report", "alerts"])
    ap.add_argument("--window-hours", type=float, default=None)
    ap.add_argument("--threshold", type=float, default=AlertRule.threshold)
    ap.add_argument("--min-sample", type=int, default=AlertRule.min_sample)
    a = ap.parse_args(argv)
    pool = build()
    try:
        require_system_plane(pool)  # under RLS the tenant role sees no rows: never report that as "no data"
        return _run(a, pool)
    except WrongDatabaseRole as e:
        event(log, "ops.failed", logging.ERROR, error_type=type(e).__name__, command=a.command)
        print(json.dumps({"error": "wrong_database_role", "command": a.command}))
        return 1
    except DatabaseUnavailable as e:
        event(log, "ops.failed", logging.ERROR, error_type=type(e).__name__, command=a.command)
        print(json.dumps({"error": "database_unavailable", "command": a.command}))
        return 1
    finally:
        pool.close()


def _run(a: argparse.Namespace, pool: ConnectionPool[Conn]) -> int:
    if a.command == "report":
        doc = report(pool, window=timedelta(hours=a.window_hours or 24))
        print(json.dumps(doc, sort_keys=True))
        return 0
    res = failure_rate(pool, AlertRule(a.threshold, a.min_sample), window=timedelta(hours=a.window_hours or 1))
    print(json.dumps(res, sort_keys=True))
    return 2 if res["state"] == "firing" else 0


if __name__ == "__main__":  # pragma: no cover
    from tracewise.logging import configure_cli

    configure_cli()
    sys.exit(main())
