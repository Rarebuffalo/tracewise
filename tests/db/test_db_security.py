"""Security audit 2026-10-19: database boundary guards that future migrations and configuration must keep.

These are structural checks on a freshly migrated disposable database, plus the fail-closed role check.
They do not show that RLS stops arbitrary SQL running as `tracewise_app` (it does not; ARCHITECTURE §4.7).
"""

from __future__ import annotations

import psycopg
import pytest

from tests.pg import APP, OWNER, SYSTEM
from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import WrongDatabaseRole, make_pool, require_tenant_plane

# Reviewed system-plane tables. redelivery_request has an installation_id but holds GitHub delivery
# metadata for the recovery pass only, and the tenant role has no access to it (0005).
SYSTEM_ONLY = {"alembic_version", "recovery_checkpoint", "redelivery_request"}


def _tables(owner) -> dict[str, tuple[bool, bool]]:  # type: ignore[no-untyped-def]
    rows = owner.execute(
        """SELECT c.relname,
                  EXISTS (SELECT 1 FROM information_schema.columns k WHERE k.table_schema = 'public'
                          AND k.table_name = c.relname AND k.column_name = 'installation_id') OR c.relname = 'installation',
                  c.relrowsecurity
           FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p')"""
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def test_every_tenant_table_has_rls_and_the_policy_and_every_other_table_is_declared(owner) -> None:  # type: ignore[no-untyped-def]
    tables = _tables(owner)
    policies = {r[0] for r in owner.execute("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")}
    tenant = {t for t, (has_inst, _) in tables.items() if has_inst} - SYSTEM_ONLY
    assert tenant, "no tenant tables found"
    for t in tenant:
        assert tables[t][1], f"{t} carries an installation but has no row-level security"
        assert t in policies, f"{t} has no tenant_isolation policy"
    undeclared = set(tables) - tenant - SYSTEM_ONLY
    assert not undeclared, f"new non-tenant tables must be declared system-only and reviewed: {undeclared}"


def test_runtime_roles_cannot_write_migration_state_or_create_objects(owner) -> None:  # type: ignore[no-untyped-def]
    for role in (APP, SYSTEM):
        for priv in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert owner.execute("SELECT has_table_privilege(%s, 'alembic_version', %s)", (role, priv)).fetchone() == (False,), (
                role,
                priv,
            )
        assert owner.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (role,)).fetchone() == (False,)
    with psycopg.connect(owner.info.dsn.replace(f"user={OWNER}", f"user={APP}")) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE alembic_version SET version_num = '0004'")


def test_tenant_role_has_no_access_to_system_only_tables_and_the_system_role_reads_all(owner) -> None:  # type: ignore[no-untyped-def]
    for t in SYSTEM_ONLY - {"alembic_version"}:
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert owner.execute("SELECT has_table_privilege(%s, %s, %s)", (APP, t, priv)).fetchone() == (False,), (t, priv)
    for t in _tables(owner):
        assert owner.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (SYSTEM, t)).fetchone() == (True,), t
    assert owner.execute("SELECT prosecdef FROM pg_proc WHERE proname = 'tracewise_tenant'").fetchone() == (False,)


def test_migration_0006_roundtrip(pg, owner) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER), "0005")
    assert owner.execute("SELECT has_table_privilege(%s, 'alembic_version', 'UPDATE')", (APP,)).fetchone() == (True,)
    upgrade(pg.url(OWNER))
    assert owner.execute("SELECT has_table_privilege(%s, 'alembic_version', 'UPDATE')", (APP,)).fetchone() == (False,)


@pytest.mark.parametrize("role", [SYSTEM, OWNER])
def test_tenant_plane_refuses_a_pool_that_bypasses_rls(pg, owner, role) -> None:  # type: ignore[no-untyped-def]
    p = make_pool(pg.url(role))
    try:
        with pytest.raises(WrongDatabaseRole) as e:
            require_tenant_plane(p)
        assert role in str(e.value) and "host=" not in str(e.value) and str(pg.sock) not in str(e.value)
    finally:
        p.close()


def test_tenant_plane_accepts_the_tenant_role(tenant_pool) -> None:  # type: ignore[no-untyped-def]
    require_tenant_plane(tenant_pool)


def test_analyze_handler_cannot_be_built_on_the_system_pool(pool) -> None:  # type: ignore[no-untyped-def]
    from tracewise.jobs.handlers.analyze import AnalyzeDeps, make_analyze_handler

    deps = AnalyzeDeps(pool, None, None, 1, provider_factory=lambda: None, fetcher_factory=lambda: None)  # type: ignore[arg-type]
    with pytest.raises(WrongDatabaseRole):
        make_analyze_handler(deps)
