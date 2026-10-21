"""HTTP behaviour of /api/waitlist/*: validation, generic answers, authorisation, rate limits, headers."""

from __future__ import annotations

import logging
import time
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.waitlist.conftest import RecordingSender, form_token, signup_body, verify_token_from
from tracewise.waitlist import ratelimit
from tracewise.waitlist.security import issue_form_token, unsubscribe_token
from tracewise.waitlist.settings import WaitlistSettings

Owner = psycopg.Connection[tuple[Any, ...]]
API = "/api/waitlist"


def one(owner: Owner, sql: str) -> Any:
    row = owner.execute(sql).fetchone()
    assert row is not None
    return row[0]


def signup_ok(client: TestClient, settings: WaitlistSettings, email: str = "ada@example.com", **extra: object) -> dict[str, Any]:
    r = client.post(f"{API}/signup", json=signup_body(settings, email, **extra))
    assert r.status_code == 202, r.text
    body: dict[str, Any] = r.json()
    return body


def test_form_token_endpoint(client: TestClient) -> None:
    r = client.get(f"{API}/form")
    assert r.status_code == 200 and r.json()["form_token"].count(".") == 2
    assert r.headers["cache-control"] == "no-store"


def test_full_flow(client: TestClient, settings: WaitlistSettings, sender: RecordingSender, owner: Owner) -> None:
    body = signup_ok(client, settings, "Ada@Example.com", github="@octocat", updates=True)
    assert body["status"] == "check_email" and set(body) == {"status", "receipt"}
    assert len(sender.sent) == 1 and sender.sent[0].to == "ada@example.com"  # delivered inline
    token = verify_token_from(sender.sent[0])
    r = client.post(f"{API}/confirm", json={"token": token})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    receipt = r.json()["receipt"]
    assert [m.to for m in sender.sent] == ["ada@example.com", "owner@tracewise-test.example"]
    assert client.post(f"{API}/profile", json={"receipt": receipt, "ci_failure_freq": "weekly"}).status_code == 204
    assert one(owner, "SELECT ci_failure_freq FROM waitlist.signup") == "weekly"
    again = client.post(f"{API}/confirm", json={"token": token})
    assert again.json()["status"] == "already_confirmed"
    assert len(sender.sent) == 2  # no second notification


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b", "x" * 300 + "@example.com", "ada@example.com\r\nBcc: x@y.z"])
def test_invalid_email_is_rejected(client: TestClient, settings: WaitlistSettings, owner: Owner, email: str) -> None:
    r = client.post(f"{API}/signup", json=signup_body(settings, email))
    assert r.status_code == 422
    assert r.json()["error"] in ("invalid_email", "invalid_request")
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0


def test_invalid_github_is_rejected(client: TestClient, settings: WaitlistSettings) -> None:
    r = client.post(f"{API}/signup", json=signup_body(settings, github="not a user!"))
    assert r.status_code == 422 and r.json()["error"] == "invalid_github"


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"content": b"{not json", "headers": {"content-type": "application/json"}}, 422),
        ({"content": b"email=a@b.co", "headers": {"content-type": "application/x-www-form-urlencoded"}}, 415),
        ({"content": b"[]", "headers": {"content-type": "application/json"}}, 422),
        ({"content": b'{"email": 5}', "headers": {"content-type": "application/json"}}, 422),
        ({"content": b"{" + b" " * 5000 + b"}", "headers": {"content-type": "application/json"}}, 413),
    ],
)
def test_malformed_requests(client: TestClient, kwargs: dict[str, Any], status: int) -> None:
    assert client.post(f"{API}/signup", **kwargs).status_code == status


