"""Phase 12: fresh-install lifecycle on a brand-new disposable cluster, bootstrapped ONLY by the reviewed
template `scripts/db/provision_roles.sql` (non-superuser owner, no passwords), then every migration in order.

Unlike the session cluster (whose migration owner is the initdb superuser), this proves a clean install with the
documented role model: schema, constraints, indexes, grants, RLS, the definer function's owner, the full
downgrade/upgrade cycle (catalog snapshot identical), and fail-closed behaviour for missing roles and wrong URLs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
import pytest

from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import WrongDatabaseRole, make_pool, require_tenant_plane, transaction

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "db" / "provision_roles.sql"
ADMIN = "tw_admin"
TENANT_TABLES = {
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
}

if shutil.which("initdb") is None:  # pragma: no cover
    pytest.skip("PostgreSQL server binaries not installed", allow_module_level=True)


class Cluster:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="twpg-fresh-"))
        self.root.chmod(0o700)
        self.sock = self.root / "s"
        self.sock.mkdir(mode=0o700)
        env = {**os.environ, "LC_ALL": "C"}
        subprocess.run(  # noqa: S603
            [
                shutil.which("initdb") or "initdb",
                "-D",
                str(self.root / "data"),
                "-U",
                ADMIN,
                "--auth=trust",
                "-E",
                "UTF8",
                "--no-locale",
                "--no-sync",
            ],
            check=True,
            capture_output=True,
            env=env,
        )
        opts = f"-k {self.sock} -c listen_addresses='' -p 5433 -c fsync=off"
        subprocess.run(  # noqa: S603
            [
                shutil.which("pg_ctl") or "pg_ctl",
                "-D",
                str(self.root / "data"),
                "-o",
                opts,
                "-l",
                str(self.root / "log"),
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
            env=env,
        )

    def url(self, user: str, db: str = "tracewise") -> str:
        return f"postgresql://{user}@/{db}?host={quote(str(self.sock), safe='')}&port=5433"

    def run_script(self, text: str) -> None:
        """Minimal psql-compatible runner: `;`-separated statements, `\\connect db`, `--` comments."""
        stmts: list[tuple[str, str]] = []
        db, buf = "postgres", []
        for raw in text.split("\n"):
            line = raw.split("--", 1)[0].strip()
            if line.startswith("\\connect"):
                db = line.split()[1]
                continue
            if line:
                buf.append(line)
            if line.endswith(";"):
                stmts.append((db, " ".join(buf)))
                buf = []
        assert not buf, "unterminated statement in the template"
        for d, sql in stmts:
            with psycopg.connect(self.url(ADMIN, d), autocommit=True) as c:
                c.execute(sql.encode())

    def stop(self) -> None:
        subprocess.run(  # noqa: S603
            [shutil.which("pg_ctl") or "pg_ctl", "-D", str(self.root / "data"), "-m", "immediate", "-w", "stop"],
            check=False,
            capture_output=True,
        )
        shutil.rmtree(self.root, ignore_errors=True)


@pytest.fixture(scope="module")
def fresh() -> Iterator[Cluster]:
    c = Cluster()
    try:
        c.run_script(SCRIPT.read_text())
        upgrade(c.url("tracewise_owner"))
        yield c
    finally:
        c.stop()


def snapshot(c: Cluster) -> dict[str, Any]:
    with psycopg.connect(c.url(ADMIN)) as k:
        q = lambda sql: sorted(tuple(map(str, r)) for r in k.execute(sql))  # noqa: E731
        return {
            "columns": q("""SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns
                            WHERE table_schema = 'public'"""),
            "constraints": q("""SELECT conrelid::regclass, conname, pg_get_constraintdef(oid) FROM pg_constraint
                                WHERE connamespace = 'public'::regnamespace"""),
            "indexes": q("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"),
            "policies": q("SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies"),
            "rls": q(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                " WHERE relnamespace='public'::regnamespace AND relkind='r'"
            ),
            "grants": q("""SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
                           WHERE grantee IN ('tracewise_app', 'tracewise_system')"""),
            "functions": q("""SELECT proname, prosecdef, proconfig, pg_get_userbyid(proowner), proacl FROM pg_proc
                              WHERE pronamespace = 'public'::regnamespace"""),
            "triggers": q("SELECT tgrelid::regclass, tgname FROM pg_trigger WHERE NOT tgisinternal"),
        }


def test_template_creates_the_documented_role_attributes(fresh) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(fresh.url(ADMIN)) as k:
        rows = k.execute("""SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolpassword IS NOT NULL
                            FROM pg_authid WHERE rolname LIKE 'tracewise_%' ORDER BY 1""").fetchall()
        assert rows == [
            ("tracewise_app", False, False, False, False, False),
            ("tracewise_owner", False, False, False, False, False),
            ("tracewise_system", False, True, False, False, False),
        ]  # no passwords in the template
        assert k.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='tracewise'").fetchone() == (
            "tracewise_owner",
        )
        assert k.execute("SELECT has_database_privilege('tracewise_system', 'tracewise', 'TEMP')").fetchone() == (False,)


def test_schema_grants_rls_and_definer_owner_after_a_clean_install(fresh) -> None:  # type: ignore[no-untyped-def]
    s = snapshot(fresh)
    tables = {r[0] for r in s["rls"]}
    assert tables == TENANT_TABLES | {"alembic_version", "recovery_checkpoint", "redelivery_request"}
    assert {r[0] for r in s["rls"] if r[1] == "True"} == TENANT_TABLES
    assert {r[0] for r in s["policies"]} == TENANT_TABLES and {r[1] for r in s["policies"]} == {"tenant_isolation"}
    grants = {(g, t, p) for g, t, p in s["grants"]}
    assert ("tracewise_app", "recovery_checkpoint", "SELECT") not in grants
    assert ("tracewise_app", "analysis", "DELETE") not in grants and ("tracewise_system", "analysis", "DELETE") not in grants
    assert not any(t == "alembic_version" and p in ("INSERT", "UPDATE", "DELETE", "TRUNCATE") for _, t, p in grants)
    assert not any(t == "audit_event" and p in ("UPDATE", "DELETE") for _, t, p in grants)
    (purge,) = [f for f in s["functions"] if f[0] == "tracewise_purge"]
    assert purge[1] == "True" and "pg_temp" in purge[2] and purge[3] == "tracewise_owner"  # non-superuser owner
    with psycopg.connect(fresh.url(ADMIN)) as k:
        for role, allowed in (("public", False), ("tracewise_app", False), ("tracewise_owner", True), ("tracewise_system", True)):
            got = k.execute("SELECT has_function_privilege(%s, 'tracewise_purge(integer)', 'EXECUTE')", (role,)).fetchone()
            assert got == (allowed,), role
    with psycopg.connect(fresh.url("tracewise_owner")) as k:
        assert k.execute("SELECT version_num FROM alembic_version").fetchone() == ("0011",)
        assert k.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexname IN ('job_ready', 'analysis_updated', 'installation_purge_due')"
        ).fetchone() == (3,)


def test_runtime_paths_work_on_the_clean_install(fresh) -> None:  # type: ignore[no-untyped-def]
    from tracewise import retention
    from tracewise.db import repositories as repo

    sysp, tenp = make_pool(fresh.url("tracewise_system")), make_pool(fresh.url("tracewise_app"))
    try:
        require_tenant_plane(tenp)
        with pytest.raises(WrongDatabaseRole):
            require_tenant_plane(sysp)
        with transaction(sysp) as c:
            repo.set_installation_status(c, 1, "active", "a")
            repo.repository_added(c, 11, 1, "a/r")
        with transaction(tenp, tenant=1) as c:
            assert repo.repository_scope(c, 11)["installation_id"] == 1
        with transaction(tenp, tenant=2) as c:
            assert repo.repository_scope(c, 11) is None
        assert retention.purge(sysp).completed
        with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(sysp) as c:
            c.execute("CREATE TEMP TABLE x (i int)")  # template hardening: no TEMP for runtime roles
        with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenp, tenant=1) as c:
            c.execute("UPDATE alembic_version SET version_num = '0001'")
    finally:
        sysp.close()
        tenp.close()


def test_full_downgrade_and_upgrade_reproduce_the_same_catalog(fresh) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(fresh.url("tracewise_owner"), autocommit=True) as k:
        k.execute("TRUNCATE installation, repository CASCADE")
    before = snapshot(fresh)
    downgrade(fresh.url("tracewise_owner"), "base")
    with psycopg.connect(fresh.url(ADMIN)) as k:
        left = k.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r'").fetchall()
        assert left == [("alembic_version",)]
    upgrade(fresh.url("tracewise_owner"))
    assert snapshot(fresh) == before


def test_missing_runtime_roles_at_migration_time_fail_closed() -> None:
    """Roles created AFTER the migrations get no privileges: runtime access is denied, never silently open."""
    c = Cluster()
    try:
        c.run_script("CREATE ROLE tracewise_owner LOGIN NOSUPERUSER;\nCREATE DATABASE tracewise OWNER tracewise_owner;\n")
        upgrade(c.url("tracewise_owner"))
        c.run_script("CREATE ROLE tracewise_app LOGIN NOBYPASSRLS;\nCREATE ROLE tracewise_system LOGIN BYPASSRLS;\n")
        for role in ("tracewise_app", "tracewise_system"):
            with psycopg.connect(c.url(role)) as k, pytest.raises(psycopg.errors.InsufficientPrivilege):
                k.execute("SELECT * FROM job")
        with psycopg.connect(c.url("tracewise_system")) as k, pytest.raises(psycopg.errors.InsufficientPrivilege):
            k.execute("SELECT tracewise_purge(1)")
    finally:
        c.stop()


def test_schema_guard_fails_on_an_unprotected_tenant_table(fresh) -> None:  # type: ignore[no-untyped-def]
    from tests.db.test_db_security import (
        test_every_tenant_table_has_rls_and_the_policy_and_every_other_table_is_declared as guard,
    )

    with psycopg.connect(fresh.url("tracewise_owner"), autocommit=True) as k:
        guard(k)
        k.execute("CREATE TABLE new_feature (id int, installation_id bigint)")
        try:
            with pytest.raises(AssertionError, match="new_feature"):
                guard(k)
        finally:
            k.execute("DROP TABLE new_feature")


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "postgresql://tracewise_app:supersecretpw@/tracewise?host=/nonexistent-dir&port=5433",
        "postgresql://nosuchrole@/tracewise?host={sock}&port=5433",
    ],
    ids=["malformed", "password-in-unreachable-url", "unknown-role"],  # never print the URL in test ids
)
def test_bad_urls_fail_safely_without_leaking_credentials(fresh, url) -> None:  # type: ignore[no-untyped-def]
    from tracewise.db.session import DatabaseUnavailable

    url = url.format(sock=quote(str(fresh.sock), safe=""))
    with pytest.raises((DatabaseUnavailable, ValueError, psycopg.Error)) as e:
        p = make_pool(url, timeout_s=1.0)
        try:
            require_tenant_plane(p)
        finally:
            p.close()
    assert "supersecretpw" not in str(e.value) and "supersecretpw" not in repr(e.value.__cause__ or "")
