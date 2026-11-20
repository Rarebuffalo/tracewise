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
from tracewise.requeue import REASONS, NotAuthorised, OperatorMismatch, requeue

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


def _measured(values: list[int | None]) -> dict[str, Any]:
    known = [v for v in values if v is not None]
    return {"total": sum(known) if known else None, "reported": len(known), "not_reported": len(values) - len(known)}


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
                      publish_result IS NOT NULL AS recorded, cached_input_tokens, reasoning_output_tokens, usage_source
               FROM analysis WHERE created_at >= %s AND created_at < %s""",
            (start, end),
        ).fetchall()
        # Current state, not windowed: what an operator must see to find stuck or invisible work.
        q = conn.execute(
            """SELECT count(*) FILTER (WHERE status = 'queued') AS queued,
                      count(*) FILTER (WHERE status = 'retry_wait') AS retry_wait,
                      count(*) FILTER (WHERE status = 'running') AS running,
                      count(*) FILTER (WHERE status = 'running' AND locked_until < %s) AS running_lease_expired,
                      extract(epoch FROM %s - min(created_at) FILTER (WHERE status IN ('queued', 'retry_wait'))) AS oldest_s
               FROM job WHERE kind = 'analyze'""",
            (end, end),
        ).fetchone()
        pub = conn.execute(
            """SELECT (SELECT count(*) FROM analysis WHERE publish_result IS NULL AND diagnosis IS NOT NULL
                         AND updated_at < %s - interval '15 minutes') AS incomplete,
                      (SELECT count(*) FROM publication WHERE state = 'pending' AND updated_at < %s - interval '15 minutes')
                         AS unconfirmed""",
            (end, end),
        ).fetchone()
        provider_failures = conn.execute(
            """SELECT count(*) AS n FROM analysis WHERE created_at >= %s AND created_at < %s
                 AND diagnosis->>'inconclusive_reason' IN ('provider_failed', 'provider_timeout')""",
            (start, end),
        ).fetchone()
        last_purge = conn.execute(
            """SELECT created_at, detail->>'completed' AS completed, detail->>'error' AS error FROM audit_event
               WHERE action = 'retention.run' ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
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
        "tokens": {
            "in": sum(r["tokens_in"] or 0 for r in rows),
            "out": sum(r["tokens_out"] or 0 for r in rows),
            # Subsets (0014): summed over the analyses that reported them, with that count; never an unknown as 0.
            "cached_in": _measured([r["cached_input_tokens"] for r in rows]),
            "reasoning_out": _measured([r["reasoning_output_tokens"] for r in rows]),
            # Completeness of the totals above: every step reported (provider), a step failed (partial: a lower
            # bound), no model call (no_call), or no measurement record (unknown: legacy rows and notices).
            "usage": {
                k: sum((r["usage_source"] or "unknown") == k for r in rows) for k in ("provider", "partial", "no_call", "unknown")
            },
        },
        "cost_usd": {
            # Calculated from the configured prices (LLM_PRICE_*); providers report no cost. Never estimated.
            "basis": "calculated_from_configured_prices",
            "total": str(sum(priced, Decimal(0))) if priced else None,
            "priced": len(priced),
            "unpriced": len(rows) - len(priced),
            # Of the unpriced: rows with cached input, which no configured price can cover (cost unavailable, not 0).
            "unpriced_with_cached_input": sum(r["cost_usd"] is None and (r["cached_input_tokens"] or 0) > 0 for r in rows),
        },
        "publications": publish,
        "queue": {
            "queued": int(q["queued"]) if q else 0,
            "retry_wait": int(q["retry_wait"]) if q else 0,
            "running": int(q["running"]) if q else 0,
            "running_lease_expired": int(q["running_lease_expired"]) if q else 0,  # the reaper has not run yet
            "oldest_waiting_s": float(q["oldest_s"]) if q and q["oldest_s"] is not None else None,
        },
        # F1: a validated analysis whose publication has not completed for 15 minutes (a later attempt or an operator
        # requeue resumes it), and surfaces reserved but never confirmed (failed, not started or uncertain).
        "publication_incomplete": {
            "analyses": int(pub["incomplete"]) if pub else 0,
            "surfaces_unconfirmed": int(pub["unconfirmed"]) if pub else 0,
        },
        "provider_failures": int(provider_failures["n"]) if provider_failures else 0,
        "retention": {
            "last_run_at": last_purge["created_at"].isoformat() if last_purge else None,
            "last_run_completed": (last_purge["completed"] == "true") if last_purge else None,
            "last_run_error": last_purge["error"] if last_purge else None,
        },
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


def build_operator_from_settings() -> ConnectionPool[Conn]:
    """Requeue connects as the operator's OWN login (its identity is what the audit records), never the system role."""
    from tracewise.config import get_settings
    from tracewise.db.session import make_pool

    st = get_settings()
    if not st.database_url_operator:
        raise SystemExit("requeue needs DATABASE_URL_OPERATOR: your personal database login in tracewise_operator")
    return make_pool(st.database_url_operator.get_secret_value(), min_size=1, max_size=1)


def main(
    argv: list[str] | None = None,
    build: Callable[[], ConnectionPool[Conn]] = build_from_settings,
    build_operator: Callable[[], ConnectionPool[Conn]] = build_operator_from_settings,
) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.ops")
    ap.add_argument("command", choices=["report", "alerts", "requeue"])
    ap.add_argument("--window-hours", type=float, default=None)
    ap.add_argument("--threshold", type=float, default=AlertRule.threshold)
    ap.add_argument("--min-sample", type=int, default=AlertRule.min_sample)
    # requeue (I-6): one explicit dead analysis job; see tracewise/requeue.py for every condition.
    ap.add_argument("--job-id", type=int, default=None)
    ap.add_argument("--reason", choices=REASONS, default=None)
    ap.add_argument("--operator", default=None, help="optional check: must equal your authenticated database login")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.command == "requeue" and (a.job_id is None or a.reason is None):
        ap.error("requeue needs --job-id and --reason")
    pool = build_operator() if a.command == "requeue" else build()
    try:
        if a.command != "requeue":  # requeue authorises in the database (tracewise_requeue), as the operator's login
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
    if a.command == "requeue":
        try:
            rq = requeue(pool, a.job_id, reason=a.reason, operator=a.operator, dry_run=a.dry_run)
        except ValueError as e:
            print(json.dumps({"error": "invalid_arguments", "detail": str(e)}))
            return 1
        except (NotAuthorised, OperatorMismatch) as e:
            error = "not_authorised" if isinstance(e, NotAuthorised) else "operator_mismatch"
            event(log, "ops.requeue_refused", logging.WARNING, error=error, dry_run=a.dry_run)
            print(json.dumps({"error": error}))
            return 1
        event(
            log,
            "ops.requeue",
            outcome=rq.outcome,
            job_id=a.job_id,
            new_job_id=rq.new_job_id,
            dry_run=a.dry_run,
            actor=rq.actor,
            max_reruns=rq.max_reruns,
        )
        print(json.dumps(rq.as_dict(), sort_keys=True))
        return 0 if rq.ok else 1
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
