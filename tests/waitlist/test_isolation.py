"""The waitlist runtime role can reach its five tables and nothing else; product roles cannot reach the waitlist."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from tests.pg import APP, OWNER, SYSTEM, EphemeralPostgres
from tests.waitlist.conftest import ROLE
from tracewise.waitlist.migrate import upgrade as waitlist_upgrade


def test_waitlist_role_cannot_read_product_tables(wpg: EphemeralPostgres) -> None:
    with psycopg.connect(wpg.url(OWNER)) as c:
        product_tables = [
            (r[0], r[1])
            for r in c.execute(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname NOT IN ('waitlist', 'pg_catalog', 'information_schema')"
            )
        ]
    assert product_tables, "the product schema should be present in this cluster"
    with psycopg.connect(wpg.url(ROLE), autocommit=True) as c:
        for schema, table in product_tables:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(sql.Identifier(schema, table)))


def test_waitlist_role_cannot_create_or_alter(wpg: EphemeralPostgres) -> None:
    with psycopg.connect(wpg.url(ROLE), autocommit=True) as c:
        for stmt in (
            "CREATE TABLE public.x (a int)",
            "CREATE TABLE waitlist.x (a int)",
            "ALTER TABLE waitlist.signup ADD COLUMN x int",
            "DROP TABLE waitlist.rate_limit",
            "TRUNCATE waitlist.signup",
            "CREATE SCHEMA evil",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(stmt.encode())
        row = c.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert row == (False, False, False, False)


@pytest.mark.parametrize("role", [APP, SYSTEM])
def test_product_roles_cannot_read_waitlist(wpg: EphemeralPostgres, role: str) -> None:
    with psycopg.connect(wpg.url(role), autocommit=True) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT email FROM waitlist.signup")


def test_waitlist_versions_kept_apart_from_product(wpg: EphemeralPostgres) -> None:
    with psycopg.connect(wpg.url(OWNER)) as c:
        assert c.execute("SELECT version_num FROM waitlist.alembic_version").fetchall() == [("w0001",)]
        product = c.execute("SELECT version_num FROM public.alembic_version").fetchall()
        assert product and product != [("w0001",)]


def test_waitlist_migration_is_idempotent(wpg: EphemeralPostgres) -> None:
    waitlist_upgrade(wpg.url(OWNER))  # already at head: a no-op, nothing dropped
    with psycopg.connect(wpg.url(OWNER)) as c:
        assert c.execute("SELECT version_num FROM waitlist.alembic_version").fetchall() == [("w0001",)]


def test_waitlist_on_its_own_database(tmp_path: object) -> None:
    """A dedicated signup database gets only the waitlist schema (no product tables)."""
    from tests.pg import ephemeral

    cluster = ephemeral()
    try:
        waitlist_upgrade(cluster.url(OWNER))
        with psycopg.connect(cluster.url(OWNER)) as c:
            schemas = {
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT schemaname FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
                )
            }
            assert schemas == {"waitlist"}
    finally:
        cluster.stop()
