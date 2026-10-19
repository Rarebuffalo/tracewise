"""Programmatic Alembic upgrade (no alembic.ini needed). Runs with the owner role only."""

from __future__ import annotations

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


def downgrade(owner_url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(owner_url), revision)


def head_revision() -> str:
    """The migration head this build expects (read from the bundled scripts; no database access)."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(alembic_config("postgresql://unused@/unused")).get_current_head()
    if head is None:
        raise RuntimeError("no migration head found")
    return head
