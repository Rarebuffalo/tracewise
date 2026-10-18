"""Offline GitHub REST replay for one benchmark case (T-601).

An `httpx.MockTransport` serving exactly what the analysis path reads: the installation-token mint,
jobs for the run attempt, the job-log redirect and blob, the commit, and the compare. Everything comes
from the case fixture; nothing leaves the process.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import httpx

BLOB_HOST = "productionresultssa0.blob.core.windows.net"


def _j(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers or {})


def replay_transport(
    *,
    repo: str,
    token: str,
    run_id: int,
    jobs: list[dict[str, Any]],
    logs: dict[int, str],
    commits: dict[str, list[str]],
    compares: dict[str, list[dict[str, Any]]],
    on_request: Callable[[httpx.Request], None] | None = None,
) -> httpx.MockTransport:
    r = re.escape(repo)
    routes: list[tuple[str, re.Pattern[str], Callable[[httpx.Request, re.Match[str]], httpx.Response]]] = [
        (
            "POST",
            re.compile(r"^/app/installations/(\d+)/access_tokens$"),
            lambda q, m: _j(
                201,
                {
                    "token": token,
                    "expires_at": "2099-01-01T00:00:00Z",
                    "repository_selection": "selected",
                    "permissions": json.loads(q.content)["permissions"],
                    "repositories": [{"id": i} for i in json.loads(q.content)["repository_ids"]],
                },
            ),
        ),
        (
            "GET",
            re.compile(rf"^/repos/{r}/actions/runs/{run_id}/attempts/\d+/jobs$"),
            lambda q, m: _j(200, {"total_count": len(jobs), "jobs": jobs}),
        ),
        (
            "GET",
            re.compile(rf"^/repos/{r}/actions/jobs/(\d+)/logs$"),
            lambda q, m: (
                httpx.Response(302, headers={"location": f"https://{BLOB_HOST}/logs/{m.group(1)}.txt?sig=bench"})
                if int(m.group(1)) in logs
                else _j(404, {"message": "Not Found"})
            ),
        ),
        (
            "GET",
            re.compile(r"^//" + re.escape(BLOB_HOST) + r"/logs/(\d+)\.txt$"),
            lambda q, m: httpx.Response(200, text=logs[int(m.group(1))]),
        ),
        (
            "GET",
            re.compile(rf"^/repos/{r}/commits/([0-9a-f]{{40}})$"),
            lambda q, m: (
                _j(200, {"sha": m.group(1), "parents": [{"sha": p} for p in commits.get(m.group(1), [])]})
                if m.group(1) in commits
                else _j(404, {"message": "Not Found"})
            ),
        ),
        (
            "GET",
            re.compile(rf"^/repos/{r}/compare/([0-9a-f]{{40}})\.\.\.([0-9a-f]{{40}})$"),
            lambda q, m: (
                _j(200, {"total_commits": 1, "files": compares[f"{m.group(1)}...{m.group(2)}"]})
                if f"{m.group(1)}...{m.group(2)}" in compares
                else _j(404, {"message": "Not Found"})
            ),
        ),
    ]

    def handle(req: httpx.Request) -> httpx.Response:
        if on_request:
            on_request(req)
        target = req.url.path if req.url.host == "api.github.com" else f"//{req.url.host}{req.url.path}"
        for method, pat, fn in routes:
            m = pat.search(target)
            if method == req.method and m:
                return fn(req, m)
        return _j(404, {"message": "Not Found (replay)"})

    return httpx.MockTransport(handle)
