"""Phase 45C: D-10 owner decisions (DECISIONS D-13).

(a) Authorisation is re-checked before EVERY publication surface. Revocation stops further surfaces, records a
    content-free `cancelled` outcome, never duplicates a comment and never claims success.
(b) Runs cancelled because of a suspension stay cancelled after the installation is resumed. Only an explicit retry
    (a GitHub re-run, i.e. a new run attempt delivered as a new webhook) analyses that failure again.
Offline: fake GitHub, scripted model, real worker/queue/publisher on the RLS tenant pool.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import inst
from tests.db.test_recovery import Hub, run_obj, sweep
from tracewise.contracts import WorkflowRunEvent
from tracewise.db import repositories as repo
from tracewise.web.ingest import ingest_workflow_run
from tracewise.web.lifecycle import InstallationEvent, process_installation

CC = re.compile(r"^/repos/acme/coffee/commits/[0-9a-f]{40}/comments$")


def suspend(w: World, n: int = 0) -> None:
    process_installation(w.pool, f"susp-{n}", InstallationEvent.model_validate(inst("suspend")))


def unsuspend(w: World, n: int = 0) -> None:
    process_installation(w.pool, f"unsusp-{n}", InstallationEvent.model_validate(inst("unsuspend")))


def writes(w: World) -> tuple[int, int, int, int]:
    return (w.state.count("POST", "cc"), len(w.all_ccs()), w.state.count("POST", "cr"), len(w.state.check_runs))


def delivered(w: World, attempt: int, delivery: str) -> str:
    body = {
        "action": "completed",
        "installation": {"id": 9},
        "repository": {"id": 7, "full_name": "acme/coffee"},
        "workflow_run": {**run_obj(55, head_sha=w.head, attempt=attempt), "head_branch": "feature"},
    }
    return ingest_workflow_run(w.pool, delivery, WorkflowRunEvent.model_validate(body)).outcome


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]  # noqa: F811
    return World(pool, owner, server, tmp_path / "ws", head)


# ------------------------------------------------------------------ (a) re-check before every surface


def test_revoked_after_persisting_before_the_first_surface(world: World, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    real = repo.upsert_analysis

    def persist_then_suspend(*a: Any, **k: Any) -> int:
        out = real(*a, **k)
        world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")
        return out

    monkeypatch.setattr(repo, "upsert_analysis", persist_then_suspend)
    jid = world.enqueue()
    world.run()
    j = world.jobrow(jid)
    assert (j["status"], j["last_error"]) == ("cancelled", "installation_suspended")
    assert world.state.writes == [] and writes(world) == (0, 0, 0, 0)  # no surface at all
    assert world.owner.execute("SELECT count(*) FROM publication WHERE state = 'published'").fetchone() == (0,)


def test_revoked_between_two_surfaces(world: World) -> None:
    def suspend_after_comment(req: httpx.Request) -> httpx.Response:
        resp = next(
            h for m, p, h in world.gh.routes if h is not suspend_after_comment and m == "POST" and p.search(req.url.path)
        )(req)
        world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")
        return resp

    world.gh.routes.insert(0, ("POST", CC, suspend_after_comment))
    jid = world.enqueue()
    world.run()
    assert (world.jobrow(jid)["status"], world.jobrow(jid)["last_error"]) == ("cancelled", "installation_suspended")
    assert writes(world) == (1, 1, 0, 0)  # the commit comment stays; no Check Run after the revocation
    states = dict(world.owner.execute("SELECT surface, state FROM publication").fetchall())
    assert states == {"commit_comment": "published"}  # nothing claims a Check Run


def test_revoked_during_a_retry(world: World) -> None:
    world.state.fault("POST", "cr", 502)
    jid = world.enqueue()
    world.run()  # attempt 1: commit comment published, Check Run failed → retry_wait
    assert world.jobrow(jid)["status"] == "retry_wait" and writes(world) == (1, 1, 0, 0)
    suspend(world)  # lifecycle cancels pending work, including retry_wait
    assert world.jobrow(jid)["status"] == "cancelled"
    world.ready(jid)
    assert not world.worker().run_once() and writes(world) == (1, 1, 0, 0)


def test_uncertain_publication_then_revocation_then_explicit_retry_never_duplicates(world: World) -> None:
    world.state.fault("POST", "cc", "accept_then_timeout")  # GitHub stored the comment; we never saw the answer
    jid = world.enqueue()
    world.run()
    assert world.jobrow(jid)["status"] == "retry_wait" and len(world.all_ccs()) == 1
    cc_state = world.owner.execute("SELECT state FROM publication WHERE surface = 'commit_comment'").fetchone()
    assert cc_state != ("published",)  # no misleading success recorded for the uncertain write
    suspend(world)
    unsuspend(world)
    assert world.jobrow(jid)["status"] == "cancelled"  # (b): resuming does not revive it
    assert delivered(world, 2, "rerun-2") == "enqueued"  # the explicit retry: a GitHub re-run (attempt 2)
    world.run()
    assert len(world.all_ccs()) == 1 and world.state.count("POST", "cc") == 1  # reconciled (adopted), not re-posted
    assert len(world.state.check_runs) == 1


# ------------------------------------------------------------------ (b) explicit retry after suspension


def test_suspension_cancelled_runs_stay_cancelled_until_an_explicit_retry(world: World) -> None:
    assert delivered(world, 1, "orig-1") == "enqueued"
    (jid,) = world.owner.execute("SELECT id FROM job").fetchone()
    suspend(world, 1)
    assert world.jobrow(jid)["status"] == "cancelled"
    for n in range(2, 5):  # repeated, out-of-order lifecycle events
        unsuspend(world, n)
        suspend(world, n)
        unsuspend(world, n + 10)
    assert world.owner.execute("SELECT status FROM installation WHERE id = 9").fetchone() == ("active",)
    assert world.jobrow(jid)["status"] == "cancelled"  # reactivation is not authorisation to re-run
    assert delivered(world, 1, "orig-1") == "duplicate_delivery"  # GitHub redelivers the same webhook
    assert delivered(world, 1, "redelivered-new-guid") == "duplicate_run"  # or the same run under a new GUID
    hub = Hub(world.gh)
    hub.runs[7] = [run_obj(55, head_sha=world.head)]
    assert sweep(world.pool, hub).enqueued == 0  # the recovery sweep does not revive it either
    assert not world.worker().run_once() and world.state.writes == []
    assert world.owner.execute("SELECT count(*) FROM job").fetchone() == (1,)
    assert delivered(world, 2, "rerun-2") == "enqueued"  # explicit retry = a GitHub re-run (new attempt)
    world.run()
    assert writes(world) == (1, 1, 1, 1)
    statuses = sorted(r[0] for r in world.owner.execute("SELECT status FROM job"))
    assert statuses == ["cancelled", "succeeded"]  # the original stays cancelled; the retry succeeded


def test_stale_queued_work_is_not_revived_by_resumption(world: World) -> None:
    q1 = world.enqueue()
    q2 = world.enqueue(attempt=2)
    world.owner.execute("UPDATE job SET status = 'retry_wait', attempts = 1 WHERE id = %s", (q2,))
    suspend(world)
    unsuspend(world)
    assert {world.jobrow(q1)["status"], world.jobrow(q2)["status"]} == {"cancelled"}
    world.owner.execute("UPDATE job SET run_after = now() - interval '1 second'")
    assert not world.worker().run_once() and world.state.writes == []


# ------------------------------------------------------------------ Phase 46E: the PR and notice paths


PRC = re.compile(r"^/repos/acme/coffee/issues/\d+/comments$")


def _suspend_after_persist(world: World, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    real = repo.upsert_analysis

    def persist_then_suspend(*a: Any, **k: Any) -> int:
        out = real(*a, **k)
        world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")
        return out

    monkeypatch.setattr(repo, "upsert_analysis", persist_then_suspend)


def _suspend_after_post(world: World, path: re.Pattern[str]) -> None:
    def hook(req: httpx.Request) -> httpx.Response:
        resp = next(h for m, p, h in world.gh.routes if h is not hook and m == "POST" and p.search(req.url.path))(req)
        world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")
        return resp

    world.gh.routes.insert(0, ("POST", path, hook))


def _jobs_api_forbidden(world: World) -> None:  # forces the missing-permission notice path
    world.gh.routes.insert(
        0,
        (
            "GET",
            re.compile(r"^/repos/acme/coffee/actions/runs/55/attempts/\d+/jobs$"),
            lambda r: httpx.Response(
                403, json={"message": "Resource not accessible"}, headers={"x-accepted-github-permissions": "actions=read"}
            ),
        ),
    )


def test_pr_path_revoked_before_the_pr_comment(world: World, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    _suspend_after_persist(world, monkeypatch)
    jid = world.enqueue()
    world.run()
    assert (world.jobrow(jid)["status"], world.jobrow(jid)["last_error"]) == ("cancelled", "installation_suspended")
    assert world.state.pr_comments.get(12, []) == [] and world.state.check_runs == [] and world.state.writes == []


def test_notice_path_revoked_before_its_pr_comment(world: World, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _jobs_api_forbidden(world)
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    _suspend_after_persist(world, monkeypatch)
    jid = world.enqueue()
    world.run()
    assert (world.jobrow(jid)["status"], world.jobrow(jid)["last_error"]) == ("cancelled", "installation_suspended")
    assert world.state.pr_comments.get(12, []) == [] and world.state.check_runs == [] and world.state.writes == []


def test_notice_path_revoked_between_its_pr_comment_and_check_run(world: World) -> None:
    _jobs_api_forbidden(world)
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    _suspend_after_post(world, PRC)
    jid = world.enqueue()
    world.run()
    assert (world.jobrow(jid)["status"], world.jobrow(jid)["last_error"]) == ("cancelled", "installation_suspended")
    assert len(world.state.pr_comments[12]) == 1 and world.state.check_runs == []  # the comment stays; nothing after
    states = dict(world.owner.execute("SELECT surface, state FROM publication").fetchall())
    assert "check_run" not in states or states["check_run"] != "published"
