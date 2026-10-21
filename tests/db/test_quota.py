"""T-703 / FS-QTA-1 / AT-QTA-01: monthly per-installation analysis quota. Offline: fake GitHub, scripted provider.

"Quota 3, 5 failures → 3 analyses, then one 'quota reached' Check Run per day per repo." Over quota: no
investigation, no comments, one neutral Check Run per repository per UTC day. The quota value is an owner setting
(ANALYSIS_QUOTA_MONTHLY); unset means no quota.
"""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import secrets
from typing import Any

import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401
from tracewise.db import repositories as repo
from tracewise.db.session import transaction
from tracewise.jobs import queue

TITLE = "Analysis quota reached"


def enqueue_run(w: World, run_id: int, installation_id: int = 9) -> int:
    j = w.job(1, run_id=run_id, delivery_id=f"d-{run_id}", installation_id=installation_id)
    with transaction(w.pool) as c:
        repo.insert_workflow_run(
            c,
            installation_id=installation_id,
            repo_id=7,
            run_id=run_id,
            attempt=1,
            workflow_id=3,
            head_sha=w.head,
            head_branch="feature",
            head_repo_id=7,
            event=w.event,
            conclusion="failure",
        )
        jid = queue.enqueue(
            c,
            kind="analyze",
            installation_id=installation_id,
            dedupe_key=f"analyze:7:{run_id}:1:{secrets.token_hex(2)}",
            payload=j.model_dump(mode="json"),
            run_key=f"7:{run_id}",
        )
    assert jid is not None
    return jid


@pytest.fixture
def world(pool, owner, server, tmp_path, head) -> World:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head)
    jobs55 = next(h for m, p, h in w.gh.routes if m == "GET" and p.search("/repos/acme/coffee/actions/runs/55/attempts/1/jobs"))
    w.gh.route("GET", r"^/repos/acme/coffee/actions/runs/\d+/attempts/\d+/jobs$", jobs55)  # same failed job for every run
    w.quota = 3
    return w


def quota_runs(w: World) -> list[dict[str, Any]]:
    return [cr for cr in w.state.check_runs if cr["output"]["title"] == TITLE]


def run(w: World, jid: int) -> dict[str, Any]:
    assert w.worker().run_once()
    return w.jobrow(jid)


def test_at_qta_01_three_analyses_then_one_quota_check_run_per_day(world: World) -> None:
    jobs = [enqueue_run(world, 100 + i) for i in range(5)]
    rows = [run(world, j) for j in jobs[:3]]
    comment_writes = [w for w in world.state.writes if w[1] in ("cc", "prc")]
    rows += [run(world, j) for j in jobs[3:]]
    assert [r["result"]["outcome"] for r in rows] == ["diagnosed"] * 3 + ["quota_exceeded"] * 2
    assert all(r["status"] == "succeeded" for r in rows)
    assert world.provider_calls == 3  # no investigation once over quota
    (notice,) = quota_runs(world)  # one per repository per day, not one per run
    assert notice["conclusion"] == "neutral" and notice["external_id"] == "103"
    assert "3" in notice["output"]["summary"]  # names the quota
    # FS-QTA-1: no comments for over-quota runs (the three analysed runs share one write-once commit comment)
    assert [w for w in world.state.writes if w[1] in ("cc", "prc")] == comment_writes


def test_a_new_utc_day_gets_one_new_notice(world: World) -> None:
    for i in range(4):
        run(world, enqueue_run(world, 200 + i))
    assert len(quota_runs(world)) == 1
    world.owner.execute("UPDATE analysis SET created_at = created_at - interval '1 day' WHERE status = 'quota_exceeded'")
    run(world, enqueue_run(world, 210))
    assert len(quota_runs(world)) == 2


def test_last_months_analyses_do_not_count(world: World) -> None:
    for i in range(3):
        run(world, enqueue_run(world, 300 + i))
    world.owner.execute("UPDATE analysis SET created_at = date_trunc('month', now()) - interval '1 hour'")
    assert run(world, enqueue_run(world, 310))["result"]["outcome"] == "diagnosed"


def test_another_installations_analyses_do_not_count(world: World) -> None:
    with transaction(world.pool) as c:
        repo.upsert_installation(c, 10, "other")
    world.owner.execute(
        "INSERT INTO workflow_run (installation_id, repo_id, github_run_id, run_attempt, head_sha, event, conclusion)"
        " SELECT 10, 8, g, 1, %s, 'push', 'failure' FROM generate_series(1, 5) g",
        (world.head,),
    )
    world.owner.execute(
        "INSERT INTO analysis (installation_id, run_pk, status, diagnosis) SELECT 10, id, 'diagnosed', '{}'::jsonb"
        " FROM workflow_run WHERE installation_id = 10"
    )
    assert run(world, enqueue_run(world, 400))["result"]["outcome"] == "diagnosed"


def test_no_quota_configured_means_no_limit(world: World) -> None:
    world.quota = None
    rows = [run(world, enqueue_run(world, 500 + i)) for i in range(4)]
    assert [r["result"]["outcome"] for r in rows] == ["diagnosed"] * 4 and quota_runs(world) == []


def test_revocation_before_the_quota_notice_writes_nothing(world: World) -> None:
    for i in range(3):
        run(world, enqueue_run(world, 600 + i))
    before = list(world.state.writes)
    original = repo.count_monthly_analyses

    def count_then_suspend(*a: Any, **k: Any) -> int:
        n = original(*a, **k)
        world.owner.execute("UPDATE installation SET status = 'suspended' WHERE id = 9")
        return n

    import tracewise.db.repositories as r

    r.count_monthly_analyses = count_then_suspend  # type: ignore[assignment]
    try:
        j = enqueue_run(world, 610)
        row = run(world, j)
    finally:
        r.count_monthly_analyses = original  # type: ignore[assignment]
    assert (row["status"], row["last_error"]) == ("cancelled", "installation_suspended")
    assert world.state.writes == before and quota_runs(world) == []  # D-10: re-checked before the surface


def test_quota_setting_is_validated() -> None:
    from pydantic import ValidationError

    from tracewise.config import Settings

    assert Settings(analysis_quota_monthly=None).analysis_quota_monthly is None
    assert Settings(analysis_quota_monthly=50).analysis_quota_monthly == 50
    with pytest.raises(ValidationError):
        Settings(analysis_quota_monthly=0)


def test_a_retry_of_the_run_that_reached_the_quota_is_not_turned_into_a_quota_notice(world: World) -> None:
    world.quota = 1
    world.state.fault("POST", "cr", 502)  # the analysed run's Check Run fails once: the job retries
    jid = enqueue_run(world, 700)
    assert run(world, jid)["status"] == "retry_wait"
    world.ready(jid)
    row = run(world, jid)
    assert (row["status"], row["result"]["outcome"]) == ("succeeded", "diagnosed")  # not quota_exceeded
    assert world.owner.execute("SELECT status FROM analysis").fetchall() == [("diagnosed",)]
    assert quota_runs(world) == [] and len(world.state.check_runs) == 1
