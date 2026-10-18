"""DB fixtures: one disposable cluster per session; tables truncated between tests."""

from __future__ import annotations

import shutil
from collections.abc import Iterator

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from tests.pg import OWNER, EphemeralPostgres, ephemeral
from tracewise.db.migrate import upgrade
from tracewise.db.session import Conn, make_pool

TABLES = (
    "audit_event, usage_event, failure_signature, publication, analysis, job, workflow_run, "
    "webhook_delivery, repository, installation, recovery_checkpoint, redelivery_request"
)

if shutil.which("initdb") is None:  # pragma: no cover
    pytest.skip("PostgreSQL server binaries not installed", allow_module_level=True)


@pytest.fixture(scope="session")
def pg() -> Iterator[EphemeralPostgres]:
    cluster = ephemeral()
    try:
        upgrade(cluster.url(OWNER))
        yield cluster
    finally:
        cluster.stop()


@pytest.fixture
def owner(pg: EphemeralPostgres) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """Owner connection (autocommit) for test setup: truncation and clock manipulation."""
    with psycopg.connect(pg.url(OWNER), autocommit=True) as c:
        c.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        yield c


@pytest.fixture
def pool(pg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> Iterator[ConnectionPool[Conn]]:
    """Runtime-role pool (least privilege), as the service uses it."""
    p = make_pool(pg.url(), min_size=1, max_size=20)
    try:
        yield p
    finally:
        p.close()
