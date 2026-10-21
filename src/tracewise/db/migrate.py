"""Programmatic Alembic upgrade (no alembic.ini needed). Runs with the owner role only.

    python -m tracewise.db.migrate {status|upgrade}

Reads only `DATABASE_URL_MIGRATIONS` (the owner). Refuses (exit 2), before any change, when that URL is missing, is
the same URL or user as a runtime URL that is also set, connects as a runtime role (`tracewise_app`,
`tracewise_system`), connects as a superuser (the SECURITY DEFINER purge function would then run with superuser
rights; `--allow-superuser` exists for disposable development clusters only), or connects as a role other than the
one that owns an existing schema (mixed ownership). `status` prints the current and head revisions (exit 0 at head,
4 behind); `upgrade` migrates to this build's head (exit 0). An unreachable database or a failed migration gives
exit 1. Output names revisions, never a URL.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config

from tracewise.db.urls import sqlalchemy_url

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config(owner_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(owner_url).replace("%", "%%"))
    return cfg


def upgrade(owner_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(owner_url), revision)


def downgrade(owner_url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(owner_url), revision)


def head_revision() -> str:
    """The migration head this build expects (read from the bundled scripts; no database access)."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(alembic_config("postgresql://unused@/unused")).get_current_head()
    if head is None:
        raise RuntimeError("no migration head found")
    return head


RUNTIME_ROLES = frozenset({"tracewise_app", "tracewise_system"})


class MigrationRefused(Exception):
    """Configuration refused before any database change; the message names settings, never values."""


def _user(url: str | None) -> str | None:
    try:
        return urlsplit(url).username if url else None
    except ValueError:
        return None


def owner_url_from(settings: object) -> str:
    def val(name: str) -> str | None:
        v = getattr(settings, name, None)
        return v.get_secret_value() if v is not None else None

    owner = val("database_url_migrations")
    if not owner:
        raise MigrationRefused("DATABASE_URL_MIGRATIONS is not set")
    for name in ("database_url", "database_url_system"):
        other = val(name)
        if other and (other == owner or (_user(owner) is not None and _user(owner) == _user(other))):
            raise MigrationRefused(f"DATABASE_URL_MIGRATIONS uses the same role as {name.upper()}")
    if _user(owner) in RUNTIME_ROLES:
        raise MigrationRefused("DATABASE_URL_MIGRATIONS names a runtime role")
    return owner


@dataclass(frozen=True)
class DbFacts:
    revision: str | None
    role: str
    superuser: bool
    schema_owner: str | None  # owner of alembic_version, when the schema exists


def database_facts(owner_url: str) -> DbFacts:
    """Read-only facts about the migration target."""
    import psycopg

    from tracewise.db.urls import libpq_url

    with psycopg.connect(libpq_url(owner_url), connect_timeout=5) as conn:
        role, superuser = conn.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user").fetchone() or (
            "",
            False,
        )
        owner = conn.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('public.alembic_version')"
        ).fetchone()
        # Read the revision only as the schema's owner: another role may lack SELECT, and is refused anyway.
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone() if owner and owner[0] == role else None
    return DbFacts(str(rev[0]) if rev else None, str(role), bool(superuser), str(owner[0]) if owner else None)


def current_revision(owner_url: str) -> tuple[str | None, str]:
    """(revision in the database or None, the connected role). Read-only."""
    f = database_facts(owner_url)
    return f.revision, f.role


def main(argv: list[str] | None = None, settings: object = None) -> int:
    import argparse

    import psycopg

    ap = argparse.ArgumentParser(prog="python -m tracewise.db.migrate")
    ap.add_argument("action", choices=["status", "upgrade"])
    ap.add_argument("--allow-superuser", action="store_true", help="disposable development clusters only")
    a = ap.parse_args(argv)
    try:
        if settings is None:
            from tracewise.config import Settings

            settings = Settings()
        owner = owner_url_from(settings)
        facts = database_facts(owner)
        current = facts.revision
        if facts.role in RUNTIME_ROLES:
            raise MigrationRefused("DATABASE_URL_MIGRATIONS connects as a runtime role")
        if facts.superuser and not a.allow_superuser:
            raise MigrationRefused("DATABASE_URL_MIGRATIONS connects as a superuser; use the non-superuser owner role")
        if facts.schema_owner is not None and facts.schema_owner != facts.role:
            raise MigrationRefused("DATABASE_URL_MIGRATIONS connects as a role that does not own the existing schema")
    except MigrationRefused as e:
        print(json.dumps({"error": "refused", "detail": str(e)}))
        return 2
    except psycopg.OperationalError:
        print(json.dumps({"error": "database_unavailable"}))
        return 1
    except Exception as e:
        from tracewise.config import invalid_fields

        print(json.dumps({"error": "refused", "detail": f"invalid configuration ({invalid_fields(e)})"}))
        return 2
    head = head_revision()
    if a.action == "status":
        print(json.dumps({"current": current, "head": head, "at_head": current == head}))
        return 0 if current == head else 4
    try:
        upgrade(owner)
        after, _ = current_revision(owner)
    except psycopg.OperationalError:
        print(json.dumps({"error": "database_unavailable", "before": current}))
        return 1
    except Exception as e:
        print(json.dumps({"error": "migration_failed", "type": type(e).__name__, "before": current}))
        return 1
    print(json.dumps({"before": current, "after": after, "head": head}))
    return 0 if after == head else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
