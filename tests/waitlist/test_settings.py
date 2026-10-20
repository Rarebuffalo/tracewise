"""Configuration rules: nothing unsafe is accepted outside local/test, and secrets never print."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tracewise.waitlist.settings import WaitlistSettings


def make(**kw: object) -> WaitlistSettings:
    return WaitlistSettings(**kw)  # type: ignore[arg-type]


def test_defaults_are_safe() -> None:
    s = make()
    assert s.waitlist_email_mode == "disabled"
    assert s.waitlist_owner_notify_email is None  # never a built-in recipient
    assert s.waitlist_env == "local"


def test_production_requires_secret_and_https_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    with pytest.raises(ValidationError):
        make(waitlist_env="production")
    with pytest.raises(ValidationError):
        make(waitlist_env="production", waitlist_secret="x" * 40, waitlist_public_site_url="http://insecure.example")
    ok = make(waitlist_env="production", waitlist_secret="x" * 40, waitlist_public_site_url="https://example.com/")
    assert ok.site_url() == "https://example.com"


def test_production_falls_back_to_vercel_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "tracewise-abc.vercel.app")
    s = make(waitlist_env="production", waitlist_secret="x" * 40)
    assert s.site_url() == "https://tracewise-abc.vercel.app"


def test_file_mode_forbidden_outside_local() -> None:
    with pytest.raises(ValidationError):
        make(
            waitlist_env="preview",
            waitlist_secret="x" * 40,
            waitlist_public_site_url="https://p.example",
            waitlist_email_mode="file",
        )


def test_resend_mode_needs_key_and_from() -> None:
    with pytest.raises(ValidationError):
        make(waitlist_email_mode="resend")
    with pytest.raises(ValidationError):
        make(waitlist_email_mode="resend", resend_api_key="re_x")


def test_short_secret_rejected() -> None:
    with pytest.raises(ValidationError):
        make(waitlist_secret="short")


def test_site_url_must_be_an_origin() -> None:
    with pytest.raises(ValidationError):
        make(waitlist_public_site_url="https://example.com/path")
    with pytest.raises(ValidationError):
        make(waitlist_public_site_url="javascript:alert(1)")


def test_secret_bytes_requires_real_secret_outside_local() -> None:
    s = make(waitlist_env="production", waitlist_secret="y" * 40, waitlist_public_site_url="https://e.example")
    assert s.secret_bytes() == b"y" * 40


def test_secrets_are_not_in_repr() -> None:
    s = make(
        waitlist_secret="z" * 40,
        resend_api_key="re_supersecretvalue",
        cron_secret="c" * 40,
        waitlist_database_url="postgresql://u:pw-secret@h/db",
    )
    text = repr(s) + str(s) + str(s.model_dump())
    for secret in ("z" * 40, "re_supersecretvalue", "c" * 40, "pw-secret"):
        assert secret not in text


def test_signup_block_reason() -> None:
    assert make().signup_block_reason() == "WAITLIST_EMAIL_MODE is disabled"
    assert make(waitlist_email_mode="file").signup_block_reason() is None  # local
    prod = {
        "waitlist_env": "production",
        "waitlist_secret": "x" * 40,
        "waitlist_public_site_url": "https://e.example",
        "waitlist_email_mode": "resend",
        "resend_api_key": "re_x",
        "waitlist_email_from": "a@e.example",
    }
    assert make(**prod).signup_block_reason() == "WAITLIST_OWNER_NOTIFY_EMAIL is not set"
    assert make(**prod, waitlist_owner_notify_email="o@e.example").signup_block_reason() is None


def test_preview_deployments_link_to_themselves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "tw.vercel.app")
    monkeypatch.setenv("VERCEL_URL", "tw-git-branch-abc.vercel.app")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    assert make().site_url() == "https://tw-git-branch-abc.vercel.app"
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert make().site_url() == "https://tw.vercel.app"
    assert make(waitlist_public_site_url="https://www.example.com").site_url() == "https://www.example.com"
