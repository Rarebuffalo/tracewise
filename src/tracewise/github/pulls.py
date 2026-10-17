"""PR association by API (T-303; FS-PUB-7, ADR-15).

Never trusts `workflow_run.pull_requests` (empty in 20/20 sampled runs, EV-P23/24).
1. `GET /commits/{head_sha}/pulls` → open PRs into THIS repository whose `head.sha == head_sha`.
2. Fork runs only, if (1) found nothing: `GET /pulls?state=open&head={head_owner}:{head_branch}`,
   filtered the same way.
3. No match → `None`: the run is treated as a push (commit comment).
Several matches (one branch open against two bases) → the lowest PR number, deterministically.
Needs a `publish`-scope client (Pull requests read is outside the analysis scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from tracewise.github.client import RepoClient

Source = Literal["commit_pulls", "head_filter", "none"]


@dataclass(frozen=True)
class PRAssociation:
    number: int | None
    source: Source
    candidates: int = 0

    @property
    def is_pr(self) -> bool:
        return self.number is not None


def _matches(prs: list[dict[str, Any]], head_sha: str, repo_id: int) -> list[int]:
    out = []
    for pr in prs:
        head = pr.get("head") or {}
        base_repo = (pr.get("base") or {}).get("repo") or {}
        if pr.get("state") == "open" and head.get("sha") == head_sha and base_repo.get("id") == repo_id:
            n = pr.get("number")
            if isinstance(n, int):
                out.append(n)
    return sorted(out)


def associate_pr(
    rc: RepoClient, *, head_sha: str, head_branch: str | None, head_repo_full_name: str | None, is_fork: bool
) -> PRAssociation:
    found = _matches(rc.paginate("list_commit_pulls", None, sha=head_sha), head_sha, rc.repo_id)
    if found:
        return PRAssociation(found[0], "commit_pulls", len(found))
    if is_fork and head_branch and head_repo_full_name and "/" in head_repo_full_name:
        head_owner = head_repo_full_name.split("/", 1)[0]
        prs = rc.paginate("list_pulls", None, query={"state": "open", "head": f"{head_owner}:{head_branch}"})
        found = _matches(prs, head_sha, rc.repo_id)
        if found:
            return PRAssociation(found[0], "head_filter", len(found))
    return PRAssociation(None, "none")
