"""T-105: queue state machine, retries, leases, caps, concurrency (AT-REL-04 at queue level)."""

from __future__ import annotations

import random
import threading
import time

import psycopg
import pytest

from tracewise.db.session import transaction
from tracewise.jobs import queue
from tracewise.jobs.queue import PermanentError, RetryableError


def enq(pool, n: int = 1, inst: int = 9, run_key: str | None = None, prefix: str = "k", **kw) -> list[int]:  # type: ignore[no-untyped-def]
    ids = []
    with transaction(pool) as c:
        for i in range(n):
            jid = queue.enqueue(
                c,
                kind="analyze",
                installation_id=inst,
                dedupe_key=f"{prefix}-{inst}-{i}",
                payload={"i": i},
                run_key=run_key or f"{inst}:{prefix}{i}",
                **kw,
            )
            assert jid is not None
            ids.append(jid)
    return ids


def claim(pool, worker: str = "w1", **kw):  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        return queue.claim(c, worker, **kw)


def status(pool, jid: int) -> queue.Job:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        j = queue.get(c, jid)
    assert j is not None
    return j


def make_ready(owner, jid: int) -> None:  # type: ignore[no-untyped-def]
    owner.execute("UPDATE job SET run_after = now() - interval '1 second' WHERE id = %s", (jid,))


def test_enqueue_dedupe(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        a = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="analyze:1:2:1", payload={})
        b = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="analyze:1:2:1", payload={})
    assert a is not None and b is None


def test_happy_path_and_owner_guard(pool) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    j = claim(pool)
    assert j is not None and (j.id, j.status, j.attempts, j.locked_by) == (jid, "running", 1, "w1")
    assert j.deadline_at is not None
    assert claim(pool, "w2") is None  # nothing else ready
    with transaction(pool) as c:
        assert not queue.complete(c, jid, "w2")  # not the owner
        assert queue.complete(c, jid, "w1", {"analysis_id": 1})
        assert not queue.complete(c, jid, "w1")  # already terminal
    assert status(pool, jid).status == "succeeded"


def test_retryable_failure_backoff_then_retry(pool, owner) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool)
    with transaction(pool) as c:
        assert queue.fail(c, jid, "w1", RetryableError("502 bad gateway"), rnd=random.Random(1)) == "retry_wait"
        delay = c.execute("SELECT extract(epoch FROM run_after - now()) AS s FROM job WHERE id = %s", (jid,)).fetchone()
    assert delay is not None and 23 <= float(delay["s"]) <= 37  # 30 s ±20%
    assert claim(pool) is None  # not before run_after
    make_ready(owner, jid)
    j = claim(pool, "w2")
    assert j is not None and j.attempts == 2 and j.last_error is not None and "RetryableError: 502" in j.last_error


def test_retry_after_is_honoured(pool) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool)
    with transaction(pool) as c:
        queue.fail(c, jid, "w1", RetryableError("rate limited", retry_after_s=75))
        s = c.execute("SELECT extract(epoch FROM run_after - now()) AS s FROM job WHERE id = %s", (jid,)).fetchone()
    assert s is not None and float(s["s"]) >= 74


def test_attempts_exhausted_goes_dead(pool, owner) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool, max_attempts=2)
    for expected in ("retry_wait", "dead"):
        make_ready(owner, jid)
        assert claim(pool) is not None
        with transaction(pool) as c:
            assert queue.fail(c, jid, "w1", RuntimeError("boom")) == expected
    j = status(pool, jid)
    assert j.status == "dead" and j.last_error is not None and j.last_error.startswith("attempts exhausted")


def test_permanent_error_dead_immediately(pool) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool)
    with transaction(pool) as c:
        assert queue.fail(c, jid, "w1", PermanentError("403 missing permission")) == "dead"
    assert status(pool, jid).last_error.startswith("permanent")  # type: ignore[union-attr]


def test_deadline_exceeded(pool, owner) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool)
    owner.execute("UPDATE job SET deadline_at = now() + interval '5 seconds' WHERE id = %s", (jid,))
    with transaction(pool) as c:  # 30 s backoff would pass the deadline
        assert queue.fail(c, jid, "w1", RetryableError("timeout")) == "dead"
    assert "deadline exceeded" in (status(pool, jid).last_error or "")
    (j2,) = enq(pool, prefix="q")
    owner.execute("UPDATE job SET deadline_at = now() - interval '1 second' WHERE id = %s", (j2,))
    assert claim(pool) is None and status(pool, j2).status == "dead"


