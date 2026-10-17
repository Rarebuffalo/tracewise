"""T-105 worker: handler outcomes, heartbeats, lost leases, database failures, idempotent re-runs."""

from __future__ import annotations

import threading
import time

import pytest

from tests.pg import EphemeralPostgres
from tracewise.db.session import DatabaseUnavailable, make_pool, transaction
from tracewise.jobs import queue
from tracewise.jobs import worker as worker_mod
from tracewise.jobs.queue import PermanentError, RetryableError
from tracewise.jobs.worker import JobContext, Worker


def enq(pool, key: str = "k1") -> int:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key=key, payload={"run_id": 1}, run_key=key)
    assert jid is not None
    return jid


def job(pool, jid: int) -> queue.Job:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        j = queue.get(c, jid)
    assert j is not None
    return j


@pytest.mark.parametrize(
    ("raise_", "expected"),
    [
        (None, "succeeded"),
        (RetryableError("502"), "retry_wait"),
        (ValueError("bug"), "retry_wait"),
        (PermanentError("403"), "dead"),
    ],
)
def test_handler_outcomes(pool, raise_, expected) -> None:  # type: ignore[no-untyped-def]
    jid = enq(pool)

    def handler(ctx: JobContext) -> dict[str, int]:
        assert ctx.job.payload == {"run_id": 1}
        if raise_:
            raise raise_
        return {"ok": 1}

    assert Worker(pool, {"analyze": handler}, "w1").run_once()
    assert job(pool, jid).status == expected


def test_unknown_kind_is_dead(pool) -> None:  # type: ignore[no-untyped-def]
    jid = enq(pool)
    Worker(pool, {}, "w1").run_once()
    j = job(pool, jid)
    assert j.status == "dead" and "no handler" in (j.last_error or "")


def test_idle_returns_false(pool) -> None:  # type: ignore[no-untyped-def]
    assert not Worker(pool, {}, "w1").run_once()


def test_heartbeat_keeps_long_job_owned(pool) -> None:  # type: ignore[no-untyped-def]
    jid = enq(pool)

    def slow(ctx: JobContext) -> None:
        time.sleep(2.5)  # longer than the 1 s lease
        ctx.check()

    Worker(pool, {"analyze": slow}, "w1", lease_s=1, heartbeat_s=0.2).run_once()
    j = job(pool, jid)
    assert (j.status, j.attempts) == ("succeeded", 1)


def test_lost_lease_stops_side_effects(pool, owner) -> None:  # type: ignore[no-untyped-def]
    jid = enq(pool)
    side_effects: list[str] = []

    def handler(ctx: JobContext) -> None:
        owner.execute("UPDATE job SET locked_by = 'someone-else' WHERE id = %s", (ctx.job.id,))  # simulate reclaim
        time.sleep(0.6)
        ctx.check()  # must raise before publishing
        side_effects.append("published")

    Worker(pool, {"analyze": handler}, "w1", lease_s=30, heartbeat_s=0.1).run_once()
    assert side_effects == []
    assert job(pool, jid).locked_by == "someone-else"


def test_database_down_at_claim_raises_and_run_forever_backs_off(pg: EphemeralPostgres, tmp_path) -> None:  # type: ignore[no-untyped-def]
    bad = pg.url().replace(str(pg.sock).replace("/", "%2F"), str(tmp_path).replace("/", "%2F"))
    p = make_pool(bad, min_size=0, max_size=1, timeout_s=0.3)
    try:
        w = Worker(p, {}, "w1")
        with pytest.raises(DatabaseUnavailable) as ei:
            w.run_once()
        assert "tracewise_app" not in str(ei.value) and str(tmp_path) not in str(ei.value)  # no URL leakage
        t = threading.Thread(target=w.run_forever, kwargs={"idle_sleep_s": 0.05, "max_db_backoff_s": 0.2}, daemon=True)
        t.start()
        time.sleep(0.8)
        w.stop()
        t.join(3)
        assert not t.is_alive()
    finally:
        p.close()


def test_db_failure_on_complete_leads_to_safe_rerun(pool, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Handler succeeded but `complete` could not be written: the job is retried after lease expiry,
    so handlers must be idempotent. This test proves the re-run happens and finishes."""
    jid = enq(pool)
    calls: list[int] = []

    def handler(ctx: JobContext) -> dict[str, int]:
        calls.append(ctx.job.attempts)
        return {"n": len(calls)}

    real_complete = queue.complete

    def broken(*a, **k):  # type: ignore[no-untyped-def]
        raise DatabaseUnavailable("simulated outage")

    monkeypatch.setattr(worker_mod.queue, "complete", broken)
    Worker(pool, {"analyze": handler}, "w1", lease_s=30, heartbeat_s=10).run_once()
    assert job(pool, jid).status == "running"
    monkeypatch.setattr(worker_mod.queue, "complete", real_complete)
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))
    Worker(pool, {"analyze": handler}, "w2").run_once()
    j = job(pool, jid)
    assert (j.status, calls) == ("succeeded", [1, 2])


def test_db_failure_on_fail_record_leaves_job_for_reaper(pool, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    jid = enq(pool)

    def handler(ctx: JobContext) -> None:
        raise RetryableError("502")

    monkeypatch.setattr(worker_mod.queue, "fail", lambda *a, **k: (_ for _ in ()).throw(DatabaseUnavailable("x")))
    Worker(pool, {"analyze": handler}, "w1", heartbeat_s=10).run_once()
    assert job(pool, jid).status == "running"
    monkeypatch.undo()
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))
    with transaction(pool) as c:
        assert queue.reap_expired(c) == 1
    assert job(pool, jid).status == "retry_wait"
