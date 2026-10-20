"""Waitlist operations. Every state change is one transaction; every email is an outbox row written in the same
transaction as the change it announces, then delivered (and retried) by `process_outbox`.

Invariants (enforced by the schema as well as here):
- a signup counts only when `status = 'confirmed'`, which requires a valid, unexpired verification token;
- at most one owner notification per signup, ever (unique index), sent with a stable Idempotency-Key;
- a failed delivery never rolls back a confirmation: delivery state lives in the outbox row only.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tracewise.waitlist import outbound, templates
from tracewise.waitlist.db import Conn, transaction
from tracewise.waitlist.email import DisabledSender, Message, Sender, sanitize_error
from tracewise.waitlist.security import (
    decoy_receipt,
    is_disposable,
    issue_receipt,
    new_token,
    token_hash,
    unsubscribe_token,
)
from tracewise.waitlist.settings import WaitlistSettings

log = logging.getLogger("tracewise.waitlist")

# Identifier of the exact consent wording shown next to the form (stored with every signup).
CONSENT_VERSION = "2026-10-21.v1"
DISPLAY_THRESHOLD = 50  # the public count stays hidden below this many confirmed signups
DISPLAY_STEP = 10  # and is rounded down to a multiple of this
RECOMPUTE_AFTER_S = 3600  # the published aggregate changes at most hourly
PROCESS_CACHE_S = 300  # per-instance memo in front of the aggregate row
VERIFY_RESEND_COOLDOWN = "10 minutes"
MAX_ATTEMPTS = 8
BACKOFF_S = (60, 300, 900, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 24 * 3600)
UNVERIFIED_RETENTION = "7 days"


@dataclass(frozen=True)
class SignupResult:
    receipt: str
    outbox_ids: list[uuid.UUID]


ConfirmStatus = Literal["confirmed", "already_confirmed", "expired", "invalid"]


@dataclass(frozen=True)
class ConfirmResult:
    status: ConfirmStatus
    receipt: str | None
    outbox_ids: list[uuid.UUID]


# ------------------------------------------------------------------ signup
def signup(
    pool: ConnectionPool[Conn], s: WaitlistSettings, email_normalized: str, github: str | None, updates: bool
) -> SignupResult:
    """Create a pending signup (or re-send verification for an existing pending one). The caller always answers
    the same way, whether the address was new, pending or already confirmed (no account enumeration)."""
    secret = s.secret_bytes()
    with transaction(pool) as c:
        row = c.execute(
            """INSERT INTO waitlist.signup (email, email_normalized, github_login, updates_consent, updates_consent_at,
                                            consent_version, disposable_domain, last_verify_sent_at)
               VALUES (%(e)s, %(e)s, %(gh)s, %(u)s, CASE WHEN %(u)s THEN now() END, %(cv)s, %(d)s, now())
               ON CONFLICT (email_normalized) DO NOTHING
               RETURNING id""",
            {"e": email_normalized, "gh": github, "u": updates, "cv": CONSENT_VERSION, "d": is_disposable(email_normalized)},
        ).fetchone()
        if row is not None:
            sid = row["id"]
            oid = _queue_verify(c, sid)
            return SignupResult(issue_receipt(secret, sid), [oid] if oid else [])
        # Existing address: never change its data from an unauthenticated request. If it is still pending and no
        # verification went out recently, queue another (the earlier links stay valid until they expire).
        existing = c.execute(
            """SELECT id, status, (last_verify_sent_at IS NULL OR last_verify_sent_at < now() - %s::interval) AS may_resend
               FROM waitlist.signup WHERE email_normalized = %s FOR UPDATE""",
            (VERIFY_RESEND_COOLDOWN, email_normalized),
        ).fetchone()
        ids: list[uuid.UUID] = []
        if existing is not None and existing["status"] == "pending" and existing["may_resend"]:
            c.execute("UPDATE waitlist.signup SET last_verify_sent_at = now() WHERE id = %s", (existing["id"],))
            oid = _queue_verify(c, existing["id"])
            if oid:
                ids.append(oid)
        return SignupResult(decoy_receipt(), ids)


def _queue_verify(c: Conn, signup_id: uuid.UUID) -> uuid.UUID | None:
    row = c.execute(
        """INSERT INTO waitlist.email_outbox (signup_id, kind) VALUES (%s, 'verify')
           ON CONFLICT (signup_id) WHERE kind = 'verify' AND status IN ('pending', 'sending') DO NOTHING
           RETURNING id""",
        (signup_id,),
    ).fetchone()
    return row["id"] if row else None


# ------------------------------------------------------------------ confirmation
def confirm(pool: ConnectionPool[Conn], s: WaitlistSettings, token: str) -> ConfirmResult:
    secret = s.secret_bytes()
    with transaction(pool) as c:
        r = c.execute(
            """SELECT t.signup_id, t.expires_at < now() AS expired, s.status
               FROM waitlist.verify_token t JOIN waitlist.signup s ON s.id = t.signup_id
               WHERE t.token_hash = %s
               FOR UPDATE OF s""",
            (token_hash(token),),
        ).fetchone()
        if r is None:
            return ConfirmResult("invalid", None, [])
        sid = r["signup_id"]
        if r["status"] == "confirmed":  # a repeated click, or another link for the same address
            return ConfirmResult("already_confirmed", issue_receipt(secret, sid), [])
        if r["expired"]:
            return ConfirmResult("expired", None, [])
        c.execute("UPDATE waitlist.signup SET status = 'confirmed', confirmed_at = now() WHERE id = %s", (sid,))
        c.execute("UPDATE waitlist.verify_token SET used_at = now() WHERE signup_id = %s AND used_at IS NULL", (sid,))
        c.execute(
            """UPDATE waitlist.email_outbox SET status = 'cancelled', lease_until = NULL, updated_at = now()
               WHERE signup_id = %s AND kind = 'verify' AND status = 'pending'""",
            (sid,),
        )
        row = c.execute(
            """INSERT INTO waitlist.email_outbox (signup_id, kind) VALUES (%s, 'owner_notify')
               ON CONFLICT (signup_id) WHERE kind = 'owner_notify' DO NOTHING RETURNING id""",
            (sid,),
        ).fetchone()
    return ConfirmResult("confirmed", issue_receipt(secret, sid), [row["id"]] if row else [])


# ------------------------------------------------------------------ follow-up answer and removal
def set_ci_frequency(pool: ConnectionPool[Conn], signup_id: uuid.UUID, freq: str) -> None:
    """Only reachable with a receipt that the server issued to this signup (see security.check_receipt)."""
    with transaction(pool) as c:
        c.execute("UPDATE waitlist.signup SET ci_failure_freq = %s WHERE id = %s", (freq, signup_id))


def delete_signup(pool: ConnectionPool[Conn], signup_id: uuid.UUID) -> bool:
    """Hard delete (tokens and outbox rows cascade)."""
    with transaction(pool) as c:
        return c.execute("DELETE FROM waitlist.signup WHERE id = %s", (signup_id,)).rowcount > 0


# ------------------------------------------------------------------ public aggregate
_memo_lock = threading.Lock()
_memo: tuple[float, dict[str, Any]] | None = None


def public_count(pool: ConnectionPool[Conn], *, use_memo: bool = True) -> dict[str, Any]:
    """{"shown": false} or {"shown": true, "count_floor": N, "as_of": ISO}. Only confirmed signups count; the row is
    recomputed at most hourly (one instance at a time); the schema forbids publishing anything below 50."""
    global _memo
    now = time.monotonic()
    if use_memo:
        with _memo_lock:
            if _memo is not None and now - _memo[0] < PROCESS_CACHE_S:
                return dict(_memo[1])
    with transaction(pool) as c:
        row = c.execute("SELECT shown, count_floor, computed_at FROM waitlist.public_stats WHERE id = 1").fetchone()
        stale = row is None or (datetime.now(UTC) - row["computed_at"]).total_seconds() >= RECOMPUTE_AFTER_S
        locked = c.execute("SELECT pg_try_advisory_xact_lock(hashtext('waitlist.public_stats')) AS ok").fetchone()
        if stale and locked is not None and locked["ok"]:  # one instance recomputes; the others serve the current row
            counted = c.execute("SELECT count(*) AS n FROM waitlist.signup WHERE status = 'confirmed'").fetchone()
            n = int(counted["n"]) if counted else 0
            shown = n >= DISPLAY_THRESHOLD
            floor = (n // DISPLAY_STEP) * DISPLAY_STEP if shown else None
            row = c.execute(
                """INSERT INTO waitlist.public_stats (id, shown, count_floor, computed_at) VALUES (1, %s, %s, now())
                   ON CONFLICT (id) DO UPDATE SET shown = EXCLUDED.shown, count_floor = EXCLUDED.count_floor,
                                                  computed_at = EXCLUDED.computed_at
                   RETURNING shown, count_floor, computed_at""",
                (shown, floor),
            ).fetchone()
    out: dict[str, Any] = {"shown": False}
    if row is not None and row["shown"] and row["count_floor"] is not None and row["count_floor"] >= DISPLAY_THRESHOLD:
        as_of = row["computed_at"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = {"shown": True, "count_floor": int(row["count_floor"]), "as_of": as_of}
    with _memo_lock:
        _memo = (now, dict(out))
    return out


def reset_memo() -> None:
    global _memo
    with _memo_lock:
        _memo = None


# ------------------------------------------------------------------ outbox delivery
@dataclass(frozen=True)
class _Job:
    id: uuid.UUID
    kind: str
    attempts: int
    message: Message | None


def process_outbox(
    pool: ConnectionPool[Conn],
    s: WaitlistSettings,
    sender: Sender,
    *,
    limit: int = 10,
    ids: list[uuid.UUID] | None = None,
    budget_s: float = 8.0,
) -> dict[str, int]:
    """Deliver due outbox rows. Safe to run concurrently (rows are claimed with SKIP LOCKED and a lease); a crash
    mid-send leaves a lease that expires, and the retry reuses the same Idempotency-Key for owner notifications."""
    stats = {"sent": 0, "retry": 0, "failed": 0, "deferred": 0}
    if isinstance(sender, DisabledSender):
        return stats  # nothing is claimed or attempted: rows wait, unchanged, until sending is enabled
    start = time.monotonic()
    for _ in range(limit):
        if time.monotonic() - start > budget_s:
            break
        job = _claim(pool, s, ids)
        if job is None:
            break
        if job.message is None:
            stats["deferred"] += 1
            continue
        res = sender.send(job.message)
        with transaction(pool) as c:
            if res.ok:
                c.execute(
                    """UPDATE waitlist.email_outbox SET status = 'sent', sent_at = now(), lease_until = NULL, last_error = NULL,
                              provider = %s, provider_message_id = %s, updated_at = now()
                       WHERE id = %s AND status = 'sending'""",
                    (res.provider, res.message_id, job.id),
                )
                stats["sent"] += 1
                log.info("waitlist.email_sent", extra={"kind": job.kind, "outbox_id": str(job.id)})
            elif res.retryable and job.attempts < MAX_ATTEMPTS:
                delay = BACKOFF_S[min(job.attempts - 1, len(BACKOFF_S) - 1)]
                c.execute(
                    """UPDATE waitlist.email_outbox SET status = 'pending', lease_until = NULL, updated_at = now(),
                              next_attempt_at = now() + make_interval(secs => %s), last_error = %s
                       WHERE id = %s AND status = 'sending'""",
                    (delay, sanitize_error(res.error or "unknown error"), job.id),
                )
                stats["retry"] += 1
                log.warning("waitlist.email_retry", extra={"kind": job.kind, "outbox_id": str(job.id), "attempt": job.attempts})
            else:
                c.execute(
                    """UPDATE waitlist.email_outbox SET status = 'failed', lease_until = NULL, updated_at = now(), last_error = %s
                       WHERE id = %s AND status = 'sending'""",
                    (sanitize_error(res.error or "unknown error"), job.id),
                )
                stats["failed"] += 1
                log.error("waitlist.email_failed", extra={"kind": job.kind, "outbox_id": str(job.id)})
    return stats


_CLAIM = """
WITH due AS (
    SELECT id FROM waitlist.email_outbox
    WHERE ((status = 'pending' AND next_attempt_at <= now()) OR (status = 'sending' AND lease_until < now()))
      AND (%(ids)s::uuid[] IS NULL OR id = ANY(%(ids)s::uuid[]))
    ORDER BY next_attempt_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE waitlist.email_outbox o
SET status = 'sending', lease_until = now() + interval '2 minutes', attempts = o.attempts + 1, updated_at = now()
FROM due WHERE o.id = due.id
RETURNING o.id, o.kind, o.signup_id, o.attempts, o.payload
"""


def _claim(pool: ConnectionPool[Conn], s: WaitlistSettings, ids: list[uuid.UUID] | None) -> _Job | None:
    secret = s.secret_bytes()
    site = s.site_url() or "http://localhost:8000"
    with transaction(pool) as c:
        o = c.execute(_CLAIM, {"ids": ids}).fetchone()
        if o is None:
            return None
        sig = c.execute(
            """SELECT id, email, status, created_at, confirmed_at, github_login, ci_failure_freq, updates_consent,
                      disposable_domain FROM waitlist.signup WHERE id = %s""",
            (o["signup_id"],),
        ).fetchone()
        # Tokens travel in the URL fragment: browsers never send it to a server, so it cannot reach request logs.
        unsub = f"{site}/unsubscribe/#token={unsubscribe_token(secret, o['signup_id'])}"
        headers = {"List-Unsubscribe": f"<{unsub}>"}
        if o["kind"] == "verify":
            if sig is None or sig["status"] == "confirmed":
                c.execute("UPDATE waitlist.email_outbox SET status = 'cancelled', lease_until = NULL WHERE id = %s", (o["id"],))
                return _Job(o["id"], o["kind"], o["attempts"], None)
            token = new_token()
            c.execute(
                """INSERT INTO waitlist.verify_token (token_hash, signup_id, expires_at)
                   VALUES (%s, %s, now() + make_interval(hours => %s))""",
                (token_hash(token), o["signup_id"], s.waitlist_verify_ttl_hours),
            )
            subject, text, html = templates.verification(
                f"{site}/confirm/#token={token}", unsub, s.waitlist_postal_address, s.waitlist_verify_ttl_hours
            )
            # A new token per attempt, so the key includes the attempt (Resend rejects a reused key with a new body).
            msg = Message(sig["email"], subject, text, html, f"verify-{o['id']}-{o['attempts']}", headers)
            return _Job(o["id"], o["kind"], o["attempts"], msg)
        # owner notification
        owner = s.waitlist_owner_notify_email
        if not owner:
            c.execute(
                """UPDATE waitlist.email_outbox SET status = 'pending', attempts = attempts - 1, lease_until = NULL,
                          next_attempt_at = now() + interval '1 hour', updated_at = now(),
                          last_error = 'WAITLIST_OWNER_NOTIFY_EMAIL is not set'
                   WHERE id = %s""",
                (o["id"],),
            )
            return _Job(o["id"], o["kind"], o["attempts"], None)
        payload = o["payload"]
        if payload is None:
            if sig is None:
                return _Job(o["id"], o["kind"], o["attempts"], None)
            payload = {
                "email": sig["email"],
                "created_at": _iso(sig["created_at"]),
                "confirmed_at": _iso(sig["confirmed_at"]),
                "github_login": sig["github_login"],
                "updates_consent": sig["updates_consent"],
                "ci_failure_freq": sig["ci_failure_freq"],
                "disposable_domain": sig["disposable_domain"],
            }
            # Snapshot on first attempt: every retry sends an identical body under the same Idempotency-Key.
            c.execute("UPDATE waitlist.email_outbox SET payload = %s WHERE id = %s", (Jsonb(payload), o["id"]))
        subject, text, html = templates.owner_notification(payload)
        return _Job(o["id"], o["kind"], o["attempts"], Message(owner, subject, text, html, f"owner-notify-{o['id']}"))


def _iso(v: datetime | None) -> str | None:
    return v.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S") if v else None


# ------------------------------------------------------------------ maintenance
def purge(pool: ConnectionPool[Conn]) -> dict[str, int]:
    """Retention: unconfirmed signups after 7 days; expired tokens and old rate-limit windows; old verify-email rows."""
    from tracewise.waitlist.ratelimit import purge as purge_rl

    with transaction(pool, statement_timeout_ms=20000) as c:
        signups = c.execute(
            "DELETE FROM waitlist.signup WHERE status = 'pending' AND created_at < now() - %s::interval", (UNVERIFIED_RETENTION,)
        ).rowcount
        tokens = c.execute("DELETE FROM waitlist.verify_token WHERE expires_at < now() - interval '7 days'").rowcount
        verify_rows = c.execute(
            "DELETE FROM waitlist.email_outbox WHERE kind = 'verify' AND status IN ('sent', 'cancelled') "
            "AND updated_at < now() - interval '30 days'"
        ).rowcount
        windows = purge_rl(c)
    return {"unconfirmed_signups": signups, "expired_tokens": tokens, "old_verify_emails": verify_rows, "rate_windows": windows}


def verify_turnstile(secret: str, token: str, remote_ip: str | None, client: outbound.HttpClient | None = None) -> bool:
    """Cloudflare Turnstile server-side check (only when WAITLIST_TURNSTILE_SECRET is set)."""
    form = {"secret": secret, "response": token}
    if remote_ip:
        form["remoteip"] = remote_ip
    r = outbound.verify_turnstile(form, client)
    return r.status == 200 and isinstance(r.body, dict) and r.body.get("success") is True
