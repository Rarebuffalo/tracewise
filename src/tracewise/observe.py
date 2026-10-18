"""Operational events (T-706; FS-OPS-1). Stable names, bound correlation ids, sanitised fields.

`event(log, "job.failed", job_id=..., new_status=...)` emits one structured record. The JSON log line
(`tracewise.logging.JsonFormatter`) carries `event`, the fields, and every correlation id bound with
`bind(...)` (delivery_id, job_id, installation_id, repo_id, run_id, attempt).

Fields are restricted to scalars (and short lists of scalars). Keys that could carry credentials or content
are dropped, never logged: see `_DENY` (matched per word). Strings are truncated, and the logging `SecretFilter` still scrubs
token shapes and registered secrets. Emitting never raises: an instrumentation fault is counted in
`dropped_events` and the caller's processing continues.
"""

from __future__ import annotations

import contextvars
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_ids: contextvars.ContextVar[dict[str, int | str]] = contextvars.ContextVar("tw_ids", default={})  # noqa: B039 - never mutated

ID_KEYS = frozenset({"delivery_id", "job_id", "installation_id", "repo_id", "run_id", "attempt"})
# Field names are split on "_" and dropped if any word is in this set (so `tokens_in` is kept, `api_token` is not).
_DENY = frozenset(
    "authorization auth bearer token secret password passwd credential credentials cookie signature sig private key apikey "
    "jwt pem url uri urls href header headers body payload content contents source patch diff excerpt message msg prompt "
    "text raw".split()
)
_EVENT = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_STR = 200
MAX_LIST = 20

dropped_events = 0


def current_ids() -> dict[str, int | str]:
    return dict(_ids.get())


@contextmanager
def bind(**ids: int | str | None) -> Iterator[None]:
    """Bind correlation ids for log records emitted in this context (thread/async-task local)."""
    clean = {k: v for k, v in ids.items() if k in ID_KEYS and isinstance(v, int | str) and not isinstance(v, bool)}
    token = _ids.set({**_ids.get(), **{k: (v[:MAX_STR] if isinstance(v, str) else v) for k, v in clean.items()}})
    try:
        yield
    finally:
        _ids.reset(token)


def _denied(key: object) -> bool:
    return not isinstance(key, str) or any(w in _DENY for w in key.lower().split("_"))


def _scalar(v: Any) -> Any:
    if v is None or isinstance(v, bool | int | float):
        return v
    if isinstance(v, str):
        return v[:MAX_STR]
    return _DROP


_DROP = object()


def sanitize(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if _denied(k):
            continue
        if isinstance(v, list | tuple | set | frozenset):
            items = [_scalar(x) for x in list(v)[:MAX_LIST]]
            if all(x is not _DROP for x in items):
                out[k] = items
            continue
        if isinstance(v, dict):
            sub = {sk: _scalar(sv) for sk, sv in v.items() if not _denied(sk)}
            out[k] = {sk: sv for sk, sv in list(sub.items())[:MAX_LIST] if sv is not _DROP}
            continue
        s = _scalar(v)
        if s is not _DROP:
            out[k] = s
    return out


def event(logger: logging.Logger, name: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one operational event. Never raises."""
    global dropped_events
    try:
        if not _EVENT.match(name):
            raise ValueError("invalid event name")
        fields.pop("event", None)  # reserved for the event name
        logger.log(level, name, extra={"tw": {**current_ids(), **sanitize(fields), "event": name}})
    except Exception:
        dropped_events += 1


class Stages:
    """Wall-clock stage timings in milliseconds (monotonic clock)."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self.clock = clock
        self.ms: dict[str, int] = {}

    @contextmanager
    def time(self, stage: str) -> Iterator[None]:
        t0 = self.clock()
        try:
            yield
        finally:
            self.ms[stage] = self.ms.get(stage, 0) + max(0, int((self.clock() - t0) * 1000))
