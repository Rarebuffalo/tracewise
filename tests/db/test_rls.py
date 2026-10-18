"""T-705: row-level security and tenant isolation, exercised as the ACTUAL runtime role (`tracewise_app`).

Two installations (9 → repo 1, 10 → repo 2) are seeded through the system plane. Every assertion about
isolation is made on a `tenant_pool` connection, which logs in as `tracewise_app` (no BYPASSRLS, not the
table owner), so the policies in migration 0005 are what allow or deny each statement.
"""

from __future__ import annotations

import threading
from typing import Any

import psycopg
import pytest

from tests.pg import APP, OWNER, SYSTEM
from tracewise.db import repositories as repo
from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import transaction
from tracewise.jobs import queue

TENANT_TABLES = (
    "installation",
    "repository",
    "workflow_run",
    "job",
    "analysis",
    "publication",
    "failure_signature",
    "usage_event",
    "audit_event",
    "webhook_delivery",
)


def _seed_tenant(conn: Any, inst: int, repo_id: int) -> dict[str, int]:
    repo.upsert_installation(conn, inst, f"acct{inst}")
    repo.upsert_repository(conn, repo_id, inst, f"acct{inst}/r")
    run = repo.insert_workflow_run(
        conn,
        installation_id=inst,
        repo_id=repo_id,
        run_id=500 + inst,
        attempt=1,
        workflow_id=3,
        head_sha="c" * 40,
        head_branch="main",
        head_repo_id=repo_id,
        event="push",
        conclusion="failure",
    )
    a = repo.upsert_analysis(
        conn, installation_id=inst, run_pk=run, status="diagnosed", category=None, confidence_band=None, diagnosis=None
    )
    p = repo.reserve_publication(conn, installation_id=inst, analysis_id=a, surface="check_run", target_key=f"cr:{inst}")
    repo.record_signature(conn, repo_id=repo_id, fingerprint="f" * 16, installation_id=inst, normalized_message="m", run_pk=run)
    repo.add_usage(conn, inst, "analysis", 1, a)
    repo.audit(conn, "test", "seed", inst)
    repo.insert_delivery(conn, f"d{inst}", "workflow_run", "completed", inst, "enqueued")
    j = queue.enqueue(conn, kind="analyze", installation_id=inst, dedupe_key=f"k{inst}", payload={"repo_id": repo_id})
    assert j is not None
    return {"run": run, "analysis": a, "publication": int(p["id"]), "job": j}


@pytest.fixture
def two(pool) -> dict[int, dict[str, int]]:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:  # system plane (BYPASSRLS) seeds both tenants
        return {9: _seed_tenant(c, 9, 1), 10: _seed_tenant(c, 10, 2)}


def _visible(conn: Any, table: str) -> set[int]:
    col = "id" if table == "installation" else "installation_id"
    return {r[col] for r in conn.execute(f"SELECT {col} FROM {table}").fetchall()}  # noqa: S608 - fixed table names


def test_runtime_roles_are_what_the_policies_assume(owner) -> None:  # type: ignore[no-untyped-def]
    rows = owner.execute(
        "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname", ([APP, SYSTEM],)
    ).fetchall()
    assert rows == [(APP, False, False), (SYSTEM, False, True)]
    for t in TENANT_TABLES:
        owner_name, rls = owner.execute(
            "SELECT pg_get_userbyid(relowner), relrowsecurity FROM pg_class WHERE oid = %s::regclass", (t,)
        ).fetchone()
        assert owner_name == OWNER and rls is True, t  # neither runtime role owns a table, so RLS applies to it


