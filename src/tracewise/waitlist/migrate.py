"""Waitlist migrations, run by the owner role only: `python -m tracewise.waitlist.migrate [upgrade|current]`.

Never run by the web process. Uses WAITLIST_DATABASE_URL_MIGRATIONS; the URL is a secret and is never printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def main(argv: list[str] | None = None) -> int:
    from tracewise.waitlist.settings import WaitlistSettings

    args = sys.argv[1:] if argv is None else argv
    action = args[0] if args else "upgrade"
    s = WaitlistSettings()
    if s.waitlist_database_url_migrations is None:
        print("WAITLIST_DATABASE_URL_MIGRATIONS is not set", file=sys.stderr)
        return 2
    cfg = alembic_config(s.waitlist_database_url_migrations.get_secret_value())
    if action == "upgrade":
        command.upgrade(cfg, "head")
    elif action == "current":
        command.current(cfg)
    else:
        print("usage: python -m tracewise.waitlist.migrate [upgrade|current]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
