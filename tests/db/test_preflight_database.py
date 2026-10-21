"""T-801/T-802 preflight `--database`: read-only role and schema checks against the disposable cluster."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg

from tests.pg import APP, OWNER, SYSTEM, EphemeralPostgres
from tracewise import preflight
from tracewise.config import Settings


def st(pg: EphemeralPostgres, **over: Any) -> Settings:
    base: dict[str, Any] = {"tw_env": "test", "database_url": pg.url(APP), "database_url_system": pg.url(SYSTEM)}
    base.update(over)
    return Settings(_env_file=None, **base)


def results(s: Settings) -> dict[str, str]:
    return {c.name: c.result for c in preflight.database_checks(s, "all")}


def test_correct_roles_at_head_pass(pg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> None:
    r = results(st(pg))
    assert {k: r[k] for k in ("schema_revision", "system_role", "tenant_role")} == dict.fromkeys(
        ("schema_revision", "system_role", "tenant_role"), "pass"
    )
    # tests/pg migrates the session database as a superuser, which the preflight must flag (staging never does:
    # the migration CLI refuses a superuser; tests/db/test_migrate_cli.py shows the non-superuser case passing).
    assert r["definer_owner"] == "fail"


def test_swapped_or_owner_roles_fail(pg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> None:
    swapped = results(st(pg, database_url=pg.url(SYSTEM), database_url_system=pg.url(APP)))
    assert swapped["system_role"] == "fail" and swapped["tenant_role"] == "fail"
    assert results(st(pg, database_url=pg.url(OWNER)))["tenant_role"] == "fail"


def test_unreachable_database_fails_without_echoing_the_url(tmp_path: Path) -> None:
    url = f"postgresql://tracewise_system:pw-hidden@/tracewise?host={tmp_path}"
    out = preflight.database_checks(Settings(_env_file=None, database_url_system=url), "web")
    assert [(c.name, c.result) for c in out] == [("system_role", "fail")]
    assert all("pw-hidden" not in c.detail and str(tmp_path) not in c.detail for c in out)


def test_schema_behind_head_fails(pg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> None:
    (rev,) = owner.execute("SELECT version_num FROM alembic_version").fetchone() or ("",)
    owner.execute("UPDATE alembic_version SET version_num = '0010'")
    try:
        assert results(st(pg))["schema_revision"] == "fail"
    finally:
        owner.execute("UPDATE alembic_version SET version_num = %s", (rev,))
