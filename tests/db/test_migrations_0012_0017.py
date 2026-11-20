"""Release check for migrations 0012-0017 on a disposable PostgreSQL cluster (never a shared or production database).

Covers what the per-feature suites do not: an upgrade of a populated 0011 database, a downgrade/upgrade round trip
through every new revision, schema-head refusal by the worker, and an audit of every SECURITY DEFINER function. Fresh
installation from the template is `test_fresh_install.py`. The exact privilege matrix is `test_privilege_matrix.py`.
RLS is `test_rls.py`. Requeue authorisation, `SET ROLE`, audit rollback and the session-proof limit are
`test_requeue.py`."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from tests.db.test_privilege_matrix import documented, live
from tests.pg import APP, OPERATOR, OWNER, SYSTEM
from tracewise.db import repositories as repo
from tracewise.db.migrate import downgrade, head_revision, upgrade
from tracewise.db.session import SchemaMismatch, require_schema_at, transaction
from tracewise.jobs import queue

NEW = ("0012", "0013", "0014", "0015", "0016", "0017")
DEFINERS = {  # function -> roles that may EXECUTE it (besides its owner)
    "tracewise_job_owned": {APP, SYSTEM},
    "tracewise_purge": {SYSTEM},
    "tracewise_requeue": {"tracewise_operator"},
}


def populate(pool: Any) -> dict[str, int]:
    with transaction(pool) as c:
        repo.upsert_installation(c, 9, "acme")
        repo.upsert_repository(c, 7, 9, "acme/coffee")
        run = repo.insert_workflow_run(
            c, installation_id=9, repo_id=7, run_id=55, attempt=1, workflow_id=3, head_sha="c" * 40,
            head_branch="main", head_repo_id=7, event="push", conclusion="failure",
        )  # fmt: skip
        a = c.execute(  # the 0011 schema: no usage-breakdown columns yet (today's repository code would write them)
            """INSERT INTO analysis (installation_id, run_pk, status, diagnosis, provider, tokens_in, tokens_out)
               VALUES (9, %s, 'inconclusive', '{"inconclusive_reason": "logs_unavailable"}', 'none', 0, 0) RETURNING id""",
            (run,),
        ).fetchone()["id"]
        p = repo.reserve_publication(c, installation_id=9, analysis_id=a, surface="check_run", target_key="cr:1")
        repo.mark_published(c, p["id"], a, 123, source_run_id=55, source_attempt=1, content_digest="d" * 64)
        jid = queue.enqueue(
            c, kind="analyze", installation_id=9, dedupe_key="analyze:7:55:1", payload={"repo_id": 7}, run_key="7:55"
        )
        repo.audit(c, "system", "seeded", 9)
    assert jid is not None
    return {"analysis": a, "job": jid}


def test_head_is_0017_and_the_order_is_linear() -> None:
    from alembic.script import ScriptDirectory

    from tracewise.db.migrate import alembic_config

    assert head_revision() == "0017"
    scripts = ScriptDirectory.from_config(alembic_config("postgresql://unused@/unused"))
    chain = [s.revision for s in scripts.walk_revisions("base", "heads")][::-1]
    assert chain[-len(NEW) :] == list(NEW) and len(scripts.get_heads()) == 1


def test_a_populated_0011_database_upgrades_with_its_data_intact_and_round_trips(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER), "0011")
    try:
        _upgrade_and_round_trip(pg, pool, owner)
    finally:
        upgrade(pg.url(OWNER))  # never leave the shared test cluster below head


def _upgrade_and_round_trip(pg: Any, pool: Any, owner: Any) -> None:
    ids = populate(pool)
    before = {t: owner.execute(f"SELECT count(*) FROM {t}").fetchone() for t in ("analysis", "publication", "job", "audit_event")}  # noqa: S608
    upgrade(pg.url(OWNER))
    assert owner.execute("SELECT version_num FROM alembic_version").fetchone() == ("0017",)
    after = {t: owner.execute(f"SELECT count(*) FROM {t}").fetchone() for t in before}  # noqa: S608
    assert after == before  # no row lost or added by any of the six revisions
    # 0014 adds nullable columns; 0016 marks only the provably model-free legacy row.
    assert owner.execute(
        "SELECT usage_source, cached_input_tokens FROM analysis WHERE id = %s", (ids["analysis"],)
    ).fetchone() == (
        "no_call",
        None,
    )
    assert documented() == live(owner)  # grants exactly as documented after an upgrade, not only after a clean install
    # A running job of the old schema is fenced by the new function at once: its owner tuple is checked.
    with transaction(pool) as c:
        j = queue.claim(c, "w1")
    assert j is not None
    with transaction(pool) as c:
        assert queue.Fence(j.id, 9, "w1", j.attempts).owned(c)
    for rev in reversed(NEW[:-1]):  # every revision downgrades and upgrades again
        downgrade(pg.url(OWNER), rev)
        upgrade(pg.url(OWNER))
        assert documented() == live(owner), rev


def test_the_worker_refuses_a_schema_that_is_not_its_head(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    require_schema_at(pool, head_revision())
    downgrade(pg.url(OWNER), "0016")
    try:
        with pytest.raises(SchemaMismatch, match="0016"):
            require_schema_at(pool, head_revision())  # worker.py and preflight: refuse to start (EXIT_CONFIG)
    finally:
        upgrade(pg.url(OWNER))


def test_every_security_definer_has_the_owner_a_fixed_path_and_exactly_its_runners(owner) -> None:  # type: ignore[no-untyped-def]
    rows = owner.execute(
        """SELECT p.proname, pg_get_userbyid(p.proowner), p.proconfig FROM pg_proc p
           WHERE p.pronamespace = 'public'::regnamespace AND p.prosecdef ORDER BY 1"""
    ).fetchall()
    assert [r[0] for r in rows] == sorted(DEFINERS)
    for name, own, cfg in rows:
        assert own == OWNER, name  # the non-superuser schema owner: no more than table-owner rights
        assert cfg == ["search_path=pg_catalog, public, pg_temp"], name  # pg_temp last: no shadowing
    roles = [r for (r,) in owner.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'tracewise%' OR rolname LIKE 'ops_%'")]
    for name, runners in DEFINERS.items():
        oid = owner.execute("SELECT oid FROM pg_proc WHERE proname = %s", (name,)).fetchone()[0]
        got = {
            r
            for r in roles
            if r != OWNER and owner.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (r, oid)).fetchone()[0]
        }
        members = {OPERATOR} if "tracewise_operator" in runners else set()  # members inherit the group's EXECUTE
        assert got == runners | members, name
        acl = owner.execute("SELECT proacl::text FROM pg_proc WHERE oid = %s", (oid,)).fetchone()[0] or ""
        assert not acl.startswith("{=") and ",=" not in acl, name  # PUBLIC has nothing
    # The policy helper is not a definer and only its owner may call or replace it.
    assert owner.execute(
        "SELECT prosecdef, has_function_privilege('tracewise_operator', oid, 'EXECUTE') FROM pg_proc"
        " WHERE proname = 'tracewise_requeue_max_reruns'"
    ).fetchone() == (False, False)


def test_definers_cannot_be_turned_into_escalation(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    ids = populate(pool)
    owner.execute("UPDATE job SET status = 'dead', attempts = 3, finished_at = now() WHERE id = %s", (ids["job"],))
    with psycopg.connect(pg.url(OPERATOR)) as c:
        # A temporary table named like a real one cannot redirect the definer (pg_temp is searched last).
        c.execute("CREATE TEMP TABLE job (id bigint, status text)")
        (r,) = c.execute("SELECT tracewise_requeue(%s, 'operator_request', true)", (ids["job"],)).fetchone()
        assert r["outcome"] == "would_requeue"
    with psycopg.connect(pg.url(OPERATOR)) as c:  # the operator group reaches no table and no other definer
        for sql in ("SELECT 1 FROM job", "SELECT 1 FROM audit_event", "SELECT tracewise_purge(1)",
                    "SELECT tracewise_job_owned(1, 9, 'w', 1, false)"):  # fmt: skip
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()
    with psycopg.connect(pg.url(APP)) as c:  # the tenant fence answers only for the transaction's own tenant
        c.execute("SELECT set_config('tracewise.installation_id', '10', false)")
        assert c.execute("SELECT tracewise_job_owned(%s, 9, 'w1', 1, false)", (ids["job"],)).fetchone() == (False,)
        for sql in ("SELECT tracewise_purge(1)", "SELECT tracewise_requeue(1, 'operator_request', true)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()
    with psycopg.connect(pg.url(SYSTEM)) as c:  # the system role cannot requeue or delete anything directly
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT tracewise_requeue(1, 'operator_request', true)")
        c.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM job")


def test_sequences_are_owned_by_the_schema_owner(owner) -> None:  # type: ignore[no-untyped-def]
    rows = owner.execute(
        "SELECT relname, pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'S'"
    ).fetchall()
    assert rows and all(o == OWNER for _, o in rows)
