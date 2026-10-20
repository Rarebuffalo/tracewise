"""The waitlist's only network module. It reaches exactly two fixed endpoints, never follows redirects, and returns
plain values so no other waitlist module needs an HTTP library:

- Resend's send-email API (`WAITLIST_EMAIL_MODE=resend`);
- Cloudflare Turnstile's verification API (only when `WAITLIST_TURNSTILE_SECRET` is set).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

RESEND_URL = "https://api.resend.com/emails"
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
HttpClient = httpx.Client


@dataclass(frozen=True)
class Reply:
    status: int  # 0 when no HTTP answer arrived
    body: Any  # parsed JSON, or None
    network_error: str | None = None  # exception class name when status == 0


def _post(url: str, client: HttpClient | None, timeout: float, **kw: Any) -> Reply:
    try:
        if client is not None:
            r = client.post(url, timeout=timeout, follow_redirects=False, **kw)
        else:
            with httpx.Client(timeout=timeout, follow_redirects=False) as c:
                r = c.post(url, **kw)
    except httpx.HTTPError as e:
        return Reply(0, None, type(e).__name__)
    try:
        body = r.json()
    except ValueError:
        body = None
    return Reply(r.status_code, body)


def send_resend(api_key: str, payload: dict[str, object], idempotency_key: str, client: HttpClient | None = None) -> Reply:
    headers = {"Authorization": f"Bearer {api_key}", "Idempotency-Key": idempotency_key[:256], "Content-Type": "application/json"}
    return _post(RESEND_URL, client, 10.0, json=payload, headers=headers)


def verify_turnstile(form: dict[str, str], client: HttpClient | None = None) -> Reply:
    return _post(TURNSTILE_URL, client, 8.0, data=form)
