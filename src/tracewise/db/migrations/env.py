"""Alembic environment: raw-SQL migrations, URL from the caller or DATABASE_URL_MIGRATIONS."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

from tracewise.db.urls import sqlalchemy_url

config = context.config
url = config.get_main_option("sqlalchemy.url") or sqlalchemy_url(os.environ["DATABASE_URL_MIGRATIONS"])


def run() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run()
