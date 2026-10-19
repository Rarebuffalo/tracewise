"""Phase 13: adversarial recovery and concurrency, offline (fake GitHub, scripted provider, real worker/queue/
publisher on the RLS tenant pool). Idempotency is asserted at the side-effect boundary, i.e. the fake GitHub's
accepted writes, not only queue rows."""

from __future__ import annotations

import re
import threading
from typing import Any

import httpx
import pytest

from tests.db.test_analyze_worker import World, call, final, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import repos_ev
from tracewise.github.publish import Publisher
from tracewise.jobs.handlers import analyze as analyze_mod
from tracewise.web.lifecycle import InstallationRepositoriesEvent, process_installation_repositories


class Crash(BaseException):
    """A process death: not an Exception, so nothing in the worker catches or records it."""


def restart(w: World) -> None:
    """New process: fresh HTTP client and token cache (in-memory state is lost); the database persists."""
    w.http = w.gh.http()
    w.tokens = w.gh.provider(w.http)


def expire_leases(w: World) -> None:
    w.owner.execute("UPDATE job SET locked_until = now() - interval '1 second' WHERE status = 'running'")


def side_effects(w: World) -> tuple[int, int, int, int]:
    return (w.state.count("POST", "cc"), len(w.all_ccs()), w.state.count("POST", "cr"), len(w.state.check_runs))


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]  # noqa: F811
    return World(pool, owner, server, tmp_path / "ws", head)


@pytest.mark.parametrize("stage", ["after_claim", "after_evidence", "during_diagnosis", "during_publication"])
def test_worker_crash_at_each_stage_then_restart_publishes_exactly_once(world: World, monkeypatch, stage) -> None:  # type: ignore[no-untyped-def]
    real_check_run = Publisher.check_run
    armed = {"on": True}

    def boom(*a: Any, **k: Any) -> Any:
        if armed["on"]:
            armed["on"] = False
            raise Crash(stage)
        return None

    if stage == "after_claim":
        real = analyze_mod._load
        monkeypatch.setattr(analyze_mod, "_load", lambda *a, **k: boom() or real(*a, **k))
    elif stage == "after_evidence":
        real_d = analyze_mod.diagnose
        monkeypatch.setattr(analyze_mod, "diagnose", lambda *a, **k: boom() or real_d(*a, **k))
    elif stage == "during_diagnosis":

        def crash_step(req):  # type: ignore[no-untyped-def]
            raise Crash(stage)

        world.scripts = [[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), crash_step], *world.scripts]
    else:  # the commit comment is published and recorded; the process dies before the Check Run
        monkeypatch.setattr(Publisher, "check_run", lambda self, *a, **k: boom() or real_check_run(self, *a, **k))

    jid = world.enqueue()
    with pytest.raises(Crash):
        world.worker("w1").run_once()
    assert world.jobrow(jid)["status"] == "running"  # the dead worker still holds the lease
    restart(world)
    expire_leases(world)
    world.run()  # another process reaps the expired lease, then reclaims and finishes the job
    j = world.jobrow(jid)
    assert j["status"] == "succeeded" and j["attempts"] == 2
    assert side_effects(world) == (1, 1, 1, 1)  # one commit comment, one Check Run: never duplicated
    assert world.pubs()["commit_comment"][0] == "published" and world.pubs()["check_run"][0] == "published"


def test_duplicate_delivery_after_completion_writes_nothing(world: World) -> None:
    from tests.db.test_cross_phase import _client
    from tests.db.test_lifecycle import send
    from tests.db.test_recovery import run_obj

    body = {
        "action": "completed",
        "installation": {"id": 9},
        "repository": {"id": 7, "full_name": "acme/coffee"},
        "workflow_run": {**run_obj(55, head_sha=world.head), "head_branch": "feature"},
    }
    with _client(world.pool) as c:
        assert send(c, "workflow_run", body, "d-1").json()["outcome"] == "enqueued"
        world.run()
        assert side_effects(world) == (1, 1, 1, 1)
        assert send(c, "workflow_run", body, "d-1").json()["outcome"] == "duplicate_delivery"  # same GUID
        assert send(c, "workflow_run", body, "d-2").json()["outcome"] == "duplicate_run"  # GitHub's new GUID
    assert not world.worker().run_once() and side_effects(world) == (1, 1, 1, 1)


