"""PR association by API (T-303; FS-PUB-7, ADR-15).

Never trusts `workflow_run.pull_requests` (empty in 20/20 sampled runs, EV-P23/24); this function
does not even accept it.
1. `GET /commits/{head_sha}/pulls` → open PRs into THIS repository whose `head.sha == head_sha`.
2. Fork runs only, if (1) found nothing: `GET /pulls?state=open&head={head_owner}:{head_branch}`,
   filtered the same way.
3. Exactly one match → that PR. No match → `none` (treated as a push: commit comment).
4. Several matches → `ambiguous` with all candidates. FS-PUB-7 defines no tie-break, so none is
   invented (revised 2026-10-18; the earlier "lowest number" rule had no basis in the spec).
   Publishing policy for `ambiguous` and `error` is DECISIONS D-4: no PR comment.
5. A malformed response → `error` (nothing is guessed); malformed items are skipped individually.
Needs a `publish`-scope client (Pull requests read is outside the analysis scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient

Outcome = Literal["matched", "none", "ambiguous", "error"]
Source = Literal["commit_pulls", "head_filter", "none"]


@dataclass(frozen=True)
class PRAssociation:
    outcome: Outcome
    number: int | None = None
    source: Source = "none"
    candidates: tuple[int, ...] = ()
    detail: str | None = None

    @property
    def is_pr(self) -> bool:
        return self.outcome == "matched"


def _obj(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _matches(prs: Any, head_sha: str, repo_id: int) -> list[int]:
    if not isinstance(prs, list):
        raise gh_err.GitHubPermanent("pull request list is not a list")
    out = set()
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        head = _obj(pr.get("head"))
        base_repo = _obj(_obj(pr.get("base")).get("repo"))
        n = pr.get("number")
        if (
            pr.get("state") == "open"
            and head.get("sha") == head_sha
            and base_repo.get("id") == repo_id
            and isinstance(n, int)
            and not isinstance(n, bool)
            and n > 0
        ):
            out.add(n)
    return sorted(out)


def _decide(found: list[int], source: Source) -> PRAssociation | None:
    if len(found) == 1:
        return PRAssociation("matched", found[0], source, tuple(found))
    if len(found) > 1:
        return PRAssociation("ambiguous", None, source, tuple(found), "several open PRs have this head commit")
    return None


def associate_pr(
    rc: RepoClient, *, head_sha: str, head_branch: str | None, head_repo_full_name: str | None, is_fork: bool
) -> PRAssociation:
    try:
        found = _matches(rc.paginate("list_commit_pulls", None, sha=head_sha), head_sha, rc.repo_id)
        if (decided := _decide(found, "commit_pulls")) is not None:
            return decided
        if is_fork and head_branch and head_repo_full_name and "/" in head_repo_full_name:
            head_owner = head_repo_full_name.split("/", 1)[0]
            prs = rc.paginate("list_pulls", None, query={"state": "open", "head": f"{head_owner}:{head_branch}"})
            if (decided := _decide(_matches(prs, head_sha, rc.repo_id), "head_filter")) is not None:
                return decided
    except gh_err.GitHubPermanent as e:
        if isinstance(e, gh_err.PermissionDenied | gh_err.InstallationUnavailable):
            raise  # handled by the failure/permission paths (T-503), not guessed here
        return PRAssociation("error", detail=f"PR lookup failed: {type(e).__name__}")
    return PRAssociation("none")