def test_lease_expiry_reclaims_and_fences_old_worker(pool, owner) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool, "w1", lease_s=60)
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))
    with transaction(pool) as c:
        assert not queue.heartbeat(c, jid, "w1")  # expired lease cannot be extended
    j = claim(pool, "w2")
    assert j is not None and j.locked_by == "w2" and j.attempts == 2
    with transaction(pool) as c:
        assert not queue.complete(c, jid, "w1")
        assert queue.fail(c, jid, "w1", RuntimeError("late")) is None
        assert queue.heartbeat(c, jid, "w2")
        assert queue.complete(c, jid, "w2")


def test_lease_expiry_on_last_attempt_goes_dead(pool, owner) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool, max_attempts=1)
    claim(pool)
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))
    assert claim(pool, "w2") is None
    j = status(pool, jid)
    assert (j.status, j.last_error) == ("dead", "lease expired")


def test_per_installation_cap_and_other_installations_progress(pool) -> None:  # type: ignore[no-untyped-def]
    enq(pool, 50, inst=1)  # AT-REL-04 shape: 50 failures from one installation
    enq(pool, 3, inst=2)
    got = [claim(pool, f"w{i}") for i in range(6)]
    by_inst = [j.installation_id for j in got if j is not None]
    assert by_inst.count(1) == 2 and by_inst.count(2) == 2  # each installation capped, neither starved


def test_one_running_job_per_run(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="analyze:1:7:1", payload={}, run_key="1:7")
        queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="analyze:1:7:2", payload={}, run_key="1:7")
    assert claim(pool, "a") is not None
    assert claim(pool, "b") is None


def test_cancel_only_before_running(pool) -> None:  # type: ignore[no-untyped-def]
    a, b = enq(pool, 2)
    claim(pool)
    with transaction(pool) as c:
        assert not queue.cancel(c, a)  # running
        assert queue.cancel(c, b)
        assert queue.counts(c) == {"running": 1, "cancelled": 1}


def test_concurrent_claims_never_double_claim_or_exceed_cap(pool, owner) -> None:  # type: ignore[no-untyped-def]
    for inst in range(1, 6):
        enq(pool, 10, inst=inst)
    claimed: list[int] = []
    lock = threading.Lock()
    violations: list[str] = []

    def worker(name: str) -> None:
        while True:
            j = claim(pool, name, lease_s=30)
            if j is None:
                return
            with lock:
                claimed.append(j.id)
            peak = owner.execute(
                "SELECT max(n) FROM (SELECT count(*) n FROM job WHERE status='running' GROUP BY installation_id) t"
            ).fetchone()
            if peak and peak[0] and peak[0] > 2:
                violations.append(f"cap exceeded: {peak[0]}")
            time.sleep(0.005)
            with transaction(pool) as c:
                assert queue.complete(c, j.id, name)

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not violations
    assert len(claimed) == len(set(claimed)) == 50
    assert owner.execute("SELECT count(*) FROM job WHERE status='succeeded'").fetchone() == (50,)


def test_backoff_schedule() -> None:
    r = random.Random(0)
    vals = [queue.backoff_s(a, rnd=r) for a in (1, 2, 3, 4)]
    assert 24 <= vals[0] <= 36 and 96 <= vals[1] <= 144 and vals[2] <= 360 and vals[3] <= 360
    assert queue.backoff_s(1, retry_after_s=200, rnd=r) == 200


def test_last_error_is_redacted(pool) -> None:  # type: ignore[no-untyped-def]
    (jid,) = enq(pool)
    claim(pool)
    with transaction(pool) as c:
        queue.fail(c, jid, "w1", RetryableError("bad creds ghs_" + "B" * 36))
    assert "ghs_" not in (status(pool, jid).last_error or "")


def test_claim_requires_transaction_atomicity(pool, owner) -> None:  # type: ignore[no-untyped-def]
    """A claim whose transaction rolls back leaves the job claimable (no half-claimed rows)."""
    (jid,) = enq(pool)
    with pytest.raises(RuntimeError), transaction(pool) as c:
        assert queue.claim(c, "w1") is not None
        raise RuntimeError("crash before commit")
    j = status(pool, jid)
    assert (j.status, j.attempts) == ("queued", 0)
    assert owner.execute("SELECT 1").fetchone() == (1,)
    _ = psycopg  # keep import for type context
