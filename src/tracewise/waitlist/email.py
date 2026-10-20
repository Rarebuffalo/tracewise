"""Email delivery. Three modes, chosen by WAITLIST_EMAIL_MODE:

- `disabled` (default): nothing is sent and nothing is claimed as sent; outbox rows wait until sending is enabled.
- `file`: local testing only. Each message is written as JSON to WAITLIST_EMAIL_FILE_DIR (mode 0600).
- `resend`: the Resend HTTP API, with an Idempotency-Key per message so a retry after a timeout cannot duplicate.

Errors are reduced to a short, sanitised description (status code and provider error name); recipient addresses are
removed before anything is stored.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tracewise.waitlist.outbound import HttpClient, send_resend

_EMAILISH = re.compile(r"[^\s@<>\"']+@[^\s@<>\"']+")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    html: str
    idempotency_key: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider: str | None = None
    message_id: str | None = None
    error: str | None = None
    retryable: bool = True


class Sender(Protocol):
    name: str

    def send(self, m: Message) -> SendResult: ...


def sanitize_error(text: str) -> str:
    return _EMAILISH.sub("[address]", text)[:300]


class DisabledSender:
    name = "disabled"

    def send(self, m: Message) -> SendResult:
        return SendResult(ok=False, error="email sending is disabled (WAITLIST_EMAIL_MODE=disabled)", retryable=True)


class FileSender:
    """Local testing: writes the message where a developer can open it. Never used outside local/test."""

    name = "file"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def send(self, m: Message) -> SendResult:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = f"{time.time_ns()}-{re.sub(r'[^A-Za-z0-9_-]', '_', m.idempotency_key)[:80]}.json"
        path = self.directory / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                {
                    "to": m.to,
                    "subject": m.subject,
                    "text": m.text,
                    "html": m.html,
                    "headers": m.headers,
                    "idempotency_key": m.idempotency_key,
                },
                f,
                indent=1,
            )
        return SendResult(ok=True, provider="file", message_id=name)


class ResendSender:
    name = "resend"

    def __init__(self, api_key: str, sender: str, reply_to: str | None = None, client: HttpClient | None = None) -> None:
        self._key = api_key
        self._from = sender
        self._reply_to = reply_to
        self._client = client

    def send(self, m: Message) -> SendResult:
        body: dict[str, object] = {"from": self._from, "to": [m.to], "subject": m.subject, "text": m.text, "html": m.html}
        if m.headers:
            body["headers"] = m.headers
        if self._reply_to:
            body["reply_to"] = self._reply_to
        r = send_resend(self._key, body, m.idempotency_key, self._client)
        if r.status == 0:
            return SendResult(ok=False, error=f"network error: {r.network_error}", retryable=True)
        detail = r.body if isinstance(r.body, dict) else {}
        if 200 <= r.status < 300:
            mid = str(detail.get("id", ""))[:200] or None
            return SendResult(ok=True, provider="resend", message_id=mid)
        name, msg = str(detail.get("name", "")), str(detail.get("message", ""))
        # 429 (rate limit), 409 (idempotent request still in progress) and 5xx are temporary; other 4xx are not
        # (e.g. 403 unverified domain, 422 invalid recipient) and need an operator.
        retryable = r.status in (408, 409, 429) or r.status >= 500
        return SendResult(ok=False, error=sanitize_error(f"resend {r.status} {name}: {msg}".strip()), retryable=retryable)


def make_sender(mode: str, *, file_dir: Path, api_key: str | None, sender: str | None, reply_to: str | None) -> Sender:
    if mode == "file":
        return FileSender(file_dir)
    if mode == "resend" and api_key and sender:
        return ResendSender(api_key, sender, reply_to)
    return DisabledSender()
