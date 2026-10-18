"""Stateful fake of GitHub's publication API on top of FakeGitHub (offline).

Holds commit comments, issue (PR) comments and check runs for one repository, attributes writes to
our App (or to a person for spoofing tests), counts every external write, and injects faults:
  "accept_then_timeout"  apply the write, then raise ReadTimeout (response lost)
  "timeout"              raise ReadTimeout without applying
  403 / 404 / 422 / 5xx  return that status without applying
  "rate_limit"           403 with x-ratelimit-remaining 0 and reset +60 s
Faults are queued per (method, kind) and consumed in order.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx

from tests.github_fake import FakeGitHub, jresp

APP_ID = 123


@dataclass
class GitHubState:
    gh: FakeGitHub
    repo: str = "acme/coffee"
    app_id: int = APP_ID
    commit_comments: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    pr_comments: dict[int, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    check_runs: list[dict[str, Any]] = field(default_factory=list)
    commit_pulls: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    head_pulls: list[dict[str, Any]] = field(default_factory=list)
    faults: dict[tuple[str, str], list[Any]] = field(default_factory=lambda: defaultdict(list))
    writes: list[tuple[str, str]] = field(default_factory=list)
    _next_id: int = 1000

    def install(self) -> GitHubState:
        r = re.escape(self.repo)
        self.gh.route("GET", rf"^/repos/{r}/commits/[0-9a-f]{{40}}/comments$", self._list_cc)
        self.gh.route("POST", rf"^/repos/{r}/commits/[0-9a-f]{{40}}/comments$", self._create_cc)
        self.gh.route("GET", rf"^/repos/{r}/issues/\d+/comments$", self._list_prc)
        self.gh.route("POST", rf"^/repos/{r}/issues/\d+/comments$", self._create_prc)
        self.gh.route("PATCH", rf"^/repos/{r}/issues/comments/\d+$", self._update_prc)
        self.gh.route("GET", rf"^/repos/{r}/commits/[0-9a-f]{{40}}/check-runs$", self._list_cr)
        self.gh.route("POST", rf"^/repos/{r}/check-runs$", self._create_cr)
        self.gh.route("PATCH", rf"^/repos/{r}/check-runs/\d+$", self._update_cr)
        self.gh.route(
            "GET",
            rf"^/repos/{r}/commits/[0-9a-f]{{40}}/pulls$",
            lambda req: jresp(200, self.commit_pulls.get(req.url.path.split("/")[-2], [])),
        )
        self.gh.route("GET", rf"^/repos/{r}/pulls$", lambda req: jresp(200, self.head_pulls))
        return self

    # ------------------------------------------------------------ helpers for tests

    def fault(self, method: str, kind: str, *actions: Any) -> None:
        self.faults[(method, kind)].extend(actions)

    def pr(self, number: int, head_sha: str, repo_id: int = 7, state: str = "open") -> dict[str, Any]:
        return {
            "number": number,
            "state": state,
            "head": {"sha": head_sha, "ref": "feature"},
            "base": {"repo": {"id": repo_id, "full_name": self.repo}},
        }

    def count(self, method: str, kind: str) -> int:
        return sum(1 for w in self.writes if w == (method, kind))

    def ours(self, objs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [o for o in objs if (o.get("performed_via_github_app") or o.get("app") or {}).get("id") == self.app_id]

    # ------------------------------------------------------------ fault plumbing

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _pre(self, req: httpx.Request, kind: str) -> tuple[httpx.Response | None, bool]:
        """Returns (early response, lose_response_after_apply)."""
        q = self.faults.get((req.method, kind))
        if not q:
            return None, False
        action = q.pop(0)
        if action == "timeout":
            raise httpx.ReadTimeout("timeout", request=req)
        if action == "accept_then_timeout":
            return None, True
        if action == "rate_limit":
            return jresp(
                403,
                {"message": "API rate limit exceeded"},
                {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(self.gh.now) + 60)},
            ), False
        if action == 403:
            return jresp(
                403,
                {"message": "Resource not accessible by integration"},
                {"x-accepted-github-permissions": "pull_requests=write" if "pr" in kind else "checks=write"},
            ), False
        return jresp(int(action), {"message": "fault"}), False

    def _write(self, req: httpx.Request, kind: str, apply: Any) -> httpx.Response:
        early, lose = self._pre(req, kind)
        if early is not None:
            return early
        obj = apply(json.loads(req.content or b"{}"))
        self.writes.append((req.method, kind))
        if lose:
            raise httpx.ReadTimeout("response lost after the write was applied", request=req)
        return jresp(201 if req.method == "POST" else 200, obj)

    def _author(self) -> dict[str, Any]:
        return {"user": {"login": "tracewise[bot]", "type": "Bot"}, "performed_via_github_app": {"id": self.app_id}}

    # ------------------------------------------------------------ commit comments

    def _list_cc(self, req: httpx.Request) -> httpx.Response:
        early, _ = self._pre(req, "list_cc")
        return early or jresp(200, self.commit_comments[req.url.path.split("/")[-2]])

    def _create_cc(self, req: httpx.Request) -> httpx.Response:
        sha = req.url.path.split("/")[-2]
        return self._write(
            req,
            "cc",
            lambda b: (
                self.commit_comments[sha].append({"id": self._id(), "body": b["body"], "commit_id": sha, **self._author()})
                or self.commit_comments[sha][-1]
            ),
        )

    # ------------------------------------------------------------ PR comments

    def _list_prc(self, req: httpx.Request) -> httpx.Response:
        early, _ = self._pre(req, "list_prc")
        return early or jresp(200, self.pr_comments[int(req.url.path.split("/")[-2])])

    def _create_prc(self, req: httpx.Request) -> httpx.Response:
        n = int(req.url.path.split("/")[-2])
        return self._write(
            req,
            "prc",
            lambda b: (
                self.pr_comments[n].append({"id": self._id(), "body": b["body"], **self._author()}) or self.pr_comments[n][-1]
            ),
        )

    def _update_prc(self, req: httpx.Request) -> httpx.Response:
        cid = int(req.url.path.split("/")[-1])
        found = [c for cs in self.pr_comments.values() for c in cs if c["id"] == cid]
        if not found:
            return jresp(404, {"message": "Not Found"})

        def apply(b: dict[str, Any]) -> dict[str, Any]:
            found[0]["body"] = b["body"]
            return found[0]

        return self._write(req, "prc", apply)

    # ------------------------------------------------------------ check runs

    def _list_cr(self, req: httpx.Request) -> httpx.Response:
        early, _ = self._pre(req, "list_cr")
        sha = req.url.path.split("/")[-2]
        name = req.url.params.get("check_name")
        runs = [c for c in self.check_runs if c["head_sha"] == sha and (name is None or c["name"] == name)]
        return early or jresp(200, {"total_count": len(runs), "check_runs": runs})

    def _create_cr(self, req: httpx.Request) -> httpx.Response:
        def apply(b: dict[str, Any]) -> dict[str, Any]:
            self.check_runs.append({"id": self._id(), **b, "app": {"id": self.app_id}})
            return self.check_runs[-1]

        return self._write(req, "cr", apply)

    def _update_cr(self, req: httpx.Request) -> httpx.Response:
        cid = int(req.url.path.split("/")[-1])
        found = [c for c in self.check_runs if c["id"] == cid]
        if not found:
            return jresp(404, {"message": "Not Found"})

        def apply(b: dict[str, Any]) -> dict[str, Any]:
            found[0].update(b)
            return found[0]

        return self._write(req, "cr", apply)