def test_unknown_fields_are_refused(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    """No mass assignment: status, confirmed_at and the like cannot be set by the client."""
    r = client.post(f"{API}/signup", json=signup_body(settings, status="confirmed", confirmed_at="2026-01-01"))
    assert r.status_code == 422
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0


def test_sql_injection_attempts_are_inert(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    r = client.post(f"{API}/signup", json=signup_body(settings, "x'); DROP TABLE waitlist.signup;--@example.com"))
    assert r.status_code == 422
    signup_ok(client, settings, "o'brien@example.com")
    assert one(owner, "SELECT email FROM waitlist.signup") == "o'brien@example.com"


def test_duplicate_signup_same_response(client: TestClient, settings: WaitlistSettings, sender: RecordingSender) -> None:
    a = client.post(f"{API}/signup", json=signup_body(settings))
    b = client.post(f"{API}/signup", json=signup_body(settings, "ADA@example.com "))
    assert a.status_code == b.status_code == 202
    assert set(a.json()) == set(b.json()) and a.json()["status"] == b.json()["status"]
    assert len(sender.sent) == 1


def test_honeypot_looks_successful_but_stores_nothing(
    client: TestClient, settings: WaitlistSettings, owner: Owner, sender: RecordingSender
) -> None:
    r = client.post(f"{API}/signup", json=signup_body(settings, website="https://spam.example"))
    assert r.status_code == 202 and r.json()["status"] == "check_email"
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0 and sender.sent == []


def test_too_fast_submission_is_silently_dropped(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    body = {"email": "ada@example.com", "form_token": issue_form_token(settings.secret_bytes())}
    assert client.post(f"{API}/signup", json=body).status_code == 202
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0


def test_missing_or_forged_form_token(client: TestClient, settings: WaitlistSettings) -> None:
    r = client.post(f"{API}/signup", json={"email": "ada@example.com"})
    assert r.status_code == 400 and r.json()["error"] == "form_expired"
    forged = issue_form_token(b"wrong-secret" * 4, now=time.time() - 10)
    assert client.post(f"{API}/signup", json={"email": "ada@example.com", "form_token": forged}).status_code == 400


def test_cross_origin_post_refused(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    r = client.post(f"{API}/signup", json=signup_body(settings), headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0
    same = client.post(f"{API}/signup", json=signup_body(settings), headers={"origin": "https://tracewise-test.example"})
    assert same.status_code == 202


def test_listed_origin_gets_cors(settings: WaitlistSettings, pool: Any, sender: RecordingSender) -> None:
    from tracewise.waitlist.app import create_app

    s = settings.model_copy(update={"waitlist_allowed_origins": "https://www.tracewise-test.example"})
    with TestClient(create_app(s, pool=pool, sender=sender), base_url="https://api.tracewise-test.example") as c:
        pre = c.options(f"{API}/signup", headers={"origin": "https://www.tracewise-test.example"})
        assert pre.headers["access-control-allow-origin"] == "https://www.tracewise-test.example"
        r = c.post(f"{API}/signup", json=signup_body(s), headers={"origin": "https://www.tracewise-test.example"})
        assert r.status_code == 202 and r.headers["access-control-allow-origin"] == "https://www.tracewise-test.example"
        bad = c.options(f"{API}/signup", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in bad.headers


def test_signup_rate_limit_per_ip_is_visible(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    codes = [
        client.post(f"{API}/signup", json=signup_body(settings, f"p{i}@example.com")).status_code
        for i in range(ratelimit.SIGNUP_PER_IP.limit + 2)
    ]
    assert codes == [202] * ratelimit.SIGNUP_PER_IP.limit + [429, 429]
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == ratelimit.SIGNUP_PER_IP.limit
    # raw IPs are never stored
    assert all(b"testclient" not in bytes(k) for (k,) in owner.execute("SELECT key_hash FROM waitlist.rate_limit"))


def test_signup_rate_limit_per_email_is_silent(
    client: TestClient, settings: WaitlistSettings, owner: Owner, sender: RecordingSender
) -> None:
    for _ in range(ratelimit.SIGNUP_PER_EMAIL.limit + 2):
        assert client.post(f"{API}/signup", json=signup_body(settings, "same@example.com")).status_code == 202
    assert (
        one(owner, "SELECT hits FROM waitlist.rate_limit WHERE bucket = 'signup_email'") == ratelimit.SIGNUP_PER_EMAIL.limit + 2
    )
    assert len(sender.sent) == 1


def test_confirm_rate_limit(client: TestClient) -> None:
    codes = [
        client.post(f"{API}/confirm", json={"token": f"guess-{i}"}).status_code for i in range(ratelimit.CONFIRM_PER_IP.limit + 1)
    ]
    assert codes[:-1] == [200] * ratelimit.CONFIRM_PER_IP.limit and codes[-1] == 429


def test_confirm_invalid_and_expired(
    client: TestClient, settings: WaitlistSettings, sender: RecordingSender, owner: Owner
) -> None:
    assert client.post(f"{API}/confirm", json={"token": "nope"}).json() == {"status": "invalid"}
    signup_ok(client, settings)
    owner.execute("UPDATE waitlist.verify_token SET expires_at = now() - interval '1 minute'")
    r = client.post(f"{API}/confirm", json={"token": verify_token_from(sender.sent[0])})
    assert r.json() == {"status": "expired"}


def test_profile_requires_a_real_receipt(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    first = signup_ok(client, settings)
    dup = signup_ok(client, settings)  # a stranger re-submitting the same address
    assert client.post(f"{API}/profile", json={"receipt": dup["receipt"], "ci_failure_freq": "daily"}).status_code == 204
    assert one(owner, "SELECT ci_failure_freq FROM waitlist.signup") is None  # decoy changed nothing
    assert client.post(f"{API}/profile", json={"receipt": first["receipt"], "ci_failure_freq": "rarely"}).status_code == 204
    assert one(owner, "SELECT ci_failure_freq FROM waitlist.signup") == "rarely"
    bad = client.post(f"{API}/profile", json={"receipt": first["receipt"], "ci_failure_freq": "hourly"})
    assert bad.status_code == 422


def test_unsubscribe(client: TestClient, settings: WaitlistSettings, owner: Owner) -> None:
    signup_ok(client, settings)
    sid = one(owner, "SELECT id FROM waitlist.signup")
    assert client.post(f"{API}/unsubscribe", json={"token": "x.y"}).json() == {"status": "not_found"}
    tok = unsubscribe_token(settings.secret_bytes(), sid)
    assert client.post(f"{API}/unsubscribe", json={"token": tok}).json() == {"status": "removed"}
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0
    assert client.post(f"{API}/unsubscribe", json={"token": tok}).json() == {"status": "not_found"}


def test_count_endpoint(client: TestClient, owner: Owner) -> None:
    r = client.get(f"{API}/count")
    assert r.json() == {"shown": False}
    assert "max-age=300" in r.headers["cache-control"]


def test_outbox_endpoint_requires_cron_secret(client: TestClient, settings: WaitlistSettings) -> None:
    assert client.get(f"{API}/internal/outbox").status_code == 401
    assert client.get(f"{API}/internal/outbox", headers={"authorization": "Bearer wrong"}).status_code == 401
    secret = settings.cron_secret.get_secret_value() if settings.cron_secret else ""
    r = client.get(f"{API}/internal/outbox", headers={"authorization": f"Bearer {secret}"})
    assert r.status_code == 200 and set(r.json()) == {"delivery", "purged", "email_mode"}


def test_outbox_endpoint_disabled_without_secret(settings: WaitlistSettings, pool: Any, sender: RecordingSender) -> None:
    from tracewise.waitlist.app import create_app

    s = settings.model_copy(update={"cron_secret": None})
    with TestClient(create_app(s, pool=pool, sender=sender), base_url="https://tracewise-test.example") as c:
        assert c.get(f"{API}/internal/outbox", headers={"authorization": "Bearer "}).status_code == 401


def test_provider_outage_does_not_fail_signup(
    client: TestClient, settings: WaitlistSettings, sender: RecordingSender, owner: Owner
) -> None:
    from tracewise.waitlist.email import SendResult

    sender.fail = [SendResult(ok=False, error="network error: ConnectTimeout", retryable=True)]
    signup_ok(client, settings)
    assert one(owner, "SELECT status FROM waitlist.email_outbox") == "pending"


def test_security_headers_and_no_docs(client: TestClient) -> None:
    r = client.get(f"{API}/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_database_outage_returns_503(settings: WaitlistSettings, sender: RecordingSender) -> None:
    from tracewise.waitlist.app import create_app
    from tracewise.waitlist.db import get_pool

    dead = get_pool("postgresql://nobody@/nowhere?host=/nonexistent-socket-dir&connect_timeout=1")
    with TestClient(create_app(settings, pool=dead, sender=sender), base_url="https://tracewise-test.example") as c:
        r = c.post(f"{API}/signup", json=signup_body(settings))
        assert r.status_code == 503 and r.json() == {"error": "unavailable"}


def test_logs_never_contain_tokens_or_addresses(
    client: TestClient, settings: WaitlistSettings, sender: RecordingSender, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    signup_ok(client, settings, "private.person@example.com")
    token = verify_token_from(sender.sent[0])
    client.post(f"{API}/confirm", json={"token": token})
    text = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert token not in text
    assert "private.person@example.com" not in text


def test_response_bodies_never_reveal_secrets(client: TestClient, settings: WaitlistSettings) -> None:
    bodies = [
        client.get(f"{API}/health").text,
        client.get(f"{API}/count").text,
        client.post(f"{API}/signup", json={"email": "x"}).text,
    ]
    for secret in settings.secret_values():
        assert all(secret not in b for b in bodies)
    assert form_token(settings) not in bodies[0]


@pytest.mark.parametrize(
    "update",
    [
        {"waitlist_email_mode": "disabled", "resend_api_key": None},
        {"waitlist_env": "production", "waitlist_owner_notify_email": None},
    ],
)
def test_signups_closed_when_email_cannot_work(
    settings: WaitlistSettings, pool: Any, sender: RecordingSender, owner: Owner, update: dict[str, object]
) -> None:
    """Email disabled, or no owner inbox in production: nothing is accepted, and the page is told why (generically)."""
    from tracewise.waitlist.app import create_app

    s = settings.model_copy(update=update)
    with TestClient(create_app(s, pool=pool, sender=sender), base_url="https://tracewise-test.example") as c:
        assert c.get(f"{API}/health").json()["accepting_signups"] is False
        assert c.get(f"{API}/form").json() == {"error": "signups_closed"}
        r = c.post(f"{API}/signup", json=signup_body(s))
        assert r.status_code == 503 and r.json() == {"error": "signups_closed"}
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0 and sender.sent == []


def test_confirm_and_unsubscribe_still_work_while_signups_are_closed(
    client: TestClient, settings: WaitlistSettings, pool: Any, sender: RecordingSender, owner: Owner
) -> None:
    from tracewise.waitlist.app import create_app

    signup_ok(client, settings)
    token = verify_token_from(sender.sent[0])
    closed = settings.model_copy(update={"waitlist_email_mode": "disabled", "resend_api_key": None})
    with TestClient(create_app(closed, pool=pool, sender=sender), base_url="https://tracewise-test.example") as c:
        assert c.post(f"{API}/confirm", json={"token": token}).json()["status"] == "confirmed"


def test_health_reports_accepting(client: TestClient) -> None:
    assert client.get(f"{API}/health").json()["accepting_signups"] is True


def test_invalid_configuration_serves_a_closed_api(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A bad environment (here: a too-short secret) must not crash the app or leak the value: every route is 503."""
    from tracewise.waitlist.app import create_app
    from tracewise.waitlist.settings import get_settings

    monkeypatch.setenv("WAITLIST_ENV", "production")
    monkeypatch.setenv("WAITLIST_SECRET", "too-short-LEAKCHECK")
    get_settings.cache_clear()
    caplog.set_level(logging.ERROR)
    try:
        with TestClient(create_app(), base_url="https://tracewise-test.example") as c:
            h = c.get(f"{API}/health")
            assert h.status_code == 503
            assert h.json() == {"ok": False, "accepting_signups": False, "config_error": ["settings"]}
            assert c.get(f"{API}/form").json() == {"error": "signups_closed"}
            r = c.post(f"{API}/signup", json={"email": "ada@example.com", "form_token": "x"})
            assert r.status_code == 503 and r.json() == {"error": "signups_closed"}
            assert c.post(f"{API}/confirm", json={"token": "x"}).json() == {"error": "unavailable"}
            assert c.get(f"{API}/internal/outbox").status_code == 503
    finally:
        get_settings.cache_clear()
    assert "waitlist.config_invalid" in caplog.text and "WAITLIST_SECRET must be at least 32" in caplog.text
    assert "LEAKCHECK" not in caplog.text
