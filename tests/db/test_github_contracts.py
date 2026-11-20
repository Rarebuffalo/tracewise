"""Phase 8 GitHub contract audit, offline (fake GitHub; real worker, publisher and RLS tenant pool).

These tests pin what OUR code does under platform behaviours that are documented or simulated. They do not
show that GitHub behaves this way: every simulated platform response below is marked SIMULATED and is a
live gate (docs/GITHUB-CONTRACT-AUDIT.md).
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from tests.db.test_analyze_worker import World, call, final, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import inst, repos_ev
from tests.github_fake import jresp
from tracewise.web.lifecycle import (
    InstallationEvent,
    InstallationRepositoriesEvent,
    process_installation,
    process_installation_repositories,
)

TOKENS = re.compile(r"^/app/installations/\d+/access_tokens$")


def _first(w: World, req: httpx.Request, skip: Any) -> httpx.Response:
    target = req.url.path
    for method, pat, h in w.gh.routes:
        if h is not skip and method == req.method and pat.search(target):
            return h(req)  # type: ignore[no-any-return]
    return jresp(404, {})


def _declining(w: World, permission: str) -> list[dict[str, str]]:
    """SIMULATED: GitHub refuses (422) a token request that includes a permission the installation has not granted.
    The recorded docs only say a token "cannot be granted permissions that the app was not granted"; the exact
    response for an installation that declined one is undocumented (live gate G-PLAT-7)."""
    mints: list[dict[str, str]] = []

    def mint(req: httpx.Request) -> httpx.Response:
        perms = json.loads(req.content)["permissions"]
        mints.append(perms)
        if permission in perms:
            return jresp(422, {"message": "The permissions requested are not granted to this installation."})
        return _first(w, req, mint)

    w.gh.routes.insert(0, ("POST", TOKENS, mint))
    return mints


def test_g_plat_11_a_declined_pull_requests_permission_blocks_only_the_pr_surface(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """Before G-PLAT-11 was fixed, one bundled publish token carried every surface's permission, so this refusal also
    blocked the Check Run and the commit comment (all three ended `unpublished_permission`, nothing published)."""
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    mints = _declining(w, "pull_requests")
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 1  # no crash, no retry loop
    # Association needs Pull requests: it is refused, so D-4 falls back to the commit comment (Contents read).
    assert j["result"]["publications"] == {
        "pr_comment": "unpublished_permission",
        "commit_comment": "published",
        "check_run": "published",
    }
    (cr,) = w.state.check_runs  # AT-REL-05: the Check Run is published and names what is missing
    assert "Pull requests" in cr["output"]["text"] and cr["conclusion"] == "neutral"
    assert len(w.all_ccs()) == 1 and w.all_prcs() == []
    assert all(set(m) <= {"metadata", "contents", "actions", "checks", "pull_requests"} for m in mints)
    assert not any("contents" in m and m["contents"] != "read" for m in mints)  # never more than Contents read
    assert all(len(set(m) - {"metadata"}) == 1 for m in mints if "checks" in m or "pull_requests" in m)  # one per token


def test_g_plat_11_a_declined_checks_permission_blocks_only_the_check_run(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    _declining(w, "checks")
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded"
    assert j["result"]["publications"] == {"commit_comment": "published", "check_run": "unpublished_permission"}
    assert w.state.check_runs == [] and len(w.all_ccs()) == 1
    assert owner.execute("SELECT state, missing_permission FROM publication WHERE surface = 'check_run'").fetchone()[0] == (
        "unpublished_permission"
    )


def test_suspend_mid_job_cancels_without_any_publication(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    def suspend_during_investigation(req):  # type: ignore[no-untyped-def]
        process_installation(pool, "susp-mid", InstallationEvent.model_validate(inst("suspend")))
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), suspend_during_investigation]],
    )
    jid = w.enqueue()
    assert w.worker().run_once()
    assert w.jobrow(jid)["status"] == "cancelled" and w.jobrow(jid)["last_error"] == "installation_suspended"
    assert w.state.writes == [] and owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,)


def test_repository_removed_mid_job_cancels_without_any_publication(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    def remove_during_investigation(req):  # type: ignore[no-untyped-def]
        ev = InstallationRepositoriesEvent.model_validate(repos_ev("removed", [(7, "acme/coffee")]))
        process_installation_repositories(pool, "rm-mid", ev)
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), remove_during_investigation]],
    )
    jid = w.enqueue()
    assert w.worker().run_once()
    assert (w.jobrow(jid)["status"], w.jobrow(jid)["last_error"]) == ("cancelled", "repo_not_in_scope")
    assert w.state.writes == []


def test_suspend_between_surfaces_stops_the_remaining_writes(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """D-10(a), decided (DECISIONS D-13): scope is re-checked before EVERY publication surface. A suspension that
    lands after the commit comment was accepted stops the Check Run (F-2 closed). Whether GitHub itself refuses
    writes for a suspended installation remains a live gate (G-PLAT-6)."""
    w = World(pool, owner, server, tmp_path / "ws", head)
    cc = re.compile(r"^/repos/acme/coffee/commits/[0-9a-f]{40}/comments$")

    def suspend_after_comment(req: httpx.Request) -> httpx.Response:
        resp = _first(w, req, suspend_after_comment)
        process_installation(pool, "susp-between", InstallationEvent.model_validate(inst("suspend")))
        return resp

    w.gh.routes.insert(0, ("POST", cc, suspend_after_comment))
    jid = w.enqueue()
    w.run()
    assert (w.jobrow(jid)["status"], w.jobrow(jid)["last_error"]) == ("cancelled", "installation_suspended")
    assert (len(w.all_ccs()), len(w.state.check_runs)) == (1, 0)
    assert owner.execute("SELECT status FROM installation WHERE id = 9").fetchone() == ("suspended",)


def test_run_cancelled_by_suspension_is_not_reanalysed_after_unsuspend(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """D-10(b), decided (DECISIONS D-13): suspension-cancelled runs stay cancelled; only an explicit retry re-runs.
    A consequence of D-9/D-10 for review: run deduplication (repo, run, attempt) also blocks a
    re-analysis of a run whose job was cancelled while the installation was suspended."""
    from tests.db.test_lifecycle import failure
    from tracewise.contracts import WorkflowRunEvent
    from tracewise.web.ingest import ingest_workflow_run

    World(pool, owner, server, tmp_path / "ws", head)
    body = failure(name="acme/coffee")
    body["workflow_run"] |= {"head_sha": head}
    ev = WorkflowRunEvent.model_validate(body)
    assert ingest_workflow_run(pool, "first", ev).outcome == "enqueued"
    process_installation(pool, "s1", InstallationEvent.model_validate(inst("suspend")))
    process_installation(pool, "u1", InstallationEvent.model_validate(inst("unsuspend")))
    assert owner.execute("SELECT status, last_error FROM job").fetchall() == [("cancelled", "installation_suspended")]
    assert ingest_workflow_run(pool, "redelivered-later", ev).outcome == "duplicate_run"
    assert owner.execute("SELECT count(*) FROM job").fetchone() == (1,)


def test_a_refused_commit_comment_is_reported_on_the_check_run_and_nothing_else_is_blocked(  # type: ignore[no-untyped-def]
    pool,
    owner,
    server,  # noqa: F811
    tmp_path,
    head,  # noqa: F811
) -> None:
    """Partial publication: the commit comment's write is refused (403; e.g. Contents read not honoured for the write,
    which G-PLAT-5 must confirm live). The Check Run is still published, names what is missing, and the job ends with
    an accurate per-surface result, never as a full success claim."""
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.state.fault("POST", "cc", 403)
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 1
    assert j["result"]["publications"] == {"commit_comment": "unpublished_permission", "check_run": "published"}
    (cr,) = w.state.check_runs
    assert "commit comment could not be posted" in cr["output"]["text"] and w.all_ccs() == []
    assert owner.execute("SELECT state, missing_permission FROM publication WHERE surface = 'commit_comment'").fetchone() == (
        "unpublished_permission",
        "contents=read",
    )


def test_a_refused_check_run_write_leaves_the_comment_published_and_the_result_accurate(  # type: ignore[no-untyped-def]
    pool,
    owner,
    server,  # noqa: F811
    tmp_path,
    head,  # noqa: F811
) -> None:
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.state.fault("POST", "cr", 403)
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 1  # a permission refusal is final: no retry loop
    assert j["result"]["publications"] == {"commit_comment": "published", "check_run": "unpublished_permission"}
    assert len(w.all_ccs()) == 1 and w.state.check_runs == []
    assert owner.execute("SELECT state, missing_permission FROM publication WHERE surface = 'check_run'").fetchone() == (
        "unpublished_permission",
        "checks=write",
    )
