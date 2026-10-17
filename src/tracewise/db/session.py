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
def transaction(pool: ConnectionPool[Conn], timeout_s: float | None = None) -> Iterator[Conn]:
    """One connection, one transaction: commit on success, roll back on any exception.

    Connection-level failures are raised as `DatabaseUnavailable` (no URL in the message).
    """
    try:
        with pool.connection(timeout=timeout_s) as conn, conn.transaction():
            yield conn
    except PoolTimeout as e:
        raise DatabaseUnavailable("database pool timeout") from e
    except psycopg.OperationalError as e:
        raise DatabaseUnavailable(f"database operational error ({type(e).__name__})") from e
