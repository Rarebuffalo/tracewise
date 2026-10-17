"""T-303 PR association (AT-PUB-09, AT-PUB-10 REPLAY association half). Fake transport; one recorded real response."""

from __future__ import annotations

import copy
import inspect
import re
from typing import Any

import pytest

from tests.github_fake import FakeGitHub, jresp, recorded
from tracewise.contracts import AnalysisJob, WorkflowRunEvent
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient
from tracewise.github.pulls import associate_pr

SHA = "7689f98403" + "0" * 30
REPO_ID = 7


def pr(
    number: Any,
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


def assoc(rc: RepoClient, fork: bool = False, branch: str | None = "feature", head_repo: str | None = "acme/app"):  # type: ignore[no-untyped-def]
    return associate_pr(rc, head_sha=SHA, head_branch=branch, head_repo_full_name=head_repo, is_fork=fork)


def test_pub09_same_repo_pr_found_via_commit_pulls() -> None:
    gh, rc = client()
    gh.route("GET", rf"^/repos/acme/app/commits/{SHA}/pulls$", jresp(200, [pr(12)]))
    a = assoc(rc)
    assert (a.outcome, a.number, a.source, a.is_pr) == ("matched", 12, "commit_pulls", True)
    assert not gh.calls("GET", r"^/repos/acme/app/pulls$")


def test_pub10_fork_pr_found_via_head_filter() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    gh.route("GET", r"^/repos/acme/app/pulls$", jresp(200, [pr(34, head_repo="contrib/app", ref="fix/x")]))
    a = assoc(rc, fork=True, branch="fix/x", head_repo="contrib/app")
    assert (a.outcome, a.number, a.source) == ("matched", 34, "head_filter")
    q = gh.calls("GET", r"^/repos/acme/app/pulls$")[0].url.params
    assert (q["state"], q["head"]) == ("open", "contrib:fix/x")


def test_pub10_no_match_is_a_push() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    gh.route("GET", r"^/repos/acme/app/pulls$", jresp(200, [pr(34, sha="f" * 40)]))  # branch moved on
    a = assoc(rc, fork=True, branch="fix/x", head_repo="contrib/app")
    assert (a.outcome, a.number, a.is_pr) == ("none", None, False)


@pytest.mark.parametrize("prs", [[pr(40), pr(17)], [pr(5), pr(6), pr(7)]])
def test_multiple_matches_are_ambiguous_not_guessed(prs) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, prs))
    a = assoc(rc)
    assert (a.outcome, a.number, a.is_pr) == ("ambiguous", None, False)
    assert a.candidates == tuple(sorted(p["number"] for p in prs))


def test_fork_head_filter_ambiguity_and_duplicates() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    gh.route("GET", r"^/repos/acme/app/pulls$", jresp(200, [pr(3), pr(9)]))
    assert assoc(rc, fork=True, head_repo="contrib/app").outcome == "ambiguous"
    gh2, rc2 = client()
    gh2.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, [pr(12), pr(12)]))  # same PR twice = one match
    assert assoc(rc2).number == 12


def test_recorded_closed_merged_pr_is_not_associated() -> None:
    """Real anonymous response: pallets/flask PR #6168, merged and closed, head.sha matches the commit."""
    data = recorded("flask-commit-7689f984-pulls.json")
    sha = data[0]["head"]["sha"]
    for state, want in (("closed", "none"), ("open", "matched")):
        doc = copy.deepcopy(data)
        doc[0]["state"] = state
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
        gh.route("GET", rf"/commits/{sha}/pulls$", jresp(200, doc))
        a = associate_pr(rc, head_sha=sha, head_branch=None, head_repo_full_name=None, is_fork=False)
        assert a.outcome == want and (a.number == 6168) == (want == "matched")


@pytest.mark.parametrize(
    "prs",
    [[pr(5, sha="e" * 40)], [pr(5, state="closed")], [pr(5, base_repo_id=999)]],
    ids=["mismatched_head_sha", "closed", "other_base_repo"],
)
def test_non_matching_prs_ignored(prs) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, prs))
    assert assoc(rc).outcome == "none"


@pytest.mark.parametrize(
    "items",
    [
        ["junk", 5, None, {"number": 8}, pr("12"), pr(True), pr(-1), {**pr(9), "head": "x"}, {**pr(10), "base": None}],
    ],
)
def test_malformed_items_skipped(items) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, [*items, pr(21)]))
    assert (assoc(rc).outcome, assoc(rc).number) == ("matched", 21)


@pytest.mark.parametrize("body", [{"message": "not a list"}, "text", None])
def test_malformed_response_is_an_error_not_a_guess(body) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, body))
    a = assoc(rc)
    assert (a.outcome, a.number, a.is_pr) == ("error", None, False) and a.detail


def test_permission_errors_propagate() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(403, {"message": "Resource not accessible by integration"}))
    with pytest.raises(gh_err.PermissionDenied):
        assoc(rc)


def test_same_repo_does_not_use_head_filter_and_fork_without_branch_is_push() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{SHA}/pulls$", jresp(200, []))
    assoc(rc)
    assoc(rc, fork=True, branch=None, head_repo="contrib/app")
    assert not gh.calls("GET", r"^/repos/acme/app/pulls$")


def test_analysis_scope_cannot_list_pulls() -> None:
    _, rc = client(scope="analysis")
    with pytest.raises(ValueError, match="outside the 'analysis' token scope"):
        assoc(rc)


def test_webhook_pull_requests_field_is_never_used() -> None:
    assert "pull_requests" not in inspect.signature(associate_pr).parameters
    assert "pull_requests" not in WorkflowRunEvent.model_fields["workflow_run"].annotation.model_fields  # type: ignore[union-attr]
    assert not any(re.search("pull|pr_number", f) for f in AnalysisJob.model_fields)
