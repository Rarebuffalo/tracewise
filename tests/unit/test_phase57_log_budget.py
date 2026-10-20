"""Phase 57: a log download has a total wall-clock budget. httpx's read timeout applies per read, so a server
trickling bytes could hold a worker (and its graceful shutdown) indefinitely. At the budget the log is kept so far
and flagged truncated, exactly like the byte cap. Found by an offline audit, reproduced first."""

from __future__ import annotations

from typing import Any

import httpx

from tests.unit.test_github_client import setup


def test_a_trickling_log_stops_at_its_time_budget_and_is_flagged_incomplete() -> None:
    """A server that keeps sending a little at a time never trips httpx's per-read timeout. The download now has a
    total budget; when it runs out the log is treated like the byte cap: kept so far, flagged truncated."""
    from tests.unit.test_github_client import BLOB, LOGS

    now = {"t": 0.0}

    def tick() -> float:
        now["t"] += 1.0  # each chunk "takes" one second
        return now["t"]

    gh, rc = setup(max_log_seconds=10.0)
    rc.http._monotonic = tick
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))

    def trickle() -> Any:
        for i in range(1000):
            yield f"line {i}\n".encode()

    gh.route("GET", r"^//productionresultssa1", lambda r: httpx.Response(200, content=trickle()))
    lines = rc.job_log_lines(99)
    got = list(lines)
    assert lines.truncated and 0 < len(got) < 20  # stopped near 10 "seconds", far before the 1000 lines


def test_a_log_within_its_time_budget_is_complete() -> None:
    from tests.unit.test_github_client import BLOB, LOGS

    gh, rc = setup()
    gh.route("GET", LOGS, httpx.Response(302, headers={"location": BLOB}))
    gh.route("GET", r"^//productionresultssa1", httpx.Response(200, text="a\nb\nc"))
    lines = rc.job_log_lines(99)
    assert list(lines) == ["a", "b", "c"] and not lines.truncated
