"""I-7: every runtime pool connection carries a statement and a lock timeout, and hitting either ends in
`DatabaseUnavailable` (retryable), never an indefinite wait."""

from __future__ import annotations

import psycopg
import pytest

from tests.pg import APP, OWNER, SYSTEM, EphemeralPostgres
from tracewise.db.session import LOCK_TIMEOUT_MS, STATEMENT_TIMEOUT_MS, DatabaseUnavailable, make_pool, transaction


@pytest.mark.parametrize("role", [SYSTEM, APP])
def test_both_planes_get_the_session_timeouts(pg: EphemeralPostgres, owner, role) -> None:  # type: ignore[no-untyped-def]
    p = make_pool(pg.url(role), min_size=1, max_size=2)
    try:
        with transaction(p) as conn:
            row = conn.execute(
                "SELECT current_setting('statement_timeout') AS s, current_setting('lock_timeout') AS l"
            ).fetchone()
        assert row == {"s": f"{STATEMENT_TIMEOUT_MS // 1000}s", "l": f"{LOCK_TIMEOUT_MS // 1000}s"}
    finally:
        p.close()


def test_a_wait_on_a_held_row_lock_ends_as_database_unavailable(pg: EphemeralPostgres, owner) -> None:  # type: ignore[no-untyped-def]
    owner.execute("INSERT INTO installation (id, account_login, status) VALUES (1, 'a', 'active')")
    p = make_pool(pg.url(SYSTEM), min_size=1, max_size=2, statement_timeout_ms=5000, lock_timeout_ms=200)
    try:
        with psycopg.connect(pg.url(OWNER)) as holder:
            holder.execute("SELECT 1 FROM installation WHERE id = 1 FOR UPDATE")  # held until rollback
            with pytest.raises(DatabaseUnavailable), transaction(p) as conn:
                conn.execute("SELECT 1 FROM installation WHERE id = 1 FOR UPDATE")
            holder.rollback()
        with transaction(p) as conn:  # the pooled connection is usable again afterwards
            assert conn.execute("SELECT 1 AS one").fetchone() == {"one": 1}
    finally:
        p.close()


def test_a_long_statement_ends_as_database_unavailable(pg: EphemeralPostgres, owner) -> None:  # type: ignore[no-untyped-def]
    p = make_pool(pg.url(SYSTEM), min_size=1, max_size=1, statement_timeout_ms=200, lock_timeout_ms=100)
    try:
        with pytest.raises(DatabaseUnavailable), transaction(p) as conn:
            conn.execute("SELECT pg_sleep(5)")
    finally:
        p.close()


@pytest.mark.parametrize(("stmt", "lock"), [(0, 0), (1000, 2000), (600_001, 1000)])
def test_timeouts_are_validated(stmt: int, lock: int) -> None:
    with pytest.raises(ValueError, match="database timeouts"):
        make_pool("postgresql://unused.invalid/x", statement_timeout_ms=stmt, lock_timeout_ms=lock)
