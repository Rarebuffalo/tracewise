"""Validation, normalisation, tokens and HMAC helpers. Nothing here touches the database or the network."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import uuid
from typing import Literal

MAX_EMAIL = 254
# WHATWG `input type=email` grammar (the same rule the browser applies), plus: the domain must contain a dot.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_GITHUB_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
CiFrequency = Literal["daily", "weekly", "monthly", "rarely"]
CI_FREQUENCIES: tuple[str, ...] = ("daily", "weekly", "monthly", "rarely")

# A small, conservative list of well-known disposable-mail domains. Signups from them are *flagged*, not blocked
# (OWASP: risk-based handling); flagged signups are deprioritised for pilot invites.
DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "sharklasers.com",
        "grr.la",
        "10minutemail.com",
        "10minutemail.net",
        "temp-mail.org",
        "tempmail.com",
        "tempmail.net",
        "yopmail.com",
        "yopmail.net",
        "trashmail.com",
        "getnada.com",
        "dispostable.com",
        "maildrop.cc",
        "throwawaymail.com",
        "fakeinbox.com",
        "mailnesia.com",
        "mintemail.com",
        "mohmal.com",
        "emailondeck.com",
        "burnermail.io",
        "tempr.email",
        "discard.email",
        "spamgourmet.com",
        "mailcatch.com",
        "moakt.com",
        "tmail.ws",
        "mytemp.email",
    }
)


def normalize_email(raw: str) -> str | None:
    """Trimmed, lower-cased address if it is valid, else None. No provider-specific rewriting (dots, +tags)."""
    s = raw.strip()
    if not s or len(s) > MAX_EMAIL or not _EMAIL_RE.fullmatch(s):
        return None
    return s.lower()


def is_disposable(email_normalized: str) -> bool:
    return email_normalized.rsplit("@", 1)[1] in DISPOSABLE_DOMAINS


def normalize_github(raw: str | None) -> str | None:
    """A valid GitHub username (a leading @ or a profile URL is accepted and stripped), '' → None; ValueError if invalid."""
    if raw is None:
        return None
    s = raw.strip()
    for prefix in ("https://github.com/", "http://github.com/", "github.com/", "@"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
    s = s.strip("/")
    if s == "":
        return None
    if not _GITHUB_RE.fullmatch(s):
        raise ValueError("invalid GitHub username")
    return s


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _mac(secret: bytes, *parts: str) -> str:
    return hmac.new(secret, "|".join(parts).encode(), hashlib.sha256).hexdigest()


def key_hash(secret: bytes, bucket: str, value: str) -> bytes:
    """Keyed hash for rate-limit keys: raw IPs and emails are never stored."""
    return hmac.new(secret, f"rl|{bucket}|{value}".encode(), hashlib.sha256).digest()[:16]


# ---- form token: proves the form was rendered by a browser a moment ago (time-to-submit check)
FORM_MIN_AGE_S = 2.0
FORM_MAX_AGE_S = 2 * 3600.0


def issue_form_token(secret: bytes, now: float | None = None) -> str:
    ts = str(int((now or time.time()) * 1000))  # milliseconds; no "." so the token splits cleanly
    nonce = secrets.token_hex(8)
    return f"{ts}.{nonce}.{_mac(secret, 'form', ts, nonce)[:32]}"


def check_form_token(secret: bytes, token: str | None, now: float | None = None) -> Literal["ok", "too_fast", "invalid"]:
    if not token or token.count(".") != 2:
        return "invalid"
    ts, nonce, sig = token.split(".")
    if not hmac.compare_digest(sig, _mac(secret, "form", ts, nonce)[:32]):
        return "invalid"
    try:
        age = (now or time.time()) - int(ts) / 1000
    except ValueError:
        return "invalid"
    if age < 0 or age > FORM_MAX_AGE_S:
        return "invalid"
    return "too_fast" if age < FORM_MIN_AGE_S else "ok"


# ---- follow-up receipt: lets the person who just signed up (or just confirmed) answer one optional question
RECEIPT_TTL_S = 24 * 3600


def issue_receipt(secret: bytes, signup_id: uuid.UUID, now: float | None = None) -> str:
    exp = str(int((now or time.time()) + RECEIPT_TTL_S))
    return f"{signup_id}.{exp}.{_mac(secret, 'receipt', str(signup_id), exp)[:40]}"


def decoy_receipt(now: float | None = None) -> str:
    """Same shape as a real receipt; matches nothing (returned when the email was already on the list)."""
    exp = str(int((now or time.time()) + RECEIPT_TTL_S))
    return f"{uuid.uuid4()}.{exp}.{secrets.token_hex(20)}"


def check_receipt(secret: bytes, receipt: str, now: float | None = None) -> uuid.UUID | None:
    parts = receipt.split(".")
    if len(parts) != 3:
        return None
    sid, exp, sig = parts
    if not hmac.compare_digest(sig, _mac(secret, "receipt", sid, exp)[:40]):
        return None
    try:
        if int(exp) < (now or time.time()):
            return None
        return uuid.UUID(sid)
    except ValueError:
        return None


# ---- unsubscribe link: derived, so every email can carry one without storing a token
def unsubscribe_token(secret: bytes, signup_id: uuid.UUID) -> str:
    return f"{signup_id}.{_mac(secret, 'unsubscribe', str(signup_id))[:40]}"


def check_unsubscribe_token(secret: bytes, token: str) -> uuid.UUID | None:
    parts = token.split(".")
    if len(parts) != 2:
        return None
    try:
        sid = uuid.UUID(parts[0])
    except ValueError:
        return None
    return sid if hmac.compare_digest(parts[1], _mac(secret, "unsubscribe", str(sid))[:40]) else None
