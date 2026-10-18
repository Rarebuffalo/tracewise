"""Registry of every GitHub REST call Tracewise may make (AT-SEC-01).

The client can only call endpoints listed here. Each entry names the single App permission
that authorises it, so the permission surface is checkable statically: every entry must be
covered by the five permissions in FS-INS-2, and none may write contents, workflows or issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Method = Literal["GET", "POST", "PATCH"]
Access = Literal["read", "write"]
Auth = Literal["app", "installation"]

# FS-INS-2: exactly these, nothing else.
APP_PERMISSIONS: dict[str, Access] = {
    "actions": "read",
    "contents": "read",
    "metadata": "read",
    "pull_requests": "write",
    "checks": "write",
}

# Per-purpose token scopes: each token gets only what its phase needs.
ANALYSIS_SCOPE: dict[str, Access] = {"actions": "read", "contents": "read", "metadata": "read"}
PUBLISH_SCOPE: dict[str, Access] = {"contents": "read", "metadata": "read", "pull_requests": "write", "checks": "write"}
SCOPES: dict[str, dict[str, Access]] = {"analysis": ANALYSIS_SCOPE, "publish": PUBLISH_SCOPE}


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: Method
    path: str  # template; {owner}/{repo} are always the bound repository
    permission: str | None  # None for App-JWT endpoints
    access: Access | None
    auth: Auth = "installation"
    paginated: bool = False


ENDPOINTS: dict[str, Endpoint] = {
    e.name: e
    for e in (
        Endpoint("create_installation_token", "POST", "/app/installations/{installation_id}/access_tokens", None, None, "app"),
        Endpoint("get_run", "GET", "/repos/{owner}/{repo}/actions/runs/{run_id}", "actions", "read"),
        Endpoint(
            "list_jobs_for_attempt",
            "GET",
            "/repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs",
            "actions",
            "read",
            paginated=True,
        ),
        Endpoint("download_job_logs", "GET", "/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", "actions", "read"),
        Endpoint("get_commit", "GET", "/repos/{owner}/{repo}/commits/{sha}", "contents", "read"),
        Endpoint("compare", "GET", "/repos/{owner}/{repo}/compare/{basehead}", "contents", "read"),
        Endpoint("get_contents", "GET", "/repos/{owner}/{repo}/contents/{path}", "contents", "read"),
        Endpoint("get_tree", "GET", "/repos/{owner}/{repo}/git/trees/{tree_sha}", "contents", "read"),
        Endpoint("get_blob", "GET", "/repos/{owner}/{repo}/git/blobs/{file_sha}", "contents", "read"),
        Endpoint(
            "list_commit_pulls", "GET", "/repos/{owner}/{repo}/commits/{sha}/pulls", "pull_requests", "read", paginated=True
        ),
        Endpoint("list_pulls", "GET", "/repos/{owner}/{repo}/pulls", "pull_requests", "read", paginated=True),
        Endpoint("create_commit_comment", "POST", "/repos/{owner}/{repo}/commits/{sha}/comments", "contents", "read"),
        Endpoint(
            "list_commit_comments", "GET", "/repos/{owner}/{repo}/commits/{sha}/comments", "contents", "read", paginated=True
        ),
        Endpoint(
            "list_pr_comments", "GET", "/repos/{owner}/{repo}/issues/{number}/comments", "pull_requests", "read", paginated=True
        ),
        Endpoint("create_pr_comment", "POST", "/repos/{owner}/{repo}/issues/{number}/comments", "pull_requests", "write"),
        Endpoint("update_pr_comment", "PATCH", "/repos/{owner}/{repo}/issues/comments/{comment_id}", "pull_requests", "write"),
        Endpoint(
            "list_check_runs_for_ref", "GET", "/repos/{owner}/{repo}/commits/{ref}/check-runs", "checks", "read", paginated=True
        ),
        Endpoint("create_check_run", "POST", "/repos/{owner}/{repo}/check-runs", "checks", "write"),
        Endpoint("update_check_run", "PATCH", "/repos/{owner}/{repo}/check-runs/{check_run_id}", "checks", "write"),
    )
}


def covered(permission: str | None, access: Access | None, granted: dict[str, Access]) -> bool:
    if permission is None:
        return True
    have = granted.get(permission)
    return have == "write" or (have == "read" and access == "read")
