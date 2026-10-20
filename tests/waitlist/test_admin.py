"""Operator CLI: export, delete, stats, outbox and retry against the disposable database."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from tests.pg import EphemeralPostgres
from tests.waitlist.conftest import ROLE
from tracewise.waitlist import admin, service
from tracewise.waitlist.db import Conn
from tracewise.waitlist.settings import WaitlistSettings

Owner = psycopg.Connection[tuple[Any, ...]]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, wpg: EphemeralPostgres, pool: ConnectionPool[Conn]) -> None:
    for k in ("WAITLIST_EMAIL_MODE", "RESEND_API_KEY", "WAITLIST_OWNER_NOTIFY_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WAITLIST_ENV", "test")
    monkeypatch.setenv("WAITLIST_DATABASE_URL", wpg.url(ROLE))


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = admin.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_export_confirmed_only_by_default(
    env: None, pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    service.signup(pool, settings, "pending@example.com", None, False)
    owner.execute(
        "INSERT INTO waitlist.signup (email, email_normalized, consent_version, status, confirmed_at, github_login) "
        "VALUES ('c@example.com', 'c@example.com', 'v', 'confirmed', now(), 'octocat')"
    )
    code, out, _ = run(capsys, "export")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert code == 0 and [r["email"] for r in rows] == ["c@example.com"]
    assert set(rows[0]) == set(admin.EXPORT_COLUMNS)  # no ids, tokens or internal fields
    code, out, _ = run(capsys, "export", "--all", "--json")
    assert sorted(r["email"] for r in json.loads(out)) == ["c@example.com", "pending@example.com"]


def test_delete_by_email(
    env: None, pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    assert run(capsys, "delete", " ADA@example.com ")[1].strip() == "deleted"
    assert run(capsys, "delete", "ada@example.com")[1].strip() == "not found"
    assert run(capsys, "delete", "not-an-email")[0] == 2
    assert owner.execute("SELECT count(*) FROM waitlist.signup").fetchone() == (0,)


def test_stats_and_outbox(
    env: None, pool: ConnectionPool[Conn], settings: WaitlistSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    code, out, _ = run(capsys, "stats")
    data = json.loads(out)
    assert code == 0 and data["signups"]["pending"] == 1 and data["public"] == {"shown": False}
    code, out, err = run(capsys, "outbox")
    assert code == 0 and '"kind": "verify"' in out and "disabled" in err


def test_retry_requeues_failed_but_disabled_mode_sends_nothing(
    env: None, pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    owner.execute("UPDATE waitlist.email_outbox SET status = 'failed', attempts = 8, last_error = 'resend 403'")
    code, out, _ = run(capsys, "retry", "--failed")
    assert code == 0 and "re-queued 1" in out
    assert owner.execute("SELECT status, attempts, sent_at FROM waitlist.email_outbox").fetchone() == ("pending", 0, None)


def test_missing_database_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("WAITLIST_DATABASE_URL", raising=False)
    assert run(capsys, "stats")[0] == 2
