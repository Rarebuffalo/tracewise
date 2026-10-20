"""Connection pool and transactions for the waitlist role. The URL is a secret: never logged or put in errors.

Serverless-friendly: the pool starts empty, holds at most a few connections, health-checks them before use (an
instance may have been frozen), and disables server-side prepared statements (transaction-mode poolers such as
Neon's or PgBouncer's don't keep them across transactions).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from tracewise.db.urls import libpq_url

Conn = psycopg.Connection[DictRow]
_lock = threading.Lock()
_pools: dict[str, ConnectionPool[Conn]] = {}


class DatabaseUnavailable(Exception):
    """The database could not be reached; the caller answers 503 and the client may retry."""


def get_pool(url: str) -> ConnectionPool[Conn]:
    with _lock:
        p = _pools.get(url)
        if p is None:
            p = ConnectionPool(
                libpq_url(url),
                min_size=0,
                max_size=4,
                timeout=5.0,
                max_idle=60.0,
                check=ConnectionPool.check_connection,
                kwargs={"row_factory": dict_row, "autocommit": False, "connect_timeout": 5, "prepare_threshold": None},
                connection_class=psycopg.Connection[DictRow],
                open=True,
                name="waitlist",
            )
            _pools[url] = p
        return p


def close_pools() -> None:
    with _lock:
        for p in _pools.values():
            p.close()
        _pools.clear()


@contextmanager
def transaction(pool: ConnectionPool[Conn], statement_timeout_ms: int = 5000) -> Iterator[Conn]:
    """One connection, one transaction: commit on success, roll back on any exception."""
    try:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(int(statement_timeout_ms)),))
                yield conn
    except (psycopg.OperationalError, psycopg.errors.QueryCanceled) as e:
        raise DatabaseUnavailable(type(e).__name__) from None
    except Exception as e:
        if type(e).__name__ in ("PoolTimeout", "PoolClosed"):
            raise DatabaseUnavailable(type(e).__name__) from None
        raise
