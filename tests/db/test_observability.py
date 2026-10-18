"""T-706 end to end, offline (fake GitHub, scripted provider, disposable Postgres, real worker on the RLS pool).

Asserts the operational events and fields, the per-analysis record (AT-OPS-01), that failures, retries and
duplicates are distinguishable, that nothing sensitive reaches a log line, and that instrumentation faults do
not break processing. The report/alert module (`tracewise.ops`) is tested with hand-calculated data.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import client as client
from tests.db.test_lifecycle import failure, send
from tracewise import observe, ops
from tracewise.db import repositories as repo
from tracewise.db.session import DatabaseUnavailable, transaction
from tracewise.jobs import queue
from tracewise.logging import JsonFormatter, quiet_libraries, secret_filter


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(JsonFormatter())
        self.addFilter(secret_filter)  # as configured in production (tracewise.logging.configure)
        self.lines: list[str] = []
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        self.lines.append(self.format(record))

    def events(self, name: str | None = None) -> list[dict[str, Any]]:
        out = [r.tw for r in self.records if isinstance(getattr(r, "tw", None), dict) and "event" in r.tw]
        return [e for e in out if name is None or e["event"] == name]


@pytest.fixture
def cap() -> Iterator[Capture]:
    h = Capture()
    root = logging.getLogger()
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.DEBUG)  # stricter than production (INFO)
    quiet_libraries()
    try:
        yield h
    finally:
        root.removeHandler(h)
        root.setLevel(old)


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]  # noqa: F811
    return World(pool, owner, server, tmp_path / "ws", head)


def test_successful_analysis_events_ids_and_ops_record(world: World, cap: Capture) -> None:
    jid = world.enqueue()
    world.run()
    names = [e["event"] for e in cap.events()]
    for expected in (
        "job.claimed",
        "analysis.started",
        "analysis.diagnosed",
        "publication.result",
        "analysis.finished",
        "job.succeeded",
        "job.processed",
    ):
        assert expected in names, expected
    assert (
        names.index("job.claimed")
        < names.index("analysis.diagnosed")
        < names.index("analysis.finished")
        < names.index("job.succeeded")
    )
    for e in cap.events():
        if e["event"].startswith(("job.", "analysis.", "publication.")):
            assert (e["job_id"], e["installation_id"]) == (jid, 9), e
        if e["event"].startswith(("analysis.", "publication.")):
            assert (e["repo_id"], e["run_id"]) == (7, 55), e
    (d,) = cap.events("analysis.diagnosed")
    assert d["status"] == "diagnosed" and d["category"] == "code_regression" and d["confidence_band"] == "medium"
    assert d["abstained"] is False and d["tokens_in"] > 0 and isinstance(d["validation_flag_count"], int)
    assert {(e["surface"], e["state"]) for e in cap.events("publication.result")} == {
        ("commit_comment", "published"),
        ("check_run", "published"),
    }
    (fin,) = cap.events("analysis.finished")
    assert fin["outcome"] == "diagnosed" and set(fin["stage_ms"]) == {
        "collect",
        "associate",
        "diagnose",
        "persist",
        "publish",
        "total",
    }
    row = world.owner.execute(
        "SELECT stage_ms, publish_result, finished_at, tokens_in, tokens_out, cost_usd, status FROM analysis"
    ).fetchone()
    stage_ms, publish_result, finished_at, tin, tout, cost, status = row
    assert set(stage_ms) == set(fin["stage_ms"]) and stage_ms["total"] >= stage_ms["diagnose"]
    assert publish_result == {"commit_comment": "published", "check_run": "published"}
    assert finished_at is not None and tin > 0 and tout > 0 and status == "diagnosed"
    assert cost is None  # unpriced: no price configured, so no cost is invented


def test_cost_is_computed_only_from_configured_prices(world: World) -> None:
    from tracewise.jobs.handlers import analyze as a

    deps = a.AnalyzeDeps(
        world.tenant_pool,
        world.http,
        world.tokens,
        1,
        lambda: None,
        lambda: None,  # type: ignore[arg-type]
        price_input_per_mtok=Decimal("3"),
        price_output_per_mtok=Decimal("15"),
    )
    assert a.cost_usd(deps, 1000, 200) == Decimal("0.006")  # 1000*3/1e6 + 200*15/1e6
    assert (
        a.cost_usd(
            a.AnalyzeDeps(
                world.tenant_pool,
                world.http,
                world.tokens,
                1,
                lambda: None,
                lambda: None,  # type: ignore[arg-type]
                price_input_per_mtok=Decimal("3"),
            ),
            1000,
            200,
        )
        is None
    )


def test_no_secret_url_log_or_source_content_in_any_line(world: World, cap: Capture) -> None:
    world.enqueue()
    world.run()
    text = "\n".join(cap.lines) + json.dumps([getattr(r, "tw", None) for r in cap.records], default=str)
    for needle in (
        world.server.token,
        "Bearer",
        "sig=",
        "X-Amz",
        "blob.core.windows.net",
        "assert 0.21 == 1.21",
        "round(subtotal_",
        "acme/coffee",
        "BEGIN RSA",
        "eyJ",
    ):
        assert needle not in text, needle


def test_retry_and_dead_and_cancel_are_distinguishable(world: World, cap: Capture) -> None:
    world.state.fault("POST", "cr", 502)
    jid = world.enqueue()
    world.run()
    (r,) = cap.events("job.retry_scheduled")
    assert (r["job_id"], r["new_status"], r["error_type"]) == (jid, "retry_wait", "GitHubRetryable")
    world.ready(jid)
    world.run()
    assert [e["job_id"] for e in cap.events("job.succeeded")] == [jid]
    bad = world.enqueue(installation_id=77)  # payload/installation mismatch → permanent
    world.run()
    (f,) = cap.events("job.failed")
    assert (f["job_id"], f["new_status"], f["error_type"]) == (bad, "dead", "PermanentError")
    world.owner.execute("UPDATE repository SET enabled = false WHERE id = 7")
    off = world.enqueue()
    world.run()
    (c,) = cap.events("job.cancelled")
    assert (c["job_id"], c["reason"]) == (off, "repo_disabled")


def test_stale_lease_recovery_is_visible(world: World, cap: Capture) -> None:
    jid = world.enqueue()
    world.owner.execute(
        "UPDATE job SET status='running', attempts=1, locked_by='ghost', locked_until=now() - interval '1 minute' WHERE id=%s",
        (jid,),
    )
    world.run()
    (e,) = cap.events("queue.lease_expired")
    assert (e["job_id"], e["installation_id"], e["new_status"]) == (jid, 9, "retry_wait")
    assert world.jobrow(jid)["status"] == "succeeded"


def test_ops_record_failure_is_reported_and_never_republishes(
    world: World, cap: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*a: Any, **k: Any) -> None:
        raise DatabaseUnavailable("database operational error (OperationalError)")

    monkeypatch.setattr(repo, "record_analysis_ops", down)
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded"
    (e,) = cap.events("analysis.ops_record_failed")
    assert e["job_id"] == jid and isinstance(e["analysis_id"], int)
    assert (world.state.count("POST", "cc"), world.state.count("POST", "cr")) == (1, 1)
    assert world.owner.execute("SELECT stage_ms FROM analysis").fetchone() == (None,)


def test_instrumentation_fault_does_not_break_processing(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    before = observe.dropped_events
    monkeypatch.setattr(observe, "sanitize", lambda f: (_ for _ in ()).throw(RuntimeError("instrumentation bug")))
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "succeeded" and len(world.state.check_runs) == 1
    assert observe.dropped_events > before


def test_webhook_events_distinguish_duplicates_rejections_and_scope(client, pool, owner, cap: Capture) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        repo.set_installation_status(c, 9, "active", "acme")
        repo.repository_added(c, 7, 9, "acme/app")
        repo.repository_added(c, 8, 9, "acme/x")
        repo.repository_removed(c, 8, 9)  # removed from the installation's scope (T-701)
    send(client, "workflow_run", failure(), "dup-1")
    send(client, "workflow_run", failure(), "dup-1")
    send(client, "workflow_run", failure(run_id=56), "other-run")
    send(client, "workflow_run", failure(repo_id=8, run_id=57, name="acme/x"), "removed")
    client.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "workflow_run", "X-Hub-Signature-256": "sha256=0", "X-GitHub-Delivery": "forged"},
    )
    send(client, "workflow_run", {"action": "completed"}, "malformed")
    got = [(e["delivery_id"], e["outcome"]) for e in cap.events("webhook.ingested")]
    assert got == [
        ("dup-1", "enqueued"),
        ("dup-1", "duplicate_delivery"),
        ("other-run", "enqueued"),
        ("removed", "repo_not_in_scope"),
    ]
    assert all(e["installation_id"] == 9 and e["gh_event"] == "workflow_run" for e in cap.events("webhook.ingested"))
    assert len(cap.events("webhook.signature_rejected")) == 1 and "delivery_id" not in cap.events("webhook.signature_rejected")[0]
    (rej,) = cap.events("webhook.payload_rejected")
    assert (rej["delivery_id"], rej["reason"]) == ("malformed", "invalid_payload")


# ---------------------------------------------------------------- ops report and alert (hand-calculated)

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _job(
    owner: Any,
    status: str,
    *,
    outcome: str | None = None,
    age_min: float = 10,
    dur_s: float = 60,
    attempts: int = 1,
    at: datetime = NOW,
) -> None:
    finished = at - timedelta(minutes=age_min)
    created = finished - timedelta(seconds=dur_s)
    owner.execute(
        """INSERT INTO job (kind, installation_id, dedupe_key, payload, status, attempts, result, created_at, finished_at,
                            locked_by, locked_until)
           VALUES ('analyze', 9, md5(random()::text), '{}', %s, %s, %s, %s, %s, NULL, NULL)""",
        (
            status,
            attempts,
            json.dumps({"outcome": outcome}) if outcome else None,
            created,
            finished if status in queue.TERMINAL else None,
        ),
    )


def test_report_with_no_data_makes_no_latency_claim(pool, owner) -> None:  # type: ignore[no-untyped-def]
    r = ops.report(pool, now=NOW)
    assert r["latency"]["end_to_end_s"] == {"n": 0, "p50": None, "p95": None, "within_deadline": 0, "deadline_s": 600}
    assert r["latency"]["processing_ms"] == {"n": 0, "p50": None, "p95": None}
    assert r["cost_usd"] == {"total": None, "priced": 0, "unpriced": 0}
    assert ops.failure_rate(pool, now=NOW)["state"] == "insufficient_data"


def test_report_percentiles_and_counts_are_hand_calculated(pool, owner) -> None:  # type: ignore[no-untyped-def]
    for s in (10, 20, 30, 40, 50, 60, 70, 80, 90, 700):  # e2e seconds; nearest-rank p50 = 50, p95 = 700
        _job(owner, "succeeded", outcome="diagnosed", dur_s=s)
    _job(owner, "succeeded", outcome="diagnosed", dur_s=5, age_min=60 * 25)  # outside the 24 h window
    _job(owner, "dead", attempts=3)
    _job(owner, "cancelled")
    r = ops.report(pool, now=NOW)
    e2e = r["latency"]["end_to_end_s"]
    assert (e2e["n"], e2e["p50"], e2e["p95"], e2e["within_deadline"]) == (10, 50.0, 700.0, 9)
    assert r["jobs"]["by_status"] == {"succeeded": 10, "dead": 1, "cancelled": 1} and r["jobs"]["retried"] == 1
    assert ops.percentile([1, 2, 3, 4], 50) == 2.0 and ops.percentile([7], 95) == 7.0 and ops.percentile([], 50) is None


def test_failure_rate_alert_states_threshold_and_exclusions(pool, owner, cap: Capture) -> None:  # type: ignore[no-untyped-def]
    for _ in range(8):
        _job(owner, "succeeded", outcome="diagnosed", age_min=5)
    _job(owner, "dead", age_min=5)
    _job(owner, "succeeded", outcome="could_not_complete", age_min=5)
    for _ in range(5):
        _job(owner, "cancelled", age_min=5)  # controlled no-ops: excluded
    _job(owner, "dead", age_min=90)  # outside the 1 h window
    res = ops.failure_rate(pool, now=NOW)
    assert (res["failures"], res["finished"], res["rate"], res["state"]) == (2, 10, 0.2, "firing")  # 2/10 ≥ 0.2
    (alert,) = cap.events("alert.failure_rate")
    assert alert["rate"] == 0.2 and alert["finished"] == 10
    assert ops.failure_rate(pool, ops.AlertRule(threshold=0.25), now=NOW)["state"] == "ok"
    assert ops.failure_rate(pool, ops.AlertRule(min_sample=11), now=NOW)["state"] == "insufficient_data"


def test_ops_cli_exit_codes_and_refuses_without_config(pool, owner, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class Shared:  # main() closes the pool it is given; keep the fixture's open
        def __getattr__(self, n: str) -> Any:
            return getattr(pool, n)

        def close(self) -> None:
            pass

    assert ops.main(["report"], build=lambda: Shared()) == 0  # type: ignore[arg-type, return-value]
    assert json.loads(capsys.readouterr().out)["analyses"]["total"] == 0
    for _ in range(10):
        _job(owner, "dead", age_min=0.5, at=datetime.now(UTC))
    assert ops.main(["alerts"], build=lambda: Shared()) == 2  # type: ignore[arg-type, return-value]
    from tracewise.config import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL_SYSTEM", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL_SYSTEM"):
        ops.build_from_settings()
    get_settings.cache_clear()
