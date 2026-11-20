"""D-1 / D-2: database-backed attempt fencing. A worker whose lease was reaped and whose job was reclaimed by a newer
attempt must not persist, publish, complete, fail, cancel or renew anything. Offline: disposable PostgreSQL, the real
queue and handler, scripted providers and fake GitHub. Deterministic: takeovers happen at fixed points via script
callbacks, and heartbeats are slowed so the worker-local `lease_lost` flag never fires (the database alone decides)."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import re
import threading
from typing import Any

import psycopg
import pytest

from tests.db.test_analyze_worker import World, call, final, head, known, server  # noqa: F401 - module fixtures
from tests.pg import OWNER, SYSTEM
from tracewise.db.session import DatabaseUnavailable, make_pool, transaction
from tracewise.github.client import RepoClient
from tracewise.github.publish import Publisher
from tracewise.jobs import queue
from tracewise.jobs.queue import Fence, StaleAttempt

SLOW_BEAT = 3600.0  # the heartbeat never runs during a test: no local lease-lost signal


def make_world(pool: Any, owner: Any, server: Any, tmp_path: Any, head: str, tenant_pool: Any, **kw: Any) -> World:
    w = World(pool, owner, server, tmp_path / "ws", head, **kw)
    w.tenant_pool = tenant_pool  # the handler's writes run on the tenant plane (RLS), as in production
    return w


def expire(owner: Any, jid: int) -> None:
    owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE id = %s", (jid,))


def claim_as(pool: Any, worker: str) -> queue.Job:
    with transaction(pool) as c:
        j = queue.claim(c, worker)
    assert j is not None
    return j


def analysis_root_cause(owner: Any) -> str:
    (d,) = owner.execute("SELECT diagnosis FROM analysis").fetchone()
    return str(d["root_cause"])


# ------------------------------------------------------------------ A: stale persistence (D-1)


def test_a_stale_attempt_cannot_overwrite_the_newer_attempts_analysis(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    """Worker A is mid-investigation when its lease expires; worker B reclaims the job and finishes it. A then
    resumes with its own answer. Before fencing, A's upsert replaced B's analysis and A re-published."""
    w: World

    def takeover(req: Any) -> Any:
        expire(owner, jid)
        assert w.worker("wB", heartbeat_s=SLOW_BEAT).run_once()  # B: reclaim (attempt 2), investigate, publish, complete
        return final(root_cause="STALE answer from the reclaimed attempt (total() is wrong).")

    w = make_world(
        pool,
        owner,
        server,
        tmp_path,
        head,
        tenant_pool,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), takeover], known()],
    )
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 2, "diagnosed")  # B's completion
    assert "STALE" not in analysis_root_cause(owner)  # B's analysis intact
    assert (w.state.count("POST", "cc"), w.state.count("POST", "cr")) == (1, 1)  # only B published
    assert all("STALE" not in str(x) for x in w.state.writes)  # nothing of A's answer reached GitHub


# ------------------------------------------------------------------ B, C, D: stale queue transitions (D-2)


@pytest.mark.parametrize("second", ["wB", "w1"], ids=["other-worker", "same-worker-id"])
def test_bcd_a_stale_attempt_cannot_complete_fail_cancel_or_renew(pool, owner, second) -> None:  # type: ignore[no-untyped-def]
    """`same-worker-id`: two replicas with the same `--worker-id`, or a restarted container with the same hostname
    and pid. Before fencing on the attempt, the stale attempt could complete or fail the newer one."""
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active')")
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="d-1", payload={})
    a = claim_as(pool, "w1")
    expire(owner, jid)
    b = claim_as(pool, second)
    assert (a.attempts, b.attempts) == (1, 2)
    with transaction(pool) as c:
        assert not queue.heartbeat(c, jid, "w1", attempt=1)  # D: no renewal of the obsolete lease
        assert not queue.complete(c, jid, "w1", {"outcome": "stale"}, attempt=1)  # B: no completion
        assert queue.fail(c, jid, "w1", RuntimeError("stale"), attempt=1) is None  # C: no retry, no dead
        assert not queue.cancel_running(c, jid, "w1", "stale", attempt=1)
    row = owner.execute("SELECT status, attempts, locked_by, result, last_error FROM job WHERE id = %s", (jid,)).fetchone()
    assert row[:3] == ("running", 2, second) and row[3] is None and row[4] == "lease expired"  # untouched
    with transaction(pool) as c:
        assert queue.heartbeat(c, jid, second, attempt=2) and queue.complete(c, jid, second, {"outcome": "ok"}, attempt=2)


def test_c_a_stale_attempt_cannot_dead_letter_the_job(pool, owner) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active')")
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="d-2", payload={})
    claim_as(pool, "w1")
    expire(owner, jid)
    claim_as(pool, "w1")
    with transaction(pool) as c:
        assert queue.fail(c, jid, "w1", queue.PermanentError("stale permanent"), attempt=1) is None
    assert owner.execute("SELECT status, attempts FROM job WHERE id = %s", (jid,)).fetchone() == ("running", 2)


# ------------------------------------------------------------------ E: simultaneous claims


def test_e_simultaneous_claims_produce_exactly_one_owner(pool, owner) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active')")
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="d-3", payload={})
    gate = threading.Barrier(6)
    got: list[queue.Job | None] = []
    lock = threading.Lock()

    def racer(name: str) -> None:
        gate.wait()
        with transaction(pool) as c:
            j = queue.claim(c, name)
        with lock:
            got.append(j)

    threads = [threading.Thread(target=racer, args=(f"r{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    owners = [j for j in got if j is not None]
    assert len(got) == 6 and len(owners) == 1 and owners[0].id == jid and owners[0].attempts == 1
    assert owner.execute("SELECT locked_by FROM job WHERE id = %s", (jid,)).fetchone() == (owners[0].locked_by,)


# ------------------------------------------------------------------ F: stale publication


def test_f_a_stale_attempt_is_stopped_before_its_github_request(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    """Takeover after A persisted but before A's first publication request: the pre-request check refuses it."""
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    taken: list[queue.Job] = []
    real_find = Publisher._find_comment

    def find_then_takeover(self: Any, surface: str, endpoint: str, tag: str, **params: Any) -> Any:
        out = real_find(self, surface, endpoint, tag, **params)
        if not taken:
            expire(owner, jid)
            taken.append(claim_as(pool, "wB"))  # B owns attempt 2 from here on
        return out

    monkeypatch.setattr("tracewise.github.publish.Publisher._find_comment", find_then_takeover)
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert w.state.count("POST", "cc") == 0 and w.state.count("POST", "cr") == 0  # A wrote nothing to GitHub
    assert owner.execute("SELECT count(*) FROM publication WHERE state = 'published'").fetchone() == (0,)
    assert owner.execute("SELECT status, attempts, locked_by FROM job WHERE id = %s", (jid,)).fetchone() == (
        "running",
        2,
        "wB",
    )


