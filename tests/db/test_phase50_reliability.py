"""Phase 50, Batch A (A1, A2): reliability defects confirmed by the Phase 50 audit. Offline: fake GitHub, scripted
provider, disposable PostgreSQL.

A1 (FS-ERR-1 / AT-REL-01): a provider failure whose retry cannot fit before the 10-minute job deadline (FS-ERR-2)
    is the final attempt. It must publish the "could not complete" notice instead of being killed silently. A job
    that already ran once and waited past its deadline gets one final, notice-only attempt.
A2: a failed delivery skipped only because of the redelivery cooldown must stay within the next pass's window.
"""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

from datetime import timedelta
from typing import Any

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_recovery import NOW, Hub, count, delivery, redeliver, setup_tenants
from tracewise.investigate.provider import ProviderTimeout

TIMEOUTS = [[ProviderTimeout("t")] for _ in range(3)]


def world(pool: Any, owner: Any, server: Any, tmp_path: Any, head: str, tenant_pool: Any) -> World:
    World.tenant_pool = tenant_pool
    return World(pool, owner, server, tmp_path / "ws", head, scripts=TIMEOUTS)


def notices(w: World) -> list[dict[str, Any]]:
    return [cr for cr in w.state.check_runs if "could not complete" in cr["output"]["title"].lower()]


# ------------------------------------------------------------------ A1


def test_a1_provider_failure_without_time_to_retry_publishes_the_notice(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    w.run()
    assert w.jobrow(jid)["status"] == "retry_wait"
    owner.execute("UPDATE job SET deadline_at = now() + interval '60 seconds' WHERE id = %s", (jid,))  # 120 s backoff cannot fit
    w.ready(jid)
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 2, "could_not_complete")
    (cr,) = w.state.check_runs  # FS-ERR-1: one neutral Check Run naming the provider failure (as test_11)
    assert "timed out" in cr["output"]["text"] and cr["conclusion"] == "neutral"
    assert w.all_ccs() == [] and w.provider_calls == 2  # never a commit comment


def test_a1_a_job_that_waited_past_its_deadline_gets_one_notice_only_attempt(
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    w.run()  # attempt 1 failed; retry scheduled
    owner.execute("UPDATE job SET deadline_at = now() - interval '1 second', run_after = now() WHERE id = %s", (jid,))
    w.run()  # e.g. stuck behind the per-installation cap until after the deadline
    j = w.jobrow(jid)
    assert j["status"] == "dead" and "deadline" in (j["last_error"] or "")  # never reported as success
    assert len(notices(w)) == 1 and w.all_ccs() == [] and w.provider_calls == 1  # no new investigation
    assert not w.worker().run_once()  # nothing left: no loop
    owner.execute("UPDATE job SET run_after = now() WHERE id = %s", (jid,))
    assert not w.worker().run_once() and len(notices(w)) == 1  # and no duplicate notice


def test_a1_notice_failure_ends_the_job_without_a_retry_loop(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    w.run()
    owner.execute("UPDATE job SET deadline_at = now() - interval '1 second', run_after = now() WHERE id = %s", (jid,))
    w.state.fault("POST", "cr", 502)  # the notice itself cannot be published
    w.run()
    assert w.jobrow(jid)["status"] == "dead" and notices(w) == []
    assert not w.worker().run_once()


def test_a1_never_run_jobs_past_the_deadline_are_still_dropped_silently(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()  # logs were never fetched: FS-ERR-1 does not apply
    owner.execute("UPDATE job SET deadline_at = now() - interval '1 second' WHERE id = %s", (jid,))
    assert not w.worker().run_once()
    assert w.jobrow(jid)["status"] == "dead" and w.state.writes == []


def test_a1_cancelled_and_duplicate_work_is_not_revived(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    w.run()
    owner.execute(
        "UPDATE job SET status = 'cancelled', finished_at = now(), deadline_at = now() - interval '1 second',"
        " run_after = now() WHERE id = %s",
        (jid,),
    )
    assert not w.worker().run_once() and w.jobrow(jid)["status"] == "cancelled" and notices(w) == []


# ------------------------------------------------------------------ A2


def test_a2_cooldown_skipped_delivery_stays_in_the_window_until_retried(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(21, "g-d")]
    redeliver(pool, hub, now=lambda: NOW)
    assert hub.redelivered == [21]
    # GitHub's redelivery of g-d failed again at NOW; a newer, unrelated failure g-e appears at NOW + 11:54.
    hub.deliveries = [
        delivery(22, "g-d", age=timedelta(0)),
        delivery(21, "g-d"),
        delivery(31, "g-e", age=-timedelta(minutes=11, seconds=54)),
    ]
    for k in range(1, 6):  # passes every 12 minutes; the cooldown is 15 minutes
        redeliver(pool, hub, now=lambda k=k: NOW + timedelta(minutes=12 * k))
    assert count(owner, "SELECT attempts FROM redelivery_request WHERE guid = 'g-d'") >= 2  # retried after the cooldown
    assert hub.redelivered.count(31) <= 3  # the newer delivery stays under its own attempt cap


def test_a2_cooldown_does_not_cause_a_busy_retry_loop(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(21, "g-d", age=timedelta(0))]
    t = NOW
    for _ in range(12):  # passes every 2 minutes for 24 minutes
        redeliver(pool, hub, now=lambda t=t: t)
        t += timedelta(minutes=2)
    assert hub.redelivered.count(21) == 2  # at 0 and after the 15-minute cooldown, never in between


def test_a2_attempt_cap_releases_the_window(pool, owner) -> None:  # type: ignore[no-untyped-def]
    """Realistic: every redelivery of g-d fails again and appears as a new attempt at the time it was requested,
    while a newer, unrelated failure keeps moving `newest` ahead. g-d is requested exactly up to the cap, and once
    capped it no longer holds the high-water mark back."""
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(21, "g-d", age=timedelta(0)), delivery(31, "g-e", age=-timedelta(minutes=5))]
    next_id = 100
    for k in range(6):  # passes every 16 minutes (cooldown 15)
        t = NOW + timedelta(minutes=16 * k)
        before = len(hub.redelivered)
        redeliver(pool, hub, now=lambda t=t: t)
        for did in hub.redelivered[before:]:
            guid = next(d["guid"] for d in hub.deliveries if d["id"] == did)
            next_id += 1  # GitHub records the redelivery as a new (failed) attempt at the request time
            hub.deliveries.insert(0, delivery(next_id, guid, age=-(t - NOW)))
    gd_ids = {d["id"] for d in hub.deliveries if d["guid"] == "g-d"}
    assert sum(1 for r in hub.redelivered if r in gd_ids) == 3  # the cap still applies
    hw = owner.execute("SELECT value FROM recovery_checkpoint WHERE key = 'deliveries:high_water'").fetchone()[0]
    newest = max(d["delivered_at"] for d in hub.deliveries)
    assert hw.replace("+00:00", "Z") == newest  # nothing is held once both deliveries are capped
