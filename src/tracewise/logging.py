"""JSON logging with correlation IDs and secret scrubbing (T-102, FS-SEC-5).

Every record passes through `SecretFilter`, which replaces registered secret values
(installation tokens, configured keys) and token-shaped strings with `[REDACTED]`.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
from datetime import UTC, datetime
from typing import Any

correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# Token shapes that must never reach a log line, whether registered or not.
_TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
)
_URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@")


class SecretFilter(logging.Filter):
    """Scrubs registered secrets and token-shaped strings from records."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._secrets: set[str] = set()

    def register(self, value: str) -> None:
        if value and len(value) >= 6:
            with self._lock:
                self._secrets.add(value)

    def unregister(self, value: str) -> None:
        with self._lock:
            self._secrets.discard(value)

    def scrub(self, text: str) -> str:
        with self._lock:
            secrets = sorted(self._secrets, key=len, reverse=True)
        for s in secrets:
            text = text.replace(s, "[REDACTED]")
        text = _TOKEN_RE.sub("[REDACTED]", text)
        return _URL_CRED_RE.sub(r"\1[REDACTED]@", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.scrub(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = self.scrub(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        extra = getattr(record, "tw", None)
        if isinstance(extra, dict):
            record.tw = {k: self.scrub(v) if isinstance(v, str) else v for k, v in extra.items()}
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        extra = getattr(record, "tw", None)
        if isinstance(extra, dict):
            doc.update(extra)
        if record.exc_text:
            doc["exc"] = record.exc_text
        return json.dumps(doc, default=str)


secret_filter = SecretFilter()


def configure(level: int = logging.INFO, secrets: list[str] | None = None) -> None:
    for s in secrets or []:
        secret_filter.register(s)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(secret_filter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