def test_f_the_remaining_boundary_a_request_in_flight_at_takeover_is_never_recorded_and_never_duplicated(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    """The documented limit: ownership changes while A's request is in flight (after its last check). GitHub
    applied it; that cannot be undone. A cannot record it (the locked check before marking fails, the transaction
    rolls back), and the next owner reconciles: it adopts the existing object instead of creating a second one."""
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    real = RepoClient.request
    done: list[bool] = []

    def request(self: RepoClient, name: str, **kw: Any) -> Any:
        out = real(self, name, **kw)
        if name == "create_commit_comment" and not done:
            done.append(True)
            expire(owner, jid)
            claim_as(pool, "wB")  # takeover while A's request is "in flight"
        return out

    monkeypatch.setattr(RepoClient, "request", request)
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    assert w.state.count("POST", "cc") == 1  # applied by GitHub before the takeover was visible
    assert owner.execute("SELECT count(*) FROM publication WHERE state = 'published'").fetchone() == (0,)  # not recorded
    expire(owner, jid)  # B never runs here; a third attempt takes over and finishes
    assert w.worker("wC", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("succeeded", 3)
    assert w.state.count("POST", "cc") == 1  # adopted, not duplicated (write-once surface)
    assert w.pubs()["commit_comment"][0] == "published"


# ------------------------------------------------------------------ G: normal execution and the fence itself


def test_g_the_current_attempt_runs_unchanged(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 1, "diagnosed")
    assert (w.state.count("POST", "cc"), w.state.count("POST", "cr")) == (1, 1)


def test_the_fence_answers_only_for_its_own_tenant(pool, owner, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active'), (8, 'b', 'active')")
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="d-4", payload={})
    j = claim_as(pool, "w1")
    mine = Fence(jid, 9, "w1", j.attempts)
    with transaction(tenant_pool, tenant=9) as c:
        assert mine.owned(c)
    with transaction(tenant_pool, tenant=8) as c:  # another installation's transaction learns nothing
        assert not mine.owned(c)
    with transaction(tenant_pool, tenant=9) as c:
        assert not Fence(jid, 9, "w1", j.attempts + 1).owned(c) and not Fence(jid, 9, "w2", j.attempts).owned(c)
        with pytest.raises(StaleAttempt):
            Fence(jid, 9, "w2", j.attempts).verify(c, "test")


def test_a_fenced_write_holds_off_the_reaper_until_it_commits(pg, pool, owner, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    """The locked check (FOR SHARE) makes check-then-write atomic: a takeover cannot slip in before the commit."""
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active')")
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key="d-5", payload={})
    j = claim_as(pool, "w1")
    expire(owner, jid)  # expired but not yet reaped: still exclusively this attempt's
    reaper = make_pool(pg.url(SYSTEM), min_size=1, max_size=1, statement_timeout_ms=2000, lock_timeout_ms=300)
    try:
        with transaction(tenant_pool, tenant=9) as c:
            Fence(jid, 9, "w1", j.attempts).verify(c, "persist")  # row locked until this block commits
            with pytest.raises(DatabaseUnavailable), transaction(reaper) as rc:
                queue.reap_expired(rc)  # waits on the lock, gives up at lock_timeout
        with transaction(reaper) as rc:
            assert queue.reap_expired(rc) == 1  # after the commit the reaper proceeds
    finally:
        reaper.close()
    with psycopg.connect(pg.url(OWNER)) as k:
        assert k.execute("SELECT status FROM job WHERE id = %s", (jid,)).fetchone() == ("retry_wait",)


# ------------------------------------------------------------------ D-A / D-B at the handler


def test_d_a_a_permanent_github_error_ends_the_job_with_a_notice_not_silently(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    """Before: `except PermanentError: raise` ran ahead of the notice branch, so the job died with nothing shown."""
    from tests.github_fake import jresp

    w = make_world(pool, owner, server, tmp_path, head, tenant_pool)
    w.gh.routes.insert(
        0, ("GET", re.compile(r"^/repos/acme/coffee/actions/runs/55/attempts/\d+/jobs$"), lambda r: jresp(422, {}))
    )
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert j["status"] == "dead" and j["attempts"] == 1 and (j["last_error"] or "").startswith("permanent")
    (cr,) = w.state.check_runs  # FS-ERR-1: the user is told the analysis could not complete
    assert "could not complete" in cr["output"]["title"].lower() and cr["conclusion"] == "neutral"
    assert w.all_ccs() == [] and w.provider_calls == 0  # no diagnosis, no model spend


def test_d_b_a_validation_outage_retries_the_attempt_and_is_never_judged_as_an_answer(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, monkeypatch
) -> None:
    from tracewise.investigate.validate import ValidationUnavailable

    def outage(*a: Any, **kw: Any) -> Any:
        raise ValidationUnavailable("synthetic")

    monkeypatch.setattr("tracewise.jobs.handlers.analyze.diagnose", outage)
    w = make_world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    assert w.worker("wA", heartbeat_s=SLOW_BEAT).run_once()
    j = w.jobrow(jid)
    assert j["status"] == "retry_wait" and "validation could not read the code" in (j["last_error"] or "")
    assert owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,) and w.state.writes == []
