"""Fixed-window rate limits stored in Postgres, so they hold across serverless instances and processes.

Keys are HMACs of the client IP or the email (see `security.key_hash`); raw values are never stored. A hit is
recorded in its own short transaction, so a failing request still counts.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from tracewise.waitlist.db import Conn, transaction
from tracewise.waitlist.security import key_hash


@dataclass(frozen=True)
class Limit:
    bucket: str
    limit: int
    window_s: int


# Generous for people, tight for scripts. Signup limits are enforced silently (the response is the same).
SIGNUP_PER_IP = Limit("signup_ip", 20, 3600)
SIGNUP_PER_EMAIL = Limit("signup_email", 5, 86400)
FORM_PER_IP = Limit("form_ip", 120, 3600)
CONFIRM_PER_IP = Limit("confirm_ip", 30, 3600)
PROFILE_PER_IP = Limit("profile_ip", 30, 3600)
UNSUBSCRIBE_PER_IP = Limit("unsubscribe_ip", 30, 3600)

_HIT = """
INSERT INTO waitlist.rate_limit (bucket, key_hash, window_start, hits)
VALUES (%(bucket)s, %(key)s,
        to_timestamp(floor(extract(epoch FROM now()) / %(w)s) * %(w)s), 1)
ON CONFLICT (bucket, key_hash, window_start) DO UPDATE SET hits = waitlist.rate_limit.hits + 1
RETURNING hits
"""


def hit(pool: ConnectionPool[Conn], secret: bytes, lim: Limit, value: str) -> bool:
    """Record one hit; True if still within the limit."""
    with transaction(pool) as conn:
        row = conn.execute(_HIT, {"bucket": lim.bucket, "key": key_hash(secret, lim.bucket, value), "w": lim.window_s}).fetchone()
    assert row is not None
    return int(row["hits"]) <= lim.limit


def purge(conn: Conn) -> int:
    """Drop windows older than two days (the longest window is one day)."""
    return conn.execute("DELETE FROM waitlist.rate_limit WHERE window_start < now() - interval '2 days'").rowcount
