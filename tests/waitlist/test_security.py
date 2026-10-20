"""Pure helpers: normalisation, tokens, receipts. No database."""

from __future__ import annotations

import time
import uuid

import pytest

from tracewise.waitlist import security as sec

SECRET = b"s" * 48


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ada@Example.COM", "ada@example.com"),
        ("  ada@example.com\t", "ada@example.com"),
        ("first.last+ci@sub.example.org", "first.last+ci@sub.example.org"),
    ],
)
def test_normalize_email_accepts_and_lowercases(raw: str, expected: str) -> None:
    assert sec.normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "ada",
        "ada@",
        "@example.com",
        "ada@localhost",
        "ada@@example.com",
        "a da@example.com",
        "ada@example.com\nBcc: x@y.com",
        "<ada@example.com>",
        "a@" + "x" * 250 + ".com",
    ],
)
def test_normalize_email_rejects(raw: str) -> None:
    assert sec.normalize_email(raw) is None


def test_disposable_flag() -> None:
    assert sec.is_disposable("x@mailinator.com")
    assert not sec.is_disposable("x@example.com")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("octocat", "octocat"),
        ("@octocat", "octocat"),
        ("https://github.com/octo-cat/", "octo-cat"),
    ],
)
def test_normalize_github(raw: str | None, expected: str | None) -> None:
    assert sec.normalize_github(raw) == expected


@pytest.mark.parametrize("raw", ["-bad", "bad-", "a--b", "x" * 40, "has space", "<script>", "a/b"])
def test_normalize_github_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        sec.normalize_github(raw)


def test_tokens_are_random_and_only_hash_is_32_bytes() -> None:
    a, b = sec.new_token(), sec.new_token()
    assert a != b and len(a) >= 43
    assert len(sec.token_hash(a)) == 32 and sec.token_hash(a) != sec.token_hash(b)


def test_form_token_timing() -> None:
    now = time.time()
    t = sec.issue_form_token(SECRET, now=now)
    assert sec.check_form_token(SECRET, t, now=now + 0.5) == "too_fast"
    assert sec.check_form_token(SECRET, t, now=now + 5) == "ok"
    assert sec.check_form_token(SECRET, t, now=now + 3 * 3600) == "invalid"
    assert sec.check_form_token(b"other" * 10, t, now=now + 5) == "invalid"
    assert sec.check_form_token(SECRET, t[:-1] + ("0" if t[-1] != "0" else "1"), now=now + 5) == "invalid"
    assert sec.check_form_token(SECRET, None) == "invalid"
    assert sec.check_form_token(SECRET, "a.b.c") == "invalid"


def test_receipt_roundtrip_expiry_and_tamper() -> None:
    sid = uuid.uuid4()
    r = sec.issue_receipt(SECRET, sid)
    assert sec.check_receipt(SECRET, r) == sid
    assert sec.check_receipt(SECRET, r, now=time.time() + 25 * 3600) is None
    other = uuid.uuid4()
    forged = f"{other}." + r.split(".", 1)[1]
    assert sec.check_receipt(SECRET, forged) is None
    assert sec.check_receipt(SECRET, sec.decoy_receipt()) is None
    assert sec.check_receipt(SECRET, "garbage") is None


def test_decoy_receipt_has_same_shape() -> None:
    real = sec.issue_receipt(SECRET, uuid.uuid4())
    decoy = sec.decoy_receipt()
    assert [len(p) for p in real.split(".")] == [len(p) for p in decoy.split(".")]


def test_unsubscribe_token() -> None:
    sid = uuid.uuid4()
    t = sec.unsubscribe_token(SECRET, sid)
    assert sec.check_unsubscribe_token(SECRET, t) == sid
    assert sec.check_unsubscribe_token(SECRET, f"{uuid.uuid4()}.{t.split('.')[1]}") is None
    assert sec.check_unsubscribe_token(b"x" * 40, t) is None
    assert sec.check_unsubscribe_token(SECRET, "not-a-uuid.abc") is None


def test_rate_limit_keys_hide_raw_values() -> None:
    k = sec.key_hash(SECRET, "signup_ip", "203.0.113.9")
    assert len(k) == 16 and b"203.0.113.9" not in k
    assert k != sec.key_hash(SECRET, "signup_email", "203.0.113.9")
