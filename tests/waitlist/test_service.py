"""Signup, confirmation, outbox delivery, counter and retention against a real disposable PostgreSQL."""

from __future__ import annotations

import threading
from typing import Any

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from tests.waitlist.conftest import RecordingSender, verify_token_from
from tracewise.waitlist import service
from tracewise.waitlist.db import Conn
from tracewise.waitlist.email import DisabledSender, SendResult
from tracewise.waitlist.security import check_receipt
from tracewise.waitlist.settings import WaitlistSettings

Owner = psycopg.Connection[tuple[Any, ...]]


def one(owner: Owner, sql: str, *args: object) -> Any:
    row = owner.execute(sql, args).fetchone()
    assert row is not None
    return row[0]


def signup_and_deliver(
    pool: ConnectionPool[Conn],
    s: WaitlistSettings,
    sender: RecordingSender,
    email: str = "ada@example.com",
    github: str | None = None,
    updates: bool = False,
) -> str:
    r = service.signup(pool, s, email, github, updates)
    service.process_outbox(pool, s, sender, ids=r.outbox_ids)
    return verify_token_from(sender.sent[-1])


# ------------------------------------------------------------------ signup
def test_signup_creates_pending_row_and_queues_one_verification(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings
) -> None:
    r = service.signup(pool, settings, "ada@example.com", "octocat", True)
    assert len(r.outbox_ids) == 1 and check_receipt(settings.secret_bytes(), r.receipt) is not None
    row = owner.execute(
        "SELECT status, confirmed_at, github_login, updates_consent, updates_consent_at IS NOT NULL, consent_version "
        "FROM waitlist.signup"
    ).fetchall()
    assert row == [("pending", None, "octocat", True, True, service.CONSENT_VERSION)]
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'verify' AND status = 'pending'") == 1


