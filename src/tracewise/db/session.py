"""Connection pool for the runtime role. The URL is a secret: never logged or put in errors."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from tracewise.db.urls import libpq_url

Conn = psycopg.Connection[DictRow]


class DatabaseUnavailable(Exception):
    """The database could not be reached or failed mid-operation; the caller should retry later."""


def make_pool(url: str, *, min_size: int = 1, max_size: int = 10, timeout_s: float = 3.0) -> ConnectionPool[Conn]:
    return ConnectionPool(
        libpq_url(url),
        min_size=min_size,
        max_size=max_size,
        timeout=timeout_s,
        kwargs={"row_factory": dict_row, "autocommit": False, "connect_timeout": 3},
        connection_class=psycopg.Connection[DictRow],
        open=True,
        name="tracewise",
    )


@contextmanager
def transaction(pool: ConnectionPool[Conn], timeout_s: float | None = None, *, tenant: int | None = None) -> Iterator[Conn]:
    """One connection, one transaction: commit on success, roll back on any exception.

    `tenant` sets the transaction-local RLS context (`tracewise.installation_id`, T-705). It is cleared
    automatically at commit/rollback, so it can never leak to the next user of a pooled connection.
    Tenant-plane code must always pass it; without it the tenant role sees nothing (fail closed).
    Connection-level failures are raised as `DatabaseUnavailable` (no URL in the message).
    """
    if tenant is not None and (isinstance(tenant, bool) or not isinstance(tenant, int) or tenant <= 0):
        raise ValueError("tenant must be a positive installation id")
    try:
        with pool.connection(timeout=timeout_s) as conn, conn.transaction():
            if tenant is not None:
                conn.execute("SELECT set_config('tracewise.installation_id', %s, true)", (str(tenant),))
            yield conn
    except PoolTimeout as e:
        raise DatabaseUnavailable("database pool timeout") from e
    except psycopg.OperationalError as e:
        raise DatabaseUnavailable(f"database operational error ({type(e).__name__})") from e


class WrongDatabaseRole(RuntimeError):
    """A pool is connected as a role that does not belong to the plane it is used for (T-705)."""


def require_tenant_plane(pool: ConnectionPool[Conn]) -> None:
    """Fail closed if a tenant-plane pool could bypass row-level security.

    Guards against configuring `DATABASE_URL` with the system, owner or a superuser role: queries would still
    work, but RLS would silently not apply. Raises `WrongDatabaseRole` (role name only; never the URL).
    """
    with transaction(pool) as conn:
        row = conn.execute(
            """SELECT r.rolname, r.rolsuper, r.rolbypassrls,
                      EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
                              AND c.relkind = 'r' AND c.relowner = r.oid) AS owns_tables
               FROM pg_roles r WHERE r.rolname = current_user"""
        ).fetchone()
    if row is None or row["rolsuper"] or row["rolbypassrls"] or row["owns_tables"]:
        role = row["rolname"] if row else "unknown"
        raise WrongDatabaseRole(f"tenant-plane pool uses role {role!r}, which is not subject to row-level security")


def _role_facts(pool: ConnectionPool[Conn]) -> dict[str, object]:
    with transaction(pool) as conn:
        row = conn.execute(
            """SELECT r.rolname, r.rolsuper, r.rolbypassrls,
                      EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
                              AND c.relkind = 'r' AND c.relowner = r.oid) AS owns_tables
               FROM pg_roles r WHERE r.rolname = current_user"""
        ).fetchone()
    return dict(row) if row else {"rolname": "unknown", "rolsuper": True, "rolbypassrls": False, "owns_tables": True}


def require_system_plane(pool: ConnectionPool[Conn]) -> None:
    """Fail closed if the system-plane pool is not a non-superuser, non-owner BYPASSRLS role.

    With the tenant role here, row-level security would hide every job and delivery, and the worker would idle
    silently forever. With the owner or a superuser, the process would run with more rights than it needs."""
    f = _role_facts(pool)
    if f["rolsuper"] or f["owns_tables"] or not f["rolbypassrls"]:
        raise WrongDatabaseRole(f"system-plane pool uses role {f['rolname']!r}, which is not the BYPASSRLS system role")


def schema_revision(pool: ConnectionPool[Conn]) -> str | None:
    with transaction(pool) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row["version_num"]) if row else None


def require_schema_at(pool: ConnectionPool[Conn], revision: str) -> None:
    """The process never migrates; it refuses to run on a schema other than the one it was built for."""
    got = schema_revision(pool)
    if got != revision:
        raise SchemaMismatch(f"database schema is at {got!r}; this build needs {revision!r} (run migrations as the owner)")


class SchemaMismatch(RuntimeError):
    pass
