"""Alembic environment for the waitlist schema. Its version table lives in `waitlist`, so this chain is independent
of the product's migrations: it can run on a dedicated signup database or alongside the product schema."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool, text

from tracewise.db.urls import sqlalchemy_url

config = context.config
url = config.get_main_option("sqlalchemy.url") or sqlalchemy_url(os.environ["WAITLIST_DATABASE_URL_MIGRATIONS"])


def run() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        # The version table lives in the schema, so the schema must exist before Alembic looks for it.
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS waitlist"))
        conn.commit()
        context.configure(connection=conn, transaction_per_migration=True, version_table_schema="waitlist")
        with context.begin_transaction():
            context.run_migrations()


run()
