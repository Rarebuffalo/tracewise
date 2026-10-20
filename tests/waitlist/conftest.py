"""Waitlist fixtures: one disposable cluster with the product schema AND the waitlist schema side by side (so
isolation between them is tested for real), a runtime pool on the least-privilege role, and a recording sender."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.pg import OWNER, EphemeralPostgres, ephemeral
from tracewise.db.migrate import upgrade as product_upgrade
from tracewise.waitlist import service
from tracewise.waitlist.app import create_app
from tracewise.waitlist.db import Conn, get_pool
from tracewise.waitlist.email import Message, SendResult
from tracewise.waitlist.migrate import upgrade as waitlist_upgrade
from tracewise.waitlist.security import issue_form_token
from tracewise.waitlist.settings import WaitlistSettings

if shutil.which("initdb") is None:  # pragma: no cover
    pytest.skip("PostgreSQL server binaries not installed", allow_module_level=True)

ROLE = "tracewise_waitlist"
TABLES = "waitlist.signup, waitlist.verify_token, waitlist.email_outbox, waitlist.rate_limit, waitlist.public_stats"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def wpg() -> Iterator[EphemeralPostgres]:
    cluster = ephemeral()
    try:
        product_upgrade(cluster.url(OWNER))
        with psycopg.connect(cluster.url(OWNER), autocommit=True) as c:
            for stmt in (ROOT / "scripts/db/provision_waitlist_role.sql").read_text().split(";"):
                body = "\n".join(ln for ln in stmt.splitlines() if not ln.strip().startswith("--")).strip()
                if body:
                    c.execute(body.encode())
        waitlist_upgrade(cluster.url(OWNER))
        yield cluster
    finally:
        cluster.stop()


@pytest.fixture
def owner(wpg: EphemeralPostgres) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(wpg.url(OWNER), autocommit=True) as c:
        c.execute(f"TRUNCATE {TABLES} CASCADE")
        service.reset_memo()
        yield c


@pytest.fixture
def pool(wpg: EphemeralPostgres, owner: psycopg.Connection[tuple[object, ...]]) -> Iterator[ConnectionPool[Conn]]:
    yield get_pool(wpg.url(ROLE))


@dataclass
class RecordingSender:
    """Records every message; `fail` is a queue of results to return before succeeding."""

    name: str = "recording"
    sent: list[Message] = field(default_factory=list)
    fail: list[SendResult] = field(default_factory=list)
    calls: int = 0

    def send(self, m: Message) -> SendResult:
        self.calls += 1
        if self.fail:
            return self.fail.pop(0)
        self.sent.append(m)
        return SendResult(ok=True, provider="resend", message_id=f"msg-{self.calls}")


@pytest.fixture
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture
def settings(tmp_path: Path) -> WaitlistSettings:
    return WaitlistSettings(
        waitlist_env="test",
        waitlist_secret="t" * 48,
        waitlist_public_site_url="https://tracewise-test.example",
        waitlist_email_mode="resend",
        resend_api_key="re_test_placeholder",
        waitlist_email_from="Tracewise <hello@updates.tracewise-test.example>",
        waitlist_owner_notify_email="owner@tracewise-test.example",
        cron_secret="c" * 40,
        waitlist_email_file_dir=tmp_path / "mail",
    )


@pytest.fixture
def client(settings: WaitlistSettings, pool: ConnectionPool[Conn], sender: RecordingSender) -> Iterator[TestClient]:
    app = create_app(settings, pool=pool, sender=sender)
    with TestClient(app, base_url="https://tracewise-test.example") as c:
        yield c


def form_token(settings: WaitlistSettings) -> str:
    return issue_form_token(settings.secret_bytes(), now=time.time() - 5)


def signup_body(settings: WaitlistSettings, email: str = "ada@example.com", **extra: object) -> dict[str, object]:
    return {"email": email, "form_token": form_token(settings), **extra}


def verify_token_from(m: Message) -> str:
    return m.text.split("/confirm/#token=", 1)[1].split()[0]
