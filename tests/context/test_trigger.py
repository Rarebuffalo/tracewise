"""T-306 trigger diff + touches_implicated (AT-ATR-01/02/03/09 at unit level; fake GitHub transport).
Compare responses are synthetic; the P-03 commit is a real anonymous recorded response."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.context.memsource import MemSource
from tests.github_fake import FakeGitHub, jresp, recorded
from tracewise.context.tools import ToolBox
from tracewise.context.trigger import ChangedFile, TriggerDiff, compute_trigger_diff, relevance, to_attribution
from tracewise.github.client import RepoClient

C0, C1, C2 = "0" * 40, "1" * 40, "2" * 40
IMPLICATED_B02 = {"tests/test_pricing.py", "coffee_shop/pricing.py"}  # pre-pass test path + diagnosis location


def client(repo: str = "acme/app") -> tuple[FakeGitHub, RepoClient]:
    gh = FakeGitHub()
    gh.add_token_route()
    http = gh.http()
    return gh, RepoClient(http, gh.provider(http), installation_id=1, repo_id=7, full_name=repo, scope="analysis")


def commit(sha: str, parents: list[str]) -> dict[str, Any]:
    return {"sha": sha, "parents": [{"sha": p} for p in parents]}


def compare(files: list[tuple[str, str]], total_commits: int = 1, **extra: Any) -> dict[str, Any]:
    return {
        "status": "ahead",
        "total_commits": total_commits,
        "files": [
            {"filename": f, "status": st, "additions": 1, "deletions": 1, "patch": "@@ -1 +1 @@\n-a\n+b", **extra}
            for f, st in files
        ],
    }


def no_causal_language(text: str) -> bool:
    return not re.search(r"(?i)\bcaus|introduc|broke|responsible|fault of", text)


def test_atr01_readme_only_push_not_implicated() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{C2}$", jresp(200, commit(C2, [C1])))
    gh.route("GET", rf"/compare/{C1}\.\.\.{C2}$", jresp(200, compare([("README.md", "modified")])))
    diff = compute_trigger_diff(rc, C2)
    rel = relevance(diff, IMPLICATED_B02)
    assert rel.touches_implicated is False
    assert "changed only README.md; not implicated; likely pre-dates this push" in rel.statement
    att = to_attribution(diff, rel)
    assert (att.touches_implicated, att.trigger_changed_files, att.trigger_sha) == (False, ["README.md"], C2)
    assert no_causal_language(rel.statement)


def test_atr02_implicated_file_changed() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{C1}$", jresp(200, commit(C1, [C0])))
    gh.route("GET", rf"/compare/{C0}\.\.\.{C1}$", jresp(200, compare([("coffee_shop/pricing.py", "modified")])))
    rel = relevance(compute_trigger_diff(rc, C1), IMPLICATED_B02)
    assert rel.touches_implicated is True and "coffee_shop/pricing.py" in rel.statement
    assert rel.overlap == ("coffee_shop/pricing.py",) and no_causal_language(rel.statement)


def test_atr03_fork_pr_with_base_sha_same_statement() -> None:
    gh, rc = client()
    gh.route("GET", rf"/compare/{C0}\.\.\.{C2}$", jresp(200, compare([("README.md", "modified")])))
    rel = relevance(compute_trigger_diff(rc, C2, base_sha=C0), IMPLICATED_B02)
    assert "changed only README.md; not implicated; likely pre-dates this push" in rel.statement
    assert not gh.calls("GET", r"/commits/")  # base given: no parent lookup
    assert no_causal_language(rel.statement)


def test_atr09_b17_touch_is_evidence_only() -> None:
    diff = TriggerDiff(C2, C1, (ChangedFile("pkg/mod.py", "modified"),))
    rel = relevance(diff, {"pkg/mod.py"})
    assert rel.touches_implicated is True and no_causal_language(rel.statement)
    assert "signal, not proof" in rel.statement


def test_atr09_p03_recorded_commit_without_logs_is_unknown() -> None:
    """META P-03 (real anonymous commit): trigger edits src/flask/app.py; no logs → no implicated paths → unknown."""
    doc = recorded("flask-commit-d73fa1cdcb.json")
    gh, rc = client("pallets/flask")
    parent = doc["parents"][0]["sha"]
    gh.route("GET", rf"/commits/{doc['sha']}$", jresp(200, doc))
    gh.route("GET", rf"/compare/{parent}\.\.\.{doc['sha']}$", jresp(200, {"total_commits": 1, "files": doc["files"]}))
    diff = compute_trigger_diff(rc, doc["sha"])
    assert diff.known and diff.changed_paths() == {"src/flask/app.py"}
    rel = relevance(diff, [])
    assert rel.touches_implicated is None and no_causal_language(rel.statement)


@pytest.mark.parametrize(
    ("setup", "reason"),
    [("root", "root commit"), ("compare404", "compare unavailable"), ("bad_parent", "invalid"), ("garbage", "unexpected")],
)
def test_unknown_diffs_never_claim_not_implicated(setup, reason) -> None:  # type: ignore[no-untyped-def]
    gh, rc = client()
    if setup == "root":
        gh.route("GET", rf"/commits/{C1}$", jresp(200, commit(C1, [])))
    elif setup == "compare404":
        gh.route("GET", rf"/commits/{C1}$", jresp(200, commit(C1, [C0])))
    elif setup == "bad_parent":
        gh.route("GET", rf"/commits/{C1}$", jresp(200, commit(C1, ["../../x"])))
    else:
        gh.route("GET", rf"/commits/{C1}$", jresp(200, ["not", "a", "commit"]))
    diff = compute_trigger_diff(rc, C1)
    assert not diff.known and reason in (diff.reason or "")
    rel = relevance(diff, IMPLICATED_B02)
    assert rel.touches_implicated is None and "unknown" in rel.statement
    assert to_attribution(diff, rel).touches_implicated is None


def test_truncated_diff_without_overlap_is_unknown_but_overlap_still_counts() -> None:
    gh, rc = client()
    many = [(f"gen/f{i}.txt", "added") for i in range(300)]
    gh.route("GET", rf"/compare/{C0}\.\.\.{C1}$", jresp(200, compare(many)))
    diff = compute_trigger_diff(rc, C1, base_sha=C0)
    assert diff.truncated
    assert relevance(diff, IMPLICATED_B02).touches_implicated is None
    assert relevance(diff, {"gen/f7.txt"}).touches_implicated is True
    gh2, rc2 = client()
    gh2.route("GET", rf"/compare/{C0}\.\.\.{C1}$", jresp(200, compare([("a.py", "modified")], total_commits=251)))
    assert compute_trigger_diff(rc2, C1, base_sha=C0).truncated


def test_renames_unsafe_names_and_empty_implicated() -> None:
    gh, rc = client()
    gh.route(
        "GET",
        rf"/compare/{C0}\.\.\.{C1}$",
        jresp(
            200,
            {
                "total_commits": 1,
                "files": [
                    {"filename": "coffee_shop/prices.py", "status": "renamed", "previous_filename": "coffee_shop/pricing.py"},
                    {"filename": "../../etc/passwd", "status": "added"},
                    {"filename": "ok.md", "status": "added", "previous_filename": "/abs"},
                ],
            },
        ),
    )
    diff = compute_trigger_diff(rc, C1, base_sha=C0)
    assert diff.changed_paths() == {"coffee_shop/prices.py", "coffee_shop/pricing.py", "ok.md"}
    assert relevance(diff, {"coffee_shop/pricing.py"}).touches_implicated is True  # rename source counts
    assert relevance(diff, {"/abs/x", "../y"}).touches_implicated is None  # invalid implicated paths ignored


def test_invalid_head_and_statement_length() -> None:
    _, rc = client()
    with pytest.raises(ValueError):
        compute_trigger_diff(rc, "not-a-sha")
    diff = TriggerDiff(C1, C0, tuple(ChangedFile(f"dir/{'x' * 120}{i}.md", "added") for i in range(10)))
    rel = relevance(diff, {"src/a.py"})
    assert "and 7 more" in rel.statement and len(to_attribution(diff, rel).statement) <= 400


def test_render_feeds_get_diff_tool() -> None:
    diff = TriggerDiff(C1, C0, (ChangedFile("coffee_shop/pricing.py", "modified", 1, 1, None, "@@ -41 +41 @@\n-x\n+y"),))
    text = diff.render()
    assert "M coffee_shop/pricing.py (+1 -1)" in text and "@@ -41 +41 @@" in text
    assert len(TriggerDiff(C1, C0, (ChangedFile("a", "added", patch="p" * 20000),)).render(500)) < 600
    box = ToolBox(MemSource({}), diff_text=text)
    assert "coffee_shop/pricing.py" in box.call("get_diff", {}).content
    assert "unavailable" in TriggerDiff(C1, None, known=False, reason="root commit").render()


@pytest.mark.parametrize(
    "parents",
    [["0" * 40], [42], [None], [{"sha": 7}], [{}]],
    ids=["string-parent", "number-parent", "null-parent", "sha-not-a-string", "parent-without-sha"],
)
def test_malformed_parent_entries_give_an_unknown_diff_not_a_crash(parents: list[Any]) -> None:
    """Sprint fix: `parents[0].get` assumed an object. A malformed parent now yields an unknown trigger diff
    (the existing convention for unexpected commit responses), never an AttributeError retried by the worker."""
    gh, rc = client()
    gh.route("GET", rf"/commits/{C1}$", jresp(200, {"sha": C1, "parents": parents}))
    diff = compute_trigger_diff(rc, C1)
    assert not diff.known and "unexpected commit response" in (diff.reason or "")


def test_absent_parents_and_valid_parents_keep_their_behaviour() -> None:
    gh, rc = client()
    gh.route("GET", rf"/commits/{C1}$", jresp(200, {"sha": C1}))  # no "parents" key at all
    assert compute_trigger_diff(rc, C1).reason == "unexpected commit response"
    gh2, rc2 = client()
    gh2.route("GET", rf"/commits/{C1}$", jresp(200, commit(C1, [C0])))
    gh2.route("GET", rf"/compare/{C0}\.\.\.{C1}$", jresp(200, compare([("a.py", "modified")])))
    diff = compute_trigger_diff(rc2, C1)
    assert diff.known and diff.base_sha == C0 and diff.changed_paths() == {"a.py"}


@pytest.mark.parametrize("bad", ["x", [1], {"n": 1}, -3, True, 1.5, None])
def test_malformed_line_counts_in_a_compare_file_are_zero_not_a_crash(bad: Any) -> None:
    from tracewise.context.trigger import _parse_compare

    doc = {"files": [{"filename": "a.py", "status": "modified", "additions": bad, "deletions": bad, "patch": 7}]}
    d = _parse_compare(doc, "b" * 40, "a" * 40)
    (f,) = d.files
    assert (f.path, f.additions, f.deletions, f.patch) == ("a.py", 0, 0, None)
