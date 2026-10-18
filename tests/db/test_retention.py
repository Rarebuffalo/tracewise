"""T-704 retention and tenant purge (FS-SEC-3, FS-INS-3; AT-SEC-12, AT-INS-03), on a disposable Postgres.

Ages are produced by back-dating rows as the owner. The purge itself runs as the system role, through the
fixed-policy `tracewise_purge()` function, exactly as `python -m tracewise.retention` does.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.db.test_analyze_worker import World, head, known, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import client as client
from tests.db.test_lifecycle import failure, inst, send
from tests.investigate.factory import PRICING
from tests.pg import APP, OWNER
from tracewise import retention
from tracewise.db import repositories as repo
from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import make_pool, transaction
from tracewise.jobs import queue

TENANT_TABLES = (
    "repository",
    "workflow_run",
    "job",
    "analysis",
    "publication",
    "failure_signature",
    "usage_event",
    "webhook_delivery",
    "redelivery_request",
)


def seed(pool: Any, iid: int, repo_id: int, n: int = 1) -> list[int]:
    """n runs, each with an analysis (+ diagnosis), two publications, usage, a fingerprint, a delivery and a job."""
    out = []
    with transaction(pool) as c:
        repo.set_installation_status(c, iid, "active", f"acct{iid}")
        repo.repository_added(c, repo_id, iid, f"acct{iid}/r")
        for k in range(n):
            run = repo.insert_workflow_run(
                c,
                installation_id=iid,
                repo_id=repo_id,
                run_id=1000 * iid + k,
                attempt=1,
                workflow_id=3,
                head_sha="c" * 40,
                head_branch="main",
                head_repo_id=repo_id,
                event="push",
                conclusion="failure",
            )
            a = repo.upsert_analysis(
                c,
                installation_id=iid,
                run_pk=run,
                status="diagnosed",
                category="code_regression",
                confidence_band="medium",
                diagnosis={"primary_errors": [{"excerpt": "E assert 1 == 2"}]},
            )
            for surface in ("commit_comment", "check_run"):
                repo.reserve_publication(
                    c, installation_id=iid, analysis_id=a, surface=surface, target_key=f"{surface}:{iid}:{k}"
                )
            repo.add_usage(c, iid, "analysis", 1, a)
            repo.record_signature(
                c, repo_id=repo_id, fingerprint=f"{iid:08x}{k:08x}", installation_id=iid, normalized_message="assert", run_pk=run
            )
            repo.insert_delivery(c, f"d-{iid}-{k}", "workflow_run", "completed", iid, "enqueued")
            jid = queue.enqueue(c, kind="analyze", installation_id=iid, dedupe_key=f"j-{iid}-{k}", payload={"repo_id": repo_id})
            c.execute("UPDATE job SET status='succeeded', finished_at=now() WHERE id=%s", (jid,))
            repo.audit(c, "test", "seeded", iid)
            out.append(a)
        c.execute(
            "INSERT INTO redelivery_request (guid, github_delivery_id, installation_id, event, attempts, last_requested_at)"
            " VALUES (%s, 1, %s, 'workflow_run', 1, now())",
            (f"g-{iid}", iid),
        )
    return out


def counts(owner: Any, iid: int) -> dict[str, int]:
    return {
        t: owner.execute(f"SELECT count(*) FROM {t} WHERE installation_id = %s", (iid,)).fetchone()[0]  # noqa: S608
        for t in (*TENANT_TABLES, "audit_event")
    }


def age(owner: Any, table: str, column: str, days: float, where: str = "true") -> None:
    owner.execute(f"UPDATE {table} SET {column} = now() - make_interval(secs => %s) WHERE {where}", (days * 86400,))  # noqa: S608


def run(pool: Any, **kw: Any) -> retention.PurgeSummary:
    s = retention.purge(pool, **kw)
    assert s.error is None, s
    return s


def test_empty_database_completes_with_nothing_deleted(pool, owner) -> None:  # type: ignore[no-untyped-def]
    s = run(pool)
    assert s.completed and s.batches == 1 and sum(s.deleted.values()) == 0 and s.tenants_purged == []


def test_age_boundaries_mixed_eligible_and_ineligible(pool, owner) -> None:  # type: ignore[no-untyped-def]
    a_old, a_mid, a_new = seed(pool, 9, 1, n=3)
    # analysis content: 90 days; rows: 180 days (updated_at)
    age(owner, "analysis", "updated_at", 181, f"id = {a_old}")
    age(owner, "analysis", "updated_at", 90.01, f"id = {a_mid}")
    age(owner, "analysis", "updated_at", 89.9, f"id = {a_new}")
    # deliveries 14 days; fingerprints, runs, jobs, usage, audit, redelivery 365 days
    age(owner, "webhook_delivery", "received_at", 14.01, "delivery_id = 'd-9-0'")
    age(owner, "webhook_delivery", "received_at", 13.9, "delivery_id = 'd-9-1'")
    age(owner, "failure_signature", "last_seen_at", 365.01, "fingerprint = '0000000900000000'")
    age(owner, "failure_signature", "last_seen_at", 364.9, "fingerprint = '0000000900000001'")
    age(owner, "job", "finished_at", 365.01, "dedupe_key = 'j-9-0'")
    age(owner, "job", "finished_at", 364.9, "dedupe_key = 'j-9-1'")
    owner.execute(
        "UPDATE job SET status='queued', finished_at=NULL, created_at = now() - interval '900 days' WHERE dedupe_key='j-9-2'"
    )
    age(owner, "usage_event", "created_at", 365.01, f"analysis_id = {a_mid}")
    age(owner, "audit_event", "created_at", 365.01, "id = (SELECT min(id) FROM audit_event)")
    age(owner, "redelivery_request", "last_requested_at", 365.01)
    age(owner, "workflow_run", "created_at", 400)  # all old, but referenced runs must survive

    s = run(pool)
    assert s.completed
    rows = {
        r[0]: (r[1] is not None, r[2] is not None) for r in owner.execute("SELECT id, diagnosis, content_purged_at FROM analysis")
    }
    assert rows == {a_mid: (False, True), a_new: (True, False)}  # a_old deleted; a_mid content stripped; a_new intact
    assert owner.execute("SELECT count(*) FROM publication WHERE analysis_id = %s", (a_old,)).fetchone() == (0,)
    assert owner.execute("SELECT count(*) FROM publication").fetchone() == (4,)
    assert owner.execute("SELECT count(*) FROM usage_event WHERE analysis_id IS NULL").fetchone() == (1,)  # a_old's, detached
    assert {r[0] for r in owner.execute("SELECT delivery_id FROM webhook_delivery")} == {"d-9-1", "d-9-2"}
    assert {r[0] for r in owner.execute("SELECT fingerprint FROM failure_signature")} == {"0000000900000001", "0000000900000002"}
    assert {r[0] for r in owner.execute("SELECT dedupe_key FROM job")} == {"j-9-1", "j-9-2"}  # queued j-9-2 never touched
    assert owner.execute("SELECT count(*) FROM audit_event").fetchone() == (2,)
    assert owner.execute("SELECT count(*) FROM redelivery_request").fetchone() == (0,)
    assert owner.execute("SELECT count(*) FROM workflow_run").fetchone() == (2,)  # a_old's run (unreferenced now) went
    assert dict(s.deleted) | {} == {
        "analysis_content": 2,  # a_mid, and a_old (stripped, then deleted in the same batch)
        "analysis": 1,
        "publication": 2,
        "webhook_delivery": 1,
        "failure_signature": 1,
        "workflow_run": 1,
        "job": 1,
        "usage_event": 1,
        "audit_event": 1,
        "redelivery_request": 1,
        "tenant_rows": 0,
    }
    again = run(pool)  # idempotent
    assert again.completed and sum(again.deleted.values()) == 0


def test_batches_are_bounded_and_an_interrupted_run_resumes(pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, 9, 1)
    with transaction(pool) as c:
        for k in range(25):
            repo.insert_delivery(c, f"old-{k}", "workflow_run", "completed", 9, "ignored")
    age(owner, "webhook_delivery", "received_at", 20)
    s1 = run(pool, batch_limit=10, max_batches=1)
    assert (s1.completed, s1.deleted["webhook_delivery"]) == (False, 10)
    s2 = run(pool, batch_limit=10, max_batches=10)
    assert (
        s2.completed and s2.deleted["webhook_delivery"] == 16 and s2.batches == 2
    )  # 10 + 6; a short batch means nothing more is due
    assert owner.execute("SELECT count(*) FROM webhook_delivery").fetchone() == (0,)
    with pytest.raises(ValueError):
        retention.purge(pool, batch_limit=0)


def test_tenant_purge_removes_only_the_deleted_tenant_and_keeps_a_tombstone(pool, owner, client) -> None:  # type: ignore[no-untyped-def]
    seed(pool, 9, 1, n=2)
    seed(pool, 10, 2, n=2)
    before9 = counts(owner, 9)
    with transaction(pool) as c:
        assert queue.cancel_pending(c, installation_id=10, reason="x") == 0
        repo.mark_installation_deleted(c, 10)
    s = run(pool)
    assert s.tenants_purged == [] and counts(owner, 10)["analysis"] == 2  # grace period not over
    owner.execute("UPDATE installation SET purge_after = now() - interval '1 second' WHERE id = 10")
    s = run(pool)
    assert s.completed and s.tenants_purged == [10]
    after10 = counts(owner, 10)
    assert {t: after10[t] for t in TENANT_TABLES} == dict.fromkeys(TENANT_TABLES, 0)
    assert after10["audit_event"] == 3  # 2 seeded + tenant_purged; kept for their own 365 days
    assert counts(owner, 9) == before9  # the other tenant is untouched
    tomb = owner.execute("SELECT status, account_login, purged_at IS NOT NULL FROM installation WHERE id = 10").fetchone()
    assert tomb == ("deleted", None, True)
    assert owner.execute("SELECT action FROM audit_event WHERE installation_id = 10 ORDER BY id DESC LIMIT 1").fetchone() == (
        "tenant_purged",
    )
    for late in (inst("created", 10, repos=[(2, "acct10/r")]), inst("unsuspend", 10)):
        send(client, "installation", late)  # D-10: the tombstone stays deleted
    assert owner.execute("SELECT status FROM installation WHERE id = 10").fetchone() == ("deleted",)
    assert send(client, "workflow_run", failure(repo_id=2, iid=10, name="acct10/r")).json()["outcome"] == "installation_inactive"
    assert run(pool).tenants_purged == []  # purged once


def test_tenant_purge_is_bounded_resumable_and_waits_for_in_flight_jobs(pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, 10, 2, n=6)
    with transaction(pool) as c:
        repo.mark_installation_deleted(c, 10)
        running = queue.enqueue(c, kind="analyze", installation_id=10, dedupe_key="live", payload={"repo_id": 2})
    owner.execute(
        "UPDATE job SET status='running', locked_by='w', locked_until=now() + interval '1 minute' WHERE id=%s", (running,)
    )
    owner.execute("UPDATE installation SET purge_after = now() - interval '1 day' WHERE id = 10")
    s = run(pool)
    assert s.tenants_waiting_for_jobs == 1 and s.tenants_purged == [] and counts(owner, 10)["analysis"] == 6
    owner.execute(
        "UPDATE job SET status='cancelled', locked_by=NULL, locked_until=NULL, finished_at=now() WHERE id=%s", (running,)
    )
    s1 = run(pool, batch_limit=2, max_batches=2)  # interrupted mid-tenant
    assert not s1.completed and s1.tenants_purged == []
    assert owner.execute("SELECT purged_at FROM installation WHERE id = 10").fetchone() == (None,)
    s2 = run(pool, batch_limit=2, max_batches=100)
    assert s2.completed and s2.tenants_purged == [10]
    assert {t: v for t, v in counts(owner, 10).items() if t != "audit_event"} == dict.fromkeys(TENANT_TABLES, 0)


def test_deleted_without_purge_date_is_reported_not_guessed(pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, 10, 2)
    owner.execute("UPDATE installation SET status = 'deleted', purge_after = NULL WHERE id = 10")
    s = run(pool)
    assert s.tenants_without_purge_after == 1 and s.tenants_purged == [] and counts(owner, 10)["analysis"] == 1


def test_delivery_purge_keeps_run_deduplication(pool, owner, client) -> None:  # type: ignore[no-untyped-def]
    send(client, "installation", inst("created", repos=[(7, "acme/app")]))
    assert send(client, "workflow_run", failure(), "same-guid").json()["outcome"] == "enqueued"
    age(owner, "webhook_delivery", "received_at", 15)
    run(pool)
    assert owner.execute("SELECT count(*) FROM webhook_delivery WHERE delivery_id = 'same-guid'").fetchone() == (0,)
    assert send(client, "workflow_run", failure(), "same-guid").json()["outcome"] == "duplicate_run"  # run dedupe holds
    assert owner.execute("SELECT count(*) FROM job").fetchone() == (1,)


def test_privileges_only_the_system_role_may_purge_and_only_by_policy(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        c.execute("SELECT tracewise_purge(10)")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("DELETE FROM analysis")  # still no direct DELETE on content for the system role
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("DELETE FROM audit_event")
    assert owner.execute("SELECT prosecdef, proconfig FROM pg_proc WHERE proname = 'tracewise_purge'").fetchone() == (
        True,
        ["search_path=pg_catalog, public, pg_temp"],
    )
    assert owner.execute("SELECT pronargs FROM pg_proc WHERE proname = 'tracewise_purge'").fetchone() == (1,)  # no date input
    with transaction(pool) as c:
        assert c.execute("SELECT tracewise_purge(0)->>'batch_limit' AS n").fetchone() == {"n": "1"}
        assert c.execute("SELECT tracewise_purge(1000000)->>'batch_limit' AS n").fetchone() == {"n": "10000"}


def test_concurrent_purges_do_not_contend(pool, owner, pg) -> None:  # type: ignore[no-untyped-def]
    holder = psycopg.connect(pg.url("tracewise_system"))
    try:
        holder.execute("SELECT tracewise_purge(10)")  # transaction left open: holds the advisory lock
        s = run(pool)
        assert s.locked and not s.completed
    finally:
        holder.rollback()
        holder.close()
    assert run(pool).completed


def test_failures_are_reported_not_success(pg, owner, capsys) -> None:  # type: ignore[no-untyped-def]
    p = make_pool(pg.url(APP))  # the tenant role may not execute the purge: a real database error
    try:
        s = retention.purge(p)
        assert s.error == "InsufficientPrivilege" and not s.completed

        class Keep:
            def __getattr__(self, n: str) -> Any:
                return getattr(p, n)

            def close(self) -> None:
                pass

        assert retention.main([], build=lambda: Keep()) == 1  # type: ignore[arg-type, return-value]
        assert json.loads(capsys.readouterr().out)["error"] == "InsufficientPrivilege"
    finally:
        p.close()


def test_partial_failure_keeps_committed_batches(pool, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seed(pool, 9, 1)
    with transaction(pool) as c:
        for k in range(5):
            repo.insert_delivery(c, f"old-{k}", "workflow_run", "completed", 9, "ignored")
    age(owner, "webhook_delivery", "received_at", 20)
    real = retention.transaction
    calls = {"n": 0}

    def flaky(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated outage")
        return real(*a, **k)

    monkeypatch.setattr(retention, "transaction", flaky)
    s = retention.purge(pool, batch_limit=2, max_batches=10)
    assert (s.error, s.batches, s.completed, s.deleted["webhook_delivery"]) == ("RuntimeError", 1, False, 2)
    assert owner.execute("SELECT count(*) FROM webhook_delivery").fetchone() == (4,)  # the first batch stayed committed
    monkeypatch.setattr(retention, "transaction", real)
    assert run(pool).completed and owner.execute("SELECT count(*) FROM webhook_delivery").fetchone() == (0,)


def test_retention_cli_completes_and_signals_unfinished(pool, owner, capsys) -> None:  # type: ignore[no-untyped-def]
    class Keep:
        def __getattr__(self, n: str) -> Any:
            return getattr(pool, n)

        def close(self) -> None:
            pass

    with transaction(pool) as c:
        for k in range(3):
            repo.insert_delivery(c, f"old-{k}", "workflow_run", "completed", None, "ignored")
    age(owner, "webhook_delivery", "received_at", 20)
    assert retention.main(["--batch-limit", "1", "--max-batches", "1"], build=lambda: Keep()) == 3  # type: ignore[arg-type, return-value]
    assert json.loads(capsys.readouterr().out)["completed"] is False
    assert retention.main([], build=lambda: Keep()) == 0  # type: ignore[arg-type, return-value]


def test_migration_0008_roundtrip(pg, owner) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER), "0007")
    assert owner.execute("SELECT to_regproc('tracewise_purge')").fetchone() == (None,)
    upgrade(pg.url(OWNER))
    assert owner.execute(
        "SELECT has_function_privilege('tracewise_system', 'tracewise_purge(integer)', 'EXECUTE')"
    ).fetchone() == (True,)
    assert owner.execute("SELECT has_function_privilege(%s, 'tracewise_purge(integer)', 'EXECUTE')", (APP,)).fetchone() == (
        False,
    )


def test_at_sec_12_no_raw_logs_or_source_after_twenty_analyses(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.scripts = [known() for _ in range(20)]
    for attempt in range(1, 21):
        w.enqueue(attempt=attempt)
        w.run()
    assert owner.execute("SELECT count(*) FROM analysis").fetchone() == (20,)
    dump = "\n".join(
        str(v)
        for t in (*TENANT_TABLES, "installation", "audit_event")
        for row in owner.execute(f"SELECT to_jsonb(x)::text FROM {t} x").fetchall()  # noqa: S608 - fixed table names
        for v in row
    )
    from tests.helpers import fixture

    raw_log = fixture("pytest_b02.out")
    for needle in ("rootdir: /home/runner/work/coffee/coffee", "platform linux -- Python", raw_log[:400]):
        assert needle not in dump, needle  # never the raw log
    assert PRICING not in dump  # never the source file
    src_lines = [ln for ln in PRICING.splitlines() if len(ln.strip()) > 12]
    assert sum(ln in dump for ln in src_lines) <= 3  # at most the few cited lines
    for (doc,) in owner.execute("SELECT diagnosis FROM analysis"):
        for pe in (doc or {}).get("primary_errors", []):
            assert len(pe["excerpt"].encode()) <= 2048
    # ... and the retention job deletes by age (AT-SEC-12, last clause)
    age(owner, "analysis", "updated_at", 181)
    assert run(pool).deleted["analysis"] == 20 and owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,)


def test_definer_function_ignores_caller_temp_tables(pool, owner) -> None:  # type: ignore[no-untyped-def]
    """SECURITY DEFINER hardening: a caller's temp `installation`/`job` tables must not steer the purge onto an
    active tenant (pg_temp is searched first unless it is listed last in the function's search_path)."""
    seed(pool, 10, 2, n=2)
    before = counts(owner, 10)
    with transaction(pool) as c:  # the system role may create temp tables (PUBLIC has TEMP by default)
        c.execute(
            "CREATE TEMP TABLE installation (id bigint, status text, purge_after timestamptz, purged_at timestamptz, "
            "account_login text) ON COMMIT DROP"
        )
        c.execute("INSERT INTO installation VALUES (10, 'deleted', now() - interval '30 days', NULL, NULL)")
        c.execute(
            "CREATE TEMP TABLE job (id bigint, installation_id bigint, status text, finished_at timestamptz) ON COMMIT DROP"
        )
        r = c.execute("SELECT tracewise_purge(1000) AS r").fetchone()["r"]
    assert r.get("tenant") is None and r.get("tenant_purged") is None
    assert counts(owner, 10) == before
    assert owner.execute("SELECT status FROM installation WHERE id = 10").fetchone() == ("active",)