def test_tenant_sees_and_changes_only_its_own_rows(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    with transaction(tenant_pool, tenant=9) as c:
        assert c.execute("SELECT current_user AS u").fetchone() == {"u": APP}
        for t in TENANT_TABLES:
            assert _visible(c, t) == {9}, t
        assert repo.repository_scope(c, 2) is None  # repo 2 belongs to installation 10
        assert repo.repository_scope(c, 1)["installation_id"] == 9
        # Writes to another tenant's rows match nothing; they are not errors, and nothing changes.
        assert c.execute("UPDATE analysis SET status = 'inconclusive' WHERE id = %s", (two[10]["analysis"],)).rowcount == 0
        assert c.execute("UPDATE publication SET state = 'failed' WHERE installation_id = 10").rowcount == 0
        assert c.execute("DELETE FROM job WHERE installation_id = 10").rowcount == 0
        assert c.execute("UPDATE repository SET enabled = false WHERE id = 2").rowcount == 0
        # Its own rows are writable.
        assert c.execute("UPDATE analysis SET status = 'inconclusive' WHERE id = %s", (two[9]["analysis"],)).rowcount == 1
        repo.add_usage(c, 9, "analysis", 2)
    with transaction(tenant_pool, tenant=10) as c:
        assert {r["status"] for r in c.execute("SELECT status FROM analysis").fetchall()} == {"diagnosed"}
        assert c.execute("SELECT count(*) AS n FROM usage_event").fetchone() == {"n": 1}


def test_tenant_cannot_insert_or_move_rows_into_another_tenant(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        repo.add_usage(c, 10, "analysis", 1)  # WITH CHECK rejects a row for installation 10
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        repo.audit(c, "x", "y", 10)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        c.execute("UPDATE analysis SET installation_id = 10 WHERE id = %s", (two[9]["analysis"],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        repo.reserve_publication(c, installation_id=10, analysis_id=two[10]["analysis"], surface="pr_comment", target_key="x")


def test_missing_context_sees_nothing_and_writes_nothing(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    with transaction(tenant_pool) as c:
        for t in TENANT_TABLES:
            assert _visible(c, t) == set(), t
        assert c.execute("UPDATE job SET status = 'cancelled'").rowcount == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool) as c:
        repo.add_usage(c, 9, "analysis", 1)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool) as c:
        c.execute("SELECT set_config('tracewise.installation_id', '', true)")  # an empty value is "no tenant"
        repo.add_usage(c, 9, "analysis", 1)


def test_invalid_context_is_an_error_not_a_wildcard(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    for bad in ("9 OR true", "abc", "9;10"):
        with pytest.raises(psycopg.errors.InvalidTextRepresentation), transaction(tenant_pool) as c:
            c.execute("SELECT set_config('tracewise.installation_id', %s, true)", (bad,))
            c.execute("SELECT id FROM installation").fetchall()
    with transaction(tenant_pool, tenant=999) as c:  # a well-formed but unknown tenant sees nothing
        assert all(_visible(c, t) == set() for t in TENANT_TABLES)
    for bad_arg in (0, -1, True, "9"):
        with pytest.raises(ValueError):
            with transaction(tenant_pool, tenant=bad_arg):  # type: ignore[arg-type]
                pass


def test_context_is_transaction_local_on_reused_pooled_connections(pg, two) -> None:  # type: ignore[no-untyped-def]
    from tracewise.db.session import make_pool

    p = make_pool(pg.url(APP), min_size=1, max_size=1)  # one connection: every transaction reuses it
    try:
        with transaction(p, tenant=9) as c:
            pid = c.execute("SELECT pg_backend_pid() AS p").fetchone()["p"]
            assert _visible(c, "job") == {9}
        with transaction(p) as c:  # after COMMIT
            assert c.execute("SELECT pg_backend_pid() AS p").fetchone()["p"] == pid
            assert c.execute("SELECT current_setting('tracewise.installation_id', true) AS s").fetchone()["s"] in ("", None)
            assert _visible(c, "job") == set()
        with pytest.raises(RuntimeError), transaction(p, tenant=9) as c:
            assert _visible(c, "job") == {9}
            raise RuntimeError("abort")
        with transaction(p) as c:  # after ROLLBACK
            assert c.execute("SELECT pg_backend_pid() AS p").fetchone()["p"] == pid
            assert _visible(c, "job") == set()
    finally:
        p.close()


def test_concurrent_transactions_with_different_tenants_stay_separate(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    barrier = threading.Barrier(2)
    seen: dict[int, list[set[int]]] = {9: [], 10: []}
    errors: list[BaseException] = []

    def work(inst: int) -> None:
        try:
            for _ in range(20):
                with transaction(tenant_pool, tenant=inst) as c:
                    barrier.wait(timeout=10)  # both transactions are open at the same time
                    seen[inst].append(_visible(c, "analysis") | _visible(c, "publication") | _visible(c, "job"))
                    repo.add_usage(c, inst, "analysis", 1)
        except BaseException as e:  # surfaced below
            errors.append(e)

    ts = [threading.Thread(target=work, args=(i,)) for i in (9, 10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == []
    assert seen[9] == [{9}] * 20 and seen[10] == [{10}] * 20
    for inst in (9, 10):
        with transaction(tenant_pool, tenant=inst) as c:
            assert c.execute("SELECT count(*) AS n FROM usage_event").fetchone() == {"n": 21}


def test_tenant_role_cannot_use_system_plane_tables_or_bypass(tenant_pool, two) -> None:  # type: ignore[no-untyped-def]
    for sql in (
        "SELECT * FROM recovery_checkpoint",
        "INSERT INTO recovery_checkpoint (key, value) VALUES ('k', 'v')",
        "SELECT * FROM redelivery_request",
        "SET row_security = off",  # allowed as a setting, but then any RLS-filtered query errors instead of bypassing
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
            c.execute(sql)
            c.execute("SELECT id FROM job").fetchall()
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=9) as c:
        c.execute("ALTER TABLE job DISABLE ROW LEVEL SECURITY")


def test_system_plane_sees_all_tenants_and_audit_is_append_only(pool, two) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        assert c.execute("SELECT current_user AS u").fetchone() == {"u": SYSTEM}
        for t in TENANT_TABLES:
            assert _visible(c, t) == {9, 10}, t
        assert queue.cancel_pending(c, installation_id=10, reason="cancelled_uninstalled") == 1
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("UPDATE audit_event SET action = 'x'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("DELETE FROM audit_event")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("DELETE FROM analysis")  # no DELETE on tenant content for the system role


def test_migration_0005_roundtrip(pg, owner, two) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER), "0004")
    assert owner.execute("SELECT count(*) FROM pg_policies").fetchone() == (0,)
    assert owner.execute("SELECT to_regproc('tracewise_tenant')").fetchone() == (None,)
    with psycopg.connect(pg.url(APP)) as c:  # without RLS the tenant role reads everything again
        assert {r[0] for r in c.execute("SELECT installation_id FROM job")} == {9, 10}
    upgrade(pg.url(OWNER))
    assert owner.execute("SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation'").fetchone() == (10,)
    with psycopg.connect(pg.url(APP)) as c:
        assert c.execute("SELECT count(*) FROM job").fetchone() == (0,)
