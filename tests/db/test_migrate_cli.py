"""T-1002: the migration CLI. Owner credentials only, refusals before any change, no URL in output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from pydantic import SecretStr

from tests.pg import APP, OWNER, SYSTEM, EphemeralPostgres
from tracewise.config import Settings
from tracewise.db import migrate

DB = "tw_migrate_cli"
MIG_OWNER = "tw_mig_owner"  # a non-superuser owner, as scripts/db/provision_roles.sql creates (tests/pg's owner is a superuser)


def st(**urls: str | None) -> Settings:
    return Settings(_env_file=None, **{k: SecretStr(v) if v else None for k, v in urls.items()})


def run(capsys: pytest.CaptureFixture[str], action: str, s: Settings) -> tuple[int, dict[str, Any]]:
    code = migrate.main([action], settings=s)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


@pytest.fixture
def empty_db(pg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> Any:
    owner.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
    if not owner.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (MIG_OWNER,)).fetchone():
        owner.execute(f"CREATE ROLE {MIG_OWNER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
    owner.execute(f"CREATE DATABASE {DB} OWNER {MIG_OWNER}")
    yield pg.url(MIG_OWNER, db=DB)
    owner.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")


def test_fresh_database_status_upgrade_and_idempotent_rerun(empty_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    s = st(database_url_migrations=empty_db)
    assert run(capsys, "status", s) == (4, {"current": None, "head": migrate.head_revision(), "at_head": False})
    code, out = run(capsys, "upgrade", s)
    assert code == 0 and out == {"before": None, "after": migrate.head_revision(), "head": migrate.head_revision()}
    assert run(capsys, "upgrade", s)[0] == 0  # re-running at head is a no-op
    assert run(capsys, "status", s)[0] == 0


def test_status_reports_a_database_behind_head(pg: EphemeralPostgres, owner: Any, capsys: pytest.CaptureFixture[str]) -> None:
    (rev,) = owner.execute("SELECT version_num FROM alembic_version").fetchone()
    owner.execute("UPDATE alembic_version SET version_num = '0010'")
    try:
        code = migrate.main(["status", "--allow-superuser"], settings=st(database_url_migrations=pg.url(OWNER)))
        out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert code == 4 and out["current"] == "0010" and not out["at_head"]
    finally:
        owner.execute("UPDATE alembic_version SET version_num = %s", (rev,))


@pytest.mark.parametrize(
    ("urls", "why"),
    [
        ({}, "DATABASE_URL_MIGRATIONS is not set"),
        ({"database_url_migrations": "SYS", "database_url_system": "SYS"}, "same role as DATABASE_URL_SYSTEM"),
        ({"database_url_migrations": "APP"}, "runtime role"),
    ],
)
def test_refusals_happen_before_any_change_and_name_no_url(
    pg: EphemeralPostgres, owner: Any, capsys: pytest.CaptureFixture[str], urls: dict[str, str], why: str
) -> None:
    resolved = {k: pg.url(SYSTEM) if v == "SYS" else pg.url(APP) for k, v in urls.items()}
    code = migrate.main(["upgrade"], settings=st(**resolved))
    out = capsys.readouterr().out
    assert code == 2 and why in out and "postgresql://" not in out


def test_a_runtime_role_named_only_in_the_query_string_is_caught_by_the_connection_check(
    pg: EphemeralPostgres, owner: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    hidden = pg.url(SYSTEM).replace(f"postgresql://{SYSTEM}@/", "postgresql:///", 1) + f"&user={SYSTEM}"
    assert migrate._user(hidden) is None  # the name check cannot see this role
    code = migrate.main(["upgrade"], settings=st(database_url_migrations=hidden))
    assert code == 2 and "connects as a runtime role" in capsys.readouterr().out


def test_unreachable_database_exit_1_without_the_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    url = f"postgresql://tracewise_owner:pw-hidden@/tracewise?host={tmp_path}"
    assert migrate.main(["upgrade"], settings=st(database_url_migrations=url)) == 1
    out = capsys.readouterr().out
    assert "pw-hidden" not in out and str(tmp_path) not in out


def test_a_superuser_owner_url_is_refused_unless_explicitly_allowed(
    pg: EphemeralPostgres, owner: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    s = st(database_url_migrations=pg.url(OWNER))  # tests/pg's owner is a superuser
    assert migrate.main(["upgrade"], settings=s) == 2 and "superuser" in capsys.readouterr().out
    assert migrate.main(["status", "--allow-superuser"], settings=s) == 0


def test_a_role_that_does_not_own_the_existing_schema_is_refused(
    pg: EphemeralPostgres, owner: Any, empty_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # The session database's schema is owned by tests/pg's owner; the non-superuser owner of another database
    # must not migrate it (mixed ownership).
    owner.execute(f"GRANT CONNECT ON DATABASE tracewise TO {MIG_OWNER}")
    code = migrate.main(["upgrade"], settings=st(database_url_migrations=pg.url(MIG_OWNER)))
    assert code == 2 and "does not own the existing schema" in capsys.readouterr().out


def test_the_non_superuser_owner_produces_a_definer_the_preflight_accepts(
    pg: EphemeralPostgres, empty_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from tracewise import preflight

    assert migrate.main(["upgrade"], settings=st(database_url_migrations=empty_db)) == 0
    sys_url = pg.url(SYSTEM, db=DB)
    checks = {
        c.name: c.result
        for c in preflight.database_checks(Settings(_env_file=None, database_url_system=SecretStr(sys_url)), "web")
    }
    assert checks == {"schema_revision": "pass", "definer_owner": "pass", "system_role": "pass"}
