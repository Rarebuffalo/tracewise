"""T-303 PR association (AT-PUB-09, AT-PUB-10 REPLAY half). Fake transport; one recorded real response."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.github_fake import FakeGitHub, jresp, recorded
from tracewise.github.client import RepoClient
from tracewise.github.pulls import associate_pr

SHA = "7689f98403" + "0" * 30
REPO_ID = 7


def pr(
    number: int,
    sha: str = SHA,
    state: str = "open",
    base_repo_id: int = REPO_ID,
    head_repo: str = "acme/app",
    ref: str = "feature",
) -> dict[str, Any]:
    return {
        "number": number,
        "state": state,
        "head": {"sha": sha, "ref": ref, "repo": {"full_name": head_repo}},
        "base": {"repo": {"id": base_repo_id, "full_name": "acme/app"}},
    }


def client(scope: str = "publish") -> tuple[FakeGitHub, RepoClient]:
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http()
    return gh, RepoClient(http, gh.provider(http), installation_id=1, repo_id=REPO_ID, full_name="acme/app", scope=scope)


def test_pub09_same_repo_pr_found_via_commit_pulls() -> None:
    gh, rc = client()
    gh.route("GET", rf"^/repos/acme/app/commits/{SHA}/pulls$", jresp(200, [pr(12)]))
    a = associate_pr(rc, head_sha=SHA, head_branch="feature", head_repo_full_name="acme/app", is_fork=False)
    assert (a.number, a.source) == (12, "commit_pulls")
    assert not gh.calls("GET", r"^/repos/acme/app/pulls$")


def test_pub10_fork_pr_found_via_head_filter() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    gh.route("GET", r"^/repos/acme/app/pulls$", jresp(200, [pr(34, head_repo="contrib/app", ref="fix/x")]))
    a = associate_pr(rc, head_sha=SHA, head_branch="fix/x", head_repo_full_name="contrib/app", is_fork=True)
    assert (a.number, a.source) == (34, "head_filter")
    q = gh.calls("GET", r"^/repos/acme/app/pulls$")[0].url.params
    assert (q["state"], q["head"]) == ("open", "contrib:fix/x")


def test_pub10_no_match_is_a_push() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    gh.route("GET", r"^/repos/acme/app/pulls$", jresp(200, [pr(34, sha="f" * 40)]))  # branch moved on
    a = associate_pr(rc, head_sha=SHA, head_branch="fix/x", head_repo_full_name="contrib/app", is_fork=True)
    assert (a.number, a.source, a.is_pr) == (None, "none", False)


def test_recorded_closed_merged_pr_is_not_associated() -> None:
    """Real anonymous response: pallets/flask PR #6168, merged and closed, head.sha matches the commit."""
    data = recorded("flask-commit-7689f984-pulls.json")
    sha = data[0]["head"]["sha"]
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http()
    rc = RepoClient(
        http,
        gh.provider(http),
        installation_id=1,
        repo_id=data[0]["base"]["repo"]["id"],
        full_name="pallets/flask",
        scope="publish",
    )
    gh.route("GET", rf"/commits/{sha}/pulls$", jresp(200, data))
    assert associate_pr(rc, head_sha=sha, head_branch=None, head_repo_full_name=None, is_fork=False).number is None
    reopened = copy.deepcopy(data)
    reopened[0]["state"] = "open"
    gh.routes.clear()
    gh.add_token_route()
    gh.route("GET", rf"/commits/{sha}/pulls$", jresp(200, reopened))
    assert associate_pr(rc, head_sha=sha, head_branch=None, head_repo_full_name=None, is_fork=False).number == 6168


@pytest.mark.parametrize(
    "prs",
    [[pr(5, sha="e" * 40)], [pr(5, state="closed")], [pr(5, base_repo_id=999)]],
    ids=["stale_head", "closed", "other_base_repo"],
)
def test_non_matching_prs_ignored(prs) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, prs))
    assert associate_pr(rc, head_sha=SHA, head_branch="feature", head_repo_full_name="acme/app", is_fork=False).number is None


def test_multiple_matches_pick_lowest_number() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, [pr(40), pr(17)]))
    a = associate_pr(rc, head_sha=SHA, head_branch="feature", head_repo_full_name="acme/app", is_fork=False)
    assert (a.number, a.candidates) == (17, 2)


def test_same_repo_does_not_use_head_filter_and_fork_without_branch_is_push() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    associate_pr(rc, head_sha=SHA, head_branch="feature", head_repo_full_name="acme/app", is_fork=False)
    associate_pr(rc, head_sha=SHA, head_branch=None, head_repo_full_name="contrib/app", is_fork=True)
    assert not gh.calls("GET", r"^/repos/acme/app/pulls$")


def test_analysis_scope_cannot_list_pulls() -> None:
    _, rc = client(scope="analysis")
    with pytest.raises(ValueError, match="outside the 'analysis' token scope"):
        associate_pr(rc, head_sha=SHA, head_branch="f", head_repo_full_name="acme/app", is_fork=False)