def test_retry_exhaustion_ends_dead_and_never_duplicates_the_commit_comment(world: World) -> None:
    world.state.fault("POST", "cr", 502, 502, 502)
    jid = world.enqueue()
    for _ in range(3):
        world.run()
        world.ready(jid)
    j = world.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("dead", 3) and "GitHubRetryable" in j["last_error"]
    assert side_effects(world) == (1, 1, 0, 0)  # commit comment once; the Check Run was never accepted
    assert not world.worker().run_once()  # dead is final: no further attempt


def test_two_workers_racing_for_one_job_publish_once(world: World) -> None:
    jid = world.enqueue()
    barrier = threading.Barrier(2)
    claimed: list[bool] = []

    def go(name: str) -> None:
        w = world.worker(name)
        barrier.wait()
        claimed.append(w.run_once())

    ts = [threading.Thread(target=go, args=(n,)) for n in ("wa", "wb")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert sorted(claimed) == [False, True]
    assert world.jobrow(jid)["status"] == "succeeded" and side_effects(world) == (1, 1, 1, 1)


def test_repository_removed_during_publication_stops_the_remaining_surfaces(world: World) -> None:
    """D-10(a), decided (DECISIONS D-13): a repository removed after the commit comment was accepted gets no Check
    Run; the job ends `cancelled` with a content-free reason (F-2 closed)."""
    cc = re.compile(r"^/repos/acme/coffee/commits/[0-9a-f]{40}/comments$")

    def remove_after(req: httpx.Request) -> httpx.Response:
        for method, pat, h in world.gh.routes:
            if h is not remove_after and method == req.method and pat.search(req.url.path):
                resp = h(req)
                break
        ev = InstallationRepositoriesEvent.model_validate(repos_ev("removed", [(7, "acme/coffee")]))
        process_installation_repositories(world.pool, "rm-pub", ev)
        return resp

    world.gh.routes.insert(0, ("POST", cc, remove_after))
    jid = world.enqueue()
    world.run()
    assert (world.jobrow(jid)["status"], world.jobrow(jid)["last_error"]) == ("cancelled", "repo_not_in_scope")
    assert side_effects(world) == (1, 1, 0, 0)  # commit comment stays; no Check Run after the removal
    assert world.owner.execute("SELECT removed_at IS NOT NULL FROM repository WHERE id = 7").fetchone() == (True,)


def test_purge_alongside_jobs_in_every_state(pool, owner) -> None:  # type: ignore[no-untyped-def]
    from tracewise import retention
    from tracewise.db.session import transaction
    from tracewise.jobs import queue

    with transaction(pool) as c:
        ids = {
            s: queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key=f"k-{s}", payload={})
            for s in ("queued", "running", "retry_wait", "old_done", "recent_done", "old_dead")
        }
    owner.execute("UPDATE job SET created_at = now() - interval '800 days'")  # everything is old by creation
    owner.execute(
        "UPDATE job SET status='running', attempts=1, locked_by='w', locked_until=now() + interval '1 min' WHERE id=%s",
        (ids["running"],),
    )
    owner.execute("UPDATE job SET status='retry_wait', attempts=1 WHERE id=%s", (ids["retry_wait"],))
    owner.execute("UPDATE job SET status='succeeded', finished_at = now() - interval '400 days' WHERE id=%s", (ids["old_done"],))
    owner.execute("UPDATE job SET status='dead', finished_at = now() - interval '366 days' WHERE id=%s", (ids["old_dead"],))
    owner.execute("UPDATE job SET status='succeeded', finished_at = now() - interval '1 day' WHERE id=%s", (ids["recent_done"],))
    s = retention.purge(pool)
    assert s.completed and s.deleted["job"] == 2
    left = {r[0] for r in owner.execute("SELECT dedupe_key FROM job")}
    assert left == {"k-queued", "k-running", "k-retry_wait", "k-recent_done"}  # non-terminal never touched by age
