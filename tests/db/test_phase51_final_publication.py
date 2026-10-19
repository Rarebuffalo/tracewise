"""Phase 51, Batch A: a GitHub retryable error on the genuine final attempt (FS-ERR-1, AT-REL-01).

Rule implemented from the recorded state: `_persist` writes the analysis row before ANY publication surface is
reserved, so "no analysis row for this run attempt" proves that no surface write was attempted by any job attempt.
- Nothing attempted (e.g. GitHub fails while collecting logs on every attempt): the final attempt publishes the
  "could not complete" notice (Check Run, plus a PR comment on PRs; never a commit comment). It cannot contradict
  anything.
- A surface was attempted: a 5xx or timeout may have been applied by GitHub, so a notice could contradict a report
  that is actually visible. No notice is published; the job ends dead and its publication rows show what happened.
  The behaviour wanted for that partial case is an owner decision (docs/DECISIONS.md D-14).
Offline: fake GitHub, scripted provider, disposable PostgreSQL.
"""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401

JOBS = re.compile(r"^/repos/acme/coffee/actions/runs/55/attempts/\d+/jobs$")


def jobs_api_fails(w: World, on_call: Any = None) -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if on_call is not None:
            on_call(calls["n"])
        return httpx.Response(502, json={"message": "Server Error"})

    w.gh.routes.insert(0, ("GET", JOBS, handler))


def run_all(w: World, jid: int, attempts: int = 3) -> None:
    for _ in range(attempts):
        if not w.worker().run_once():
            break
        w.ready(jid)


def notices(w: World) -> list[dict[str, Any]]:
    return [cr for cr in w.state.check_runs if cr["output"]["title"] == "Could not complete the analysis"]


def test_nothing_published_on_the_final_attempt_publishes_the_notice(world: World) -> None:
    jobs_api_fails(world)
    jid = world.enqueue()
    run_all(world, jid)
    j = world.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("dead", 3) and "GitHubRetryable" in (j["last_error"] or "")
    assert len(notices(world)) == 1 and world.all_ccs() == [] and world.provider_calls == 0  # FS-ERR-1
    assert not world.worker().run_once() and len(notices(world)) == 1  # no loop, no duplicate


def test_nothing_published_on_a_pr_also_gets_the_pr_comment(world: World) -> None:
    world.state.commit_pulls[world.head] = [world.state.pr(12, world.head)]
    jobs_api_fails(world)
    jid = world.enqueue()
    run_all(world, jid)
    assert world.jobrow(jid)["status"] == "dead"
    assert len(notices(world)) == 1 and len(world.state.pr_comments[12]) == 1 and world.all_ccs() == []


def test_a_partially_published_report_is_never_contradicted_by_a_notice(world: World) -> None:
    world.state.fault("POST", "cr", 502, 502, 502)  # the commit comment succeeds, the Check Run never does
    jid = world.enqueue()
    run_all(world, jid)
    j = world.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("dead", 3)
    assert len(world.all_ccs()) == 1 and world.state.check_runs == [] and notices(world) == []
    states = dict(world.owner.execute("SELECT surface, state FROM publication").fetchall())
    assert states["commit_comment"] == "published" and states.get("check_run") != "published"  # recorded honestly


def test_first_surface_failing_on_every_attempt_publishes_no_notice(world: World) -> None:
    world.state.fault("POST", "cc", 502, 502, 502)  # each 502 may or may not have been applied by GitHub
    jid = world.enqueue()
    run_all(world, jid)
    assert world.jobrow(jid)["status"] == "dead" and notices(world) == []


def test_an_ambiguous_final_write_is_not_contradicted(world: World) -> None:
    world.state.fault("POST", "cc", 502, 502, "accept_then_timeout")  # the last write landed; we never saw it
    jid = world.enqueue()
    run_all(world, jid)
    assert world.jobrow(jid)["status"] == "dead"
    assert len(world.all_ccs()) == 1 and notices(world) == []  # the visible report stands alone


def test_revocation_before_the_final_notice_cancels_without_writes(world: World) -> None:
    def suspend_on_third(n: int) -> None:
        if n == 3:
            world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")

    jobs_api_fails(world, suspend_on_third)
    jid = world.enqueue()
    run_all(world, jid)
    j = world.jobrow(jid)
    assert (j["status"], j["last_error"]) == ("cancelled", "installation_suspended")
    assert world.state.writes == []  # D-10: the re-check precedes the notice


def test_a_failing_notice_ends_the_job_without_a_loop(world: World) -> None:
    jobs_api_fails(world)
    world.state.fault("POST", "cr", 502)
    jid = world.enqueue()
    run_all(world, jid)
    assert world.jobrow(jid)["status"] == "dead" and notices(world) == []
    assert not world.worker().run_once()


def test_an_explicit_rerun_after_a_final_notice_replaces_it_in_place(world: World) -> None:
    jobs_api_fails(world)
    jid = world.enqueue()
    run_all(world, jid)
    assert len(notices(world)) == 1
    world.gh.routes.pop(0)  # GitHub recovers
    j2 = world.enqueue(attempt=2)  # a re-run on GitHub: a new run attempt, delivered as a new webhook
    world.run()
    assert world.jobrow(j2)["status"] == "succeeded"
    assert len(world.state.check_runs) == 1 and notices(world) == []  # the notice was updated, not duplicated


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]
    return World(pool, owner, server, tmp_path / "ws", head)
