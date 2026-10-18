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


def test_g_plat_11_bundled_publish_token_refusal_also_blocks_the_check_run(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """SIMULATED: GitHub refuses (422) a token request that includes a permission the installation has not granted.

    The recorded docs only say a token "cannot be granted permissions that the app was not granted"; the
    response for an installation that declined a permission is undocumented. Under this simulation the bundled
    `publish` scope (pull_requests:write + checks:write) blocks the Check Run too, which AT-REL-05 intends to
    keep publishing (and the commit comment, which needs only Contents read).
    This test pins today's behaviour so that a change (per-surface tokens) is deliberate.
    """
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    mints: list[dict[str, str]] = []

    def mint(req: httpx.Request) -> httpx.Response:
        perms = json.loads(req.content)["permissions"]
        mints.append(perms)
        if perms.get("pull_requests") == "write":
            return jresp(422, {"message": "The permissions requested are not granted to this installation."})
        return _first(w, req, mint)

    w.gh.routes.insert(0, ("POST", TOKENS, mint))
    jid = w.enqueue()
    w.run()
    j = w.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 1  # no crash, no retry loop
    # PR association also uses the publish token, so it fails too; D-4 then falls back to the commit comment,
    # which needs only Contents read but shares the same refused token. Every surface is blocked.
    assert j["result"]["publications"] == {
        "pr_comment": "unpublished_permission",
        "commit_comment": "unpublished_permission",
        "check_run": "unpublished_permission",
    }
    assert w.state.check_runs == [] and w.all_prcs() == [] and w.state.writes == []  # the gap: no Check Run at all
    assert sum(1 for m in mints if m.get("pull_requests") == "write") <= 4  # bounded: one refused mint per surface try


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


def test_suspend_between_surfaces_does_not_stop_remaining_writes_today(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """Documents D-10: scope is re-checked before persisting, not between publication surfaces. A suspension that
    lands after the commit comment was accepted does not stop the Check Run; the cached publish token is used.
    Whether GitHub refuses that write for a suspended installation is a live gate (G-PLAT-6)."""
    w = World(pool, owner, server, tmp_path / "ws", head)
    cc = re.compile(r"^/repos/acme/coffee/commits/[0-9a-f]{40}/comments$")

    def suspend_after_comment(req: httpx.Request) -> httpx.Response:
        resp = _first(w, req, suspend_after_comment)
        process_installation(pool, "susp-between", InstallationEvent.model_validate(inst("suspend")))
        return resp

    w.gh.routes.insert(0, ("POST", cc, suspend_after_comment))
    jid = w.enqueue()
    w.run()
    assert w.jobrow(jid)["status"] == "succeeded"
    assert (len(w.all_ccs()), len(w.state.check_runs)) == (1, 1)
    assert owner.execute("SELECT status FROM installation WHERE id = 9").fetchone() == ("suspended",)


def test_run_cancelled_by_suspension_is_not_reanalysed_after_unsuspend(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    """PENDING D-10 (documents current behaviour; not a decision).
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
