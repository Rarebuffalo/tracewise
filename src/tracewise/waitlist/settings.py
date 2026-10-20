"""Waitlist settings (environment only). Secrets are `SecretStr` so they never appear in repr, logs or errors.

Placeholders and descriptions: `web/.env.example`; operator guide: `web/docs/deployment.md`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EmailMode = Literal["disabled", "file", "resend"]


class WaitlistSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    waitlist_env: Literal["local", "test", "preview", "production"] = "local"
    # Runtime role (tracewise_waitlist): SELECT/INSERT/UPDATE/DELETE on schema `waitlist` only.
    waitlist_database_url: SecretStr | None = None
    # Owner role: migrations only (CLI), never used by the web process.
    waitlist_database_url_migrations: SecretStr | None = None
    # HMAC key for form tokens, follow-up receipts, unsubscribe links and rate-limit keys (≥ 32 chars, random).
    waitlist_secret: SecretStr | None = None
    # Base URL used in email links. Falls back to Vercel's production URL so links work before a custom domain.
    waitlist_public_site_url: str | None = None
    # Extra origins allowed to POST (same-origin requests are always allowed). Comma-separated https origins.
    waitlist_allowed_origins: str = ""
    # Behind a proxy that sets X-Forwarded-For, take the client IP from it. Automatic on Vercel (VERCEL=1).
    waitlist_trust_proxy_headers: bool = False

    waitlist_email_mode: EmailMode = "disabled"
    waitlist_email_file_dir: Path = Path(".waitlist-mail")
    resend_api_key: SecretStr | None = None
    waitlist_email_from: str | None = None  # e.g. "Tracewise <hello@updates.example.com>" on a verified domain
    waitlist_email_reply_to: str | None = None
    waitlist_owner_notify_email: str | None = None  # the owner/admin inbox for confirmed-signup notifications
    waitlist_postal_address: str | None = None  # shown in email footers when set (CAN-SPAM for commercial mail)

    # Vercel Cron sends "Authorization: Bearer $CRON_SECRET" to the outbox endpoint.
    cron_secret: SecretStr | None = Field(None, validation_alias=AliasChoices("CRON_SECRET", "WAITLIST_CRON_SECRET"))
    # Optional Cloudflare Turnstile (off unless set; the site must also be built with PUBLIC_TURNSTILE_SITE_KEY).
    waitlist_turnstile_secret: SecretStr | None = None

    waitlist_verify_ttl_hours: int = Field(48, ge=1, le=168)

    @field_validator("waitlist_public_site_url")
    @classmethod
    def _site_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.netloc or u.path not in ("", "/") or u.query or u.fragment:
            raise ValueError("WAITLIST_PUBLIC_SITE_URL must be an origin like https://example.com")
        return f"{u.scheme}://{u.netloc}"

    @model_validator(mode="after")
    def _consistent(self) -> WaitlistSettings:
        if self.waitlist_secret is not None and len(self.waitlist_secret.get_secret_value()) < 32:
            raise ValueError("WAITLIST_SECRET must be at least 32 characters of random data")
        if self.waitlist_email_mode == "resend" and not (self.resend_api_key and self.waitlist_email_from):
            raise ValueError("WAITLIST_EMAIL_MODE=resend requires RESEND_API_KEY and WAITLIST_EMAIL_FROM")
        if self.waitlist_env in ("preview", "production"):
            if self.waitlist_email_mode == "file":
                raise ValueError("WAITLIST_EMAIL_MODE=file is for local testing only")
            if self.waitlist_secret is None:
                raise ValueError("WAITLIST_SECRET is required outside local and test")
            site = self.site_url()
            if site is None or not site.startswith("https://"):
                raise ValueError("an https site URL is required outside local and test (WAITLIST_PUBLIC_SITE_URL)")
        return self

    def site_url(self) -> str | None:
        """Where email links point. Explicit setting first; on a Vercel preview deployment, that deployment's own URL
        (so a preview can be tested end to end); otherwise Vercel's production URL (system env vars)."""
        if self.waitlist_public_site_url:
            return self.waitlist_public_site_url
        if os.environ.get("VERCEL_ENV") == "preview" and os.environ.get("VERCEL_URL"):
            return f"https://{os.environ['VERCEL_URL']}"
        vercel = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        return f"https://{vercel}" if vercel else None

    def signup_block_reason(self) -> str | None:
        """Why new signups must be refused right now (None: they may be accepted).

        A signup is only worth accepting if its confirmation email can actually be sent, and, outside local/test,
        if the owner will hear about it. Otherwise the page would promise an email that never comes."""
        if self.waitlist_email_mode == "disabled":
            return "WAITLIST_EMAIL_MODE is disabled"
        if self.waitlist_env in ("preview", "production") and not self.waitlist_owner_notify_email:
            return "WAITLIST_OWNER_NOTIFY_EMAIL is not set"
        return None

    def trust_proxy(self) -> bool:
        """On Vercel the platform sets the client-IP headers itself, so they are trusted there automatically."""
        return self.waitlist_trust_proxy_headers or os.environ.get("VERCEL") == "1"

    def allowed_origins(self) -> set[str]:
        return {o.strip().rstrip("/") for o in self.waitlist_allowed_origins.split(",") if o.strip()}

    def secret_bytes(self) -> bytes:
        if self.waitlist_secret is None:
            if self.waitlist_env in ("local", "test"):
                return b"local-development-secret-not-for-production-use!!"
            raise RuntimeError("WAITLIST_SECRET is not configured")
        return self.waitlist_secret.get_secret_value().encode()

    def secret_values(self) -> list[str]:
        out = []
        for s in (
            self.waitlist_database_url,
            self.waitlist_database_url_migrations,
            self.waitlist_secret,
            self.resend_api_key,
            self.cron_secret,
            self.waitlist_turnstile_secret,
        ):
            if s is not None and s.get_secret_value():
                out.append(s.get_secret_value())
        return out


@lru_cache(maxsize=1)
def get_settings() -> WaitlistSettings:
    return WaitlistSettings()