def test_consent_defaults_to_no_and_has_no_timestamp(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    assert owner.execute("SELECT updates_consent, updates_consent_at FROM waitlist.signup").fetchone() == (False, None)


def test_duplicate_signup_is_indistinguishable_and_changes_nothing(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings
) -> None:
    first = service.signup(pool, settings, "ada@example.com", "octocat", False)
    again = service.signup(pool, settings, "ada@example.com", "attacker", True)
    assert check_receipt(settings.secret_bytes(), again.receipt) is None  # decoy: same shape, authorises nothing
    assert len(again.receipt) == len(first.receipt)
    assert again.outbox_ids == []  # within the resend cooldown
    assert owner.execute("SELECT github_login, updates_consent FROM waitlist.signup").fetchall() == [("octocat", False)]
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 1


def test_pending_duplicate_after_cooldown_resends(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    signup_and_deliver(pool, settings, sender)
    owner.execute("UPDATE waitlist.signup SET last_verify_sent_at = now() - interval '11 minutes'")
    again = service.signup(pool, settings, "ada@example.com", None, False)
    assert len(again.outbox_ids) == 1


def test_confirmed_duplicate_sends_nothing(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    assert service.confirm(pool, settings, token).status == "confirmed"
    owner.execute("UPDATE waitlist.signup SET last_verify_sent_at = now() - interval '1 day'")
    assert service.signup(pool, settings, "ada@example.com", None, False).outbox_ids == []


def test_concurrent_duplicate_signups_store_one_row(pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings) -> None:
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def go() -> None:
        try:
            barrier.wait()
            service.signup(pool, settings, "race@example.com", None, False)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 1
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'verify'") == 1


def test_database_constraints_reject_inconsistent_rows(owner: Owner) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute("INSERT INTO waitlist.signup (email, email_normalized, consent_version) VALUES ('A@x.io', 'A@x.io', 'v')")
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "INSERT INTO waitlist.signup (email, email_normalized, consent_version, status) "
            "VALUES ('a@x.io', 'a@x.io', 'v', 'confirmed')"
        )  # confirmed without confirmed_at
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "INSERT INTO waitlist.signup (email, email_normalized, consent_version, updates_consent) "
            "VALUES ('a@x.io', 'a@x.io', 'v', true)"
        )  # consent without a timestamp


# ------------------------------------------------------------------ verification
def test_verification_email_contents(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    m = sender.sent[0]
    assert m.to == "ada@example.com"
    assert "https://tracewise-test.example/confirm/#token=" in m.text and token in m.html
    assert "/unsubscribe/#token=" in m.headers["List-Unsubscribe"]
    # only the hash is stored
    stored = owner.execute("SELECT token_hash FROM waitlist.verify_token").fetchall()
    assert len(stored) == 1 and token.encode() not in bytes(stored[0][0])
    assert one(owner, "SELECT status FROM waitlist.email_outbox") == "sent"


def test_confirm_success_then_reuse(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    first = service.confirm(pool, settings, token)
    assert first.status == "confirmed" and len(first.outbox_ids) == 1
    assert check_receipt(settings.secret_bytes(), first.receipt or "") is not None
    assert owner.execute("SELECT status, confirmed_at IS NOT NULL FROM waitlist.signup").fetchone() == ("confirmed", True)
    assert one(owner, "SELECT count(*) FROM waitlist.verify_token WHERE used_at IS NULL") == 0
    second = service.confirm(pool, settings, token)  # a repeated click
    assert second.status == "already_confirmed" and second.outbox_ids == []
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'owner_notify'") == 1


def test_confirm_invalid_token(pool: ConnectionPool[Conn], settings: WaitlistSettings) -> None:
    assert service.confirm(pool, settings, "not-a-real-token").status == "invalid"
    assert service.confirm(pool, settings, "").status == "invalid"


def test_confirm_expired_token_does_not_confirm(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    owner.execute("UPDATE waitlist.verify_token SET expires_at = now() - interval '1 second'")
    r = service.confirm(pool, settings, token)
    assert r.status == "expired" and r.receipt is None and r.outbox_ids == []
    assert one(owner, "SELECT status FROM waitlist.signup") == "pending"
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'owner_notify'") == 0


def test_older_link_still_works_after_resend(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    first = signup_and_deliver(pool, settings, sender)
    owner.execute("UPDATE waitlist.signup SET last_verify_sent_at = now() - interval '1 hour'")
    second = signup_and_deliver(pool, settings, sender)
    assert first != second
    assert service.confirm(pool, settings, first).status == "confirmed"
    assert service.confirm(pool, settings, second).status == "already_confirmed"


def test_concurrent_confirms_create_one_notification(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    results: list[str] = []
    barrier = threading.Barrier(6)

    def go() -> None:
        barrier.wait()
        results.append(service.confirm(pool, settings, token).status)

    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["already_confirmed"] * 5 + ["confirmed"]
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'owner_notify'") == 1


def test_confirm_cancels_unsent_verification(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    owner.execute("UPDATE waitlist.signup SET last_verify_sent_at = now() - interval '1 hour'")
    service.signup(pool, settings, "ada@example.com", None, False)  # queued, not yet sent
    service.confirm(pool, settings, token)
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'verify' AND status = 'cancelled'") == 1


# ------------------------------------------------------------------ owner notification
def test_owner_notification_sent_once_with_details(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender, github="octocat", updates=True)
    r = service.confirm(pool, settings, token)
    sid = check_receipt(settings.secret_bytes(), r.receipt or "")
    assert sid is not None
    service.set_ci_frequency(pool, sid, "weekly")
    service.process_outbox(pool, settings, sender)
    service.process_outbox(pool, settings, sender)  # a second run finds nothing to do
    notes = [m for m in sender.sent if m.to == "owner@tracewise-test.example"]
    assert len(notes) == 1
    n = notes[0]
    assert n.idempotency_key.startswith("owner-notify-")
    for expected in ("ada@example.com", "octocat", "Product-updates consent: yes", "CI fails: weekly", "Confirmed at (UTC):"):
        assert expected in n.text
    assert "token" not in n.text.lower()
    row = owner.execute(
        "SELECT status, provider, provider_message_id IS NOT NULL, sent_at IS NOT NULL "
        "FROM waitlist.email_outbox WHERE kind = 'owner_notify'"
    ).fetchone()
    assert row == ("sent", "resend", True, True)


def test_no_owner_notification_for_unverified_signups(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    signup_and_deliver(pool, settings, sender)
    service.process_outbox(pool, settings, sender)
    assert [m.to for m in sender.sent] == ["ada@example.com"]
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox WHERE kind = 'owner_notify'") == 0


def test_owner_inbox_unset_defers_without_failing(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    s = settings.model_copy(update={"waitlist_owner_notify_email": None})
    token = signup_and_deliver(pool, s, sender)
    assert service.confirm(pool, s, token).status == "confirmed"
    stats = service.process_outbox(pool, s, sender)
    assert stats["deferred"] == 1 and stats["sent"] == 0
    row = owner.execute("SELECT status, attempts, last_error FROM waitlist.email_outbox WHERE kind = 'owner_notify'").fetchone()
    assert row == ("pending", 0, "WAITLIST_OWNER_NOTIFY_EMAIL is not set")
    assert len(sender.sent) == 1  # only the verification email; no invented recipient


def test_provider_failure_keeps_confirmation_and_retries_with_same_key(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    token = signup_and_deliver(pool, settings, sender)
    sender.fail = [SendResult(ok=False, error="resend 503 internal_server_error: down", retryable=True)]
    assert service.confirm(pool, settings, token).status == "confirmed"
    stats = service.process_outbox(pool, settings, sender)
    assert stats == {"sent": 0, "retry": 1, "failed": 0, "deferred": 0}
    assert one(owner, "SELECT status FROM waitlist.signup") == "confirmed"  # never rolled back
    row = owner.execute(
        "SELECT status, attempts, last_error, next_attempt_at > now() FROM waitlist.email_outbox WHERE kind = 'owner_notify'"
    ).fetchone()
    assert row is not None and row[0] == "pending" and row[1] == 1 and "503" in row[2] and row[3]
    payload_before = one(owner, "SELECT payload FROM waitlist.email_outbox WHERE kind = 'owner_notify'")
    assert payload_before["email"] == "ada@example.com"
    owner.execute("UPDATE waitlist.email_outbox SET next_attempt_at = now() WHERE kind = 'owner_notify'")
    service.process_outbox(pool, settings, sender)
    keys = [m.idempotency_key for m in sender.sent if m.to.startswith("owner@")]
    assert len(keys) == 1 and keys[0].startswith("owner-notify-")
    assert one(owner, "SELECT status FROM waitlist.email_outbox WHERE kind = 'owner_notify'") == "sent"


def test_permanent_failure_is_recorded_not_faked(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    sender.fail = [SendResult(ok=False, error="resend 403 validation_error: domain not verified for owner@x.io", retryable=False)]
    service.signup(pool, settings, "ada@example.com", None, False)
    stats = service.process_outbox(pool, settings, sender)
    assert stats["failed"] == 1
    row = owner.execute("SELECT status, sent_at, last_error FROM waitlist.email_outbox").fetchone()
    assert row is not None and row[0] == "failed" and row[1] is None
    assert "owner@x.io" not in row[2] and "[address]" in row[2]


def test_attempts_are_capped(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    for _ in range(service.MAX_ATTEMPTS):
        sender.fail.append(SendResult(ok=False, error="resend 500", retryable=True))
        owner.execute("UPDATE waitlist.email_outbox SET next_attempt_at = now()")
        service.process_outbox(pool, settings, sender)
    assert owner.execute("SELECT status, attempts FROM waitlist.email_outbox").fetchone() == ("failed", service.MAX_ATTEMPTS)


def test_disabled_sender_claims_nothing(pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    stats = service.process_outbox(pool, settings, DisabledSender())
    assert stats == {"sent": 0, "retry": 0, "failed": 0, "deferred": 0}
    assert owner.execute("SELECT status, attempts, sent_at FROM waitlist.email_outbox").fetchone() == ("pending", 0, None)
    assert one(owner, "SELECT count(*) FROM waitlist.verify_token") == 0  # no link was created, none could leak


def test_crashed_send_is_reclaimed_after_lease(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    service.signup(pool, settings, "ada@example.com", None, False)
    owner.execute("UPDATE waitlist.email_outbox SET status = 'sending', attempts = 1, lease_until = now() - interval '1 second'")
    assert service.process_outbox(pool, settings, sender)["sent"] == 1


def test_concurrent_workers_send_each_message_once(
    pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings, sender: RecordingSender
) -> None:
    for i in range(6):
        service.signup(pool, settings, f"p{i}@example.com", None, False)
    barrier = threading.Barrier(3)

    def go() -> None:
        barrier.wait()
        service.process_outbox(pool, settings, sender, limit=10)

    threads = [threading.Thread(target=go) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(m.to for m in sender.sent) == sorted(f"p{i}@example.com" for i in range(6))


# ------------------------------------------------------------------ public counter
def add_confirmed(owner: Owner, n: int, start: int = 0) -> None:
    owner.execute(
        "INSERT INTO waitlist.signup (email, email_normalized, consent_version, status, confirmed_at) "
        "SELECT 'c' || g || '@example.com', 'c' || g || '@example.com', 'v', 'confirmed', now() "
        "FROM generate_series(%s::int, %s::int) g",
        (start, start + n - 1),
    )


def add_pending(owner: Owner, n: int) -> None:
    owner.execute(
        "INSERT INTO waitlist.signup (email, email_normalized, consent_version) "
        "SELECT 'p' || g || '@example.com', 'p' || g || '@example.com', 'v' FROM generate_series(1, %s::int) g",
        (n,),
    )


def test_counter_hidden_below_threshold_and_ignores_unconfirmed(pool: ConnectionPool[Conn], owner: Owner) -> None:
    add_confirmed(owner, 49)
    add_pending(owner, 500)
    assert service.public_count(pool, use_memo=False) == {"shown": False}


def test_counter_rounds_down_to_tens(pool: ConnectionPool[Conn], owner: Owner) -> None:
    add_confirmed(owner, 57)
    out = service.public_count(pool, use_memo=False)
    assert out["shown"] is True and out["count_floor"] == 50 and set(out) == {"shown", "count_floor", "as_of"}


def test_counter_recomputes_at_most_hourly(pool: ConnectionPool[Conn], owner: Owner) -> None:
    add_confirmed(owner, 60)
    assert service.public_count(pool, use_memo=False)["count_floor"] == 60
    add_confirmed(owner, 20, start=1000)
    assert service.public_count(pool, use_memo=False)["count_floor"] == 60  # unchanged within the hour
    owner.execute("UPDATE waitlist.public_stats SET computed_at = now() - interval '61 minutes'")
    assert service.public_count(pool, use_memo=False)["count_floor"] == 80


def test_counter_process_memo(pool: ConnectionPool[Conn], owner: Owner) -> None:
    assert service.public_count(pool) == {"shown": False}
    add_confirmed(owner, 70)
    owner.execute("DELETE FROM waitlist.public_stats")
    assert service.public_count(pool) == {"shown": False}  # served from the per-process memo
    service.reset_memo()
    assert service.public_count(pool)["count_floor"] == 70


def test_counter_schema_refuses_small_or_unrounded_numbers(owner: Owner) -> None:
    for bad in (10, 49, 55):
        with pytest.raises(psycopg.errors.CheckViolation):
            owner.execute("INSERT INTO waitlist.public_stats VALUES (1, true, %s, now())", (bad,))


def test_counter_is_never_seeded(pool: ConnectionPool[Conn], owner: Owner) -> None:
    assert one(owner, "SELECT count(*) FROM waitlist.public_stats") == 0
    assert service.public_count(pool, use_memo=False) == {"shown": False}


# ------------------------------------------------------------------ profile, deletion, retention
def test_ci_frequency_and_delete(pool: ConnectionPool[Conn], owner: Owner, settings: WaitlistSettings) -> None:
    r = service.signup(pool, settings, "ada@example.com", None, False)
    sid = check_receipt(settings.secret_bytes(), r.receipt)
    assert sid is not None
    service.set_ci_frequency(pool, sid, "daily")
    assert one(owner, "SELECT ci_failure_freq FROM waitlist.signup") == "daily"
    assert service.delete_signup(pool, sid) is True
    assert one(owner, "SELECT count(*) FROM waitlist.signup") == 0
    assert one(owner, "SELECT count(*) FROM waitlist.email_outbox") == 0  # cascades
    assert service.delete_signup(pool, sid) is False


def test_purge_removes_stale_unconfirmed_only(pool: ConnectionPool[Conn], owner: Owner) -> None:
    add_pending(owner, 3)
    add_confirmed(owner, 2)
    owner.execute("UPDATE waitlist.signup SET created_at = now() - interval '8 days'")
    out = service.purge(pool)
    assert out["unconfirmed_signups"] == 3
    assert one(owner, "SELECT count(*) FROM waitlist.signup WHERE status = 'confirmed'") == 2
