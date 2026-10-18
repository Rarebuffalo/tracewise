"""GitHub-shaped job logs and jobs-API documents with fixed timestamps (T-601).

Wraps raw tool output in the runner's envelope (timestamps, `##[group]Run …`, post steps), the same
shape the product parses. Timestamps are fixed so results are reproducible.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

T0 = datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC)


def _ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}0Z"


def _iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def job_document(job_id: int, name: str, step: str, *, conclusion: str = "failure", run_attempt: int = 1) -> dict[str, Any]:
    s1, s2, s3, s4 = T0, T0 + timedelta(seconds=2), T0 + timedelta(seconds=4), T0 + timedelta(seconds=16)

    def st(n: int, nm: str, a: datetime, b: datetime, c: str) -> dict[str, Any]:
        return {"name": nm, "number": n, "status": "completed", "conclusion": c, "started_at": _iso(a), "completed_at": _iso(b)}

    return {
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "run_attempt": run_attempt,
        "status": "completed",
        "started_at": _iso(T0),
        "completed_at": _iso(s4 + timedelta(seconds=1)),
        "steps": [
            st(1, "Set up job", s1, s1 + timedelta(seconds=1), "success"),
            st(2, "Checkout", s2, s2 + timedelta(seconds=1), "success"),
            st(3, step, s3, s3 + timedelta(seconds=10), conclusion),
            st(4, "Post Run actions/checkout@v4", s4, s4 + timedelta(seconds=1), "success"),
        ],
    }


def envelope_lines(
    command: str, output: str, *, failed: bool = True, timed_out: bool = False, exit_code: int = 1
) -> Iterator[str]:
    s1, s2, s3, s4 = T0, T0 + timedelta(seconds=2), T0 + timedelta(seconds=4), T0 + timedelta(seconds=16)
    yield f"{_ts(s1 + timedelta(milliseconds=10))} Current runner version: '2.320.0'"
    yield f"{_ts(s2 + timedelta(milliseconds=10))} ##[group]Run actions/checkout@v4"
    yield f"{_ts(s2 + timedelta(milliseconds=20))} ##[endgroup]"
    yield f"{_ts(s3 + timedelta(milliseconds=1))} ##[group]Run {command}"
    yield f"{_ts(s3 + timedelta(milliseconds=2))} {command}"
    yield f"{_ts(s3 + timedelta(milliseconds=3))} shell: /usr/bin/bash -e {{0}}"
    yield f"{_ts(s3 + timedelta(milliseconds=4))} ##[endgroup]"
    lines = output.splitlines()
    step = timedelta(seconds=9) / max(1, len(lines) + 1)
    for i, text in enumerate(lines):
        yield f"{_ts(s3 + timedelta(milliseconds=5) + step * i)} {text}"
    if failed and not timed_out:
        yield f"{_ts(s3 + timedelta(seconds=9, milliseconds=900))} ##[error]Process completed with exit code {exit_code}."
    yield f"{_ts(s4 + timedelta(milliseconds=10))} Post job cleanup."
