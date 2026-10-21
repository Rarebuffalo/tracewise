"""T-901: earlier analysed failures of a lane, from the existing workflow_run / analysis tables (no new data model).
Tenant plane (RLS), disposable PostgreSQL."""

from __future__ import annotations

from typing import Any

from tracewise.db import repositories as repo
from tracewise.db.session import transaction

SHA = "c" * 40


def seed(
    pool: Any,
    tenant_pool: Any,
    inst: int,
    run_id: int,
    *,
    attempt: int = 1,
    branch: str = "main",
    head_repo: int = 7,
    workflow: int = 3,
    event: str = "push",
    status: str | None = "diagnosed",
) -> None:
    with transaction(pool) as k:
        repo.set_installation_status(k, inst, "active", f"o{inst}")
        repo.repository_added(k, 7 if inst == 9 else 70 + inst, inst, f"o{inst}/r")
    repo_id = 7 if inst == 9 else 70 + inst
    with transaction(tenant_pool, tenant=inst) as k:
        pk = repo.insert_workflow_run(
            k,
            installation_id=inst,
            repo_id=repo_id,
            run_id=run_id,
            attempt=attempt,
            workflow_id=workflow,
            head_sha=SHA,
            head_branch=branch,
            head_repo_id=head_repo,
            event=event,
            conclusion="failure",
        )
        if status is not None:
            repo.upsert_analysis(
                k, installation_id=inst, run_pk=pk, status=status, category=None, confidence_band=None, diagnosis=None
            )


def lane(tenant_pool: Any, inst: int = 9, **over: Any) -> list[dict[str, Any]]:
    args: dict[str, Any] = dict(
        installation_id=inst, repo_id=7, workflow_id=3, branch="main", head_repo_id=7, events=("push",), before_run_id=100
    )
    args.update(over)
    with transaction(tenant_pool, tenant=inst) as k:
        return repo.prior_lane_analyses(k, **args)


def test_newest_first_with_rerun_attempts_and_the_current_run_excluded(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, tenant_pool, 9, 10)
    seed(pool, tenant_pool, 9, 20)
    seed(pool, tenant_pool, 9, 20, attempt=2, status="inconclusive")
    seed(pool, tenant_pool, 9, 100)  # the current run itself
    rows = lane(tenant_pool)
    assert [(r["run_id"], r["attempt"], r["status"]) for r in rows] == [
        (20, 2, "inconclusive"),
        (20, 1, "diagnosed"),
        (10, 1, "diagnosed"),
    ]


def test_other_lanes_are_excluded(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, tenant_pool, 9, 11, branch="dev")
    seed(pool, tenant_pool, 9, 12, head_repo=501)  # a fork's branch of the same name
    seed(pool, tenant_pool, 9, 13, workflow=4)
    seed(pool, tenant_pool, 9, 14, event="schedule")
    seed(pool, tenant_pool, 9, 15)
    assert [r["run_id"] for r in lane(tenant_pool)] == [15]
    assert [r["run_id"] for r in lane(tenant_pool, events=("pull_request", "pull_request_target"))] == []


def test_a_run_without_an_analysis_is_listed_with_no_status(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, tenant_pool, 9, 30, status=None)
    assert [(r["run_id"], r["status"]) for r in lane(tenant_pool)] == [(30, None)]


def test_empty_history_and_bounded_limit(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    assert lane(tenant_pool) == []
    for rid in range(1, 8):
        seed(pool, tenant_pool, 9, rid)
    assert len(lane(tenant_pool, limit=3)) == 3 and len(lane(tenant_pool, limit=10_000)) == 7


def test_another_installations_lane_is_never_visible(pool, tenant_pool, owner) -> None:  # type: ignore[no-untyped-def]
    seed(pool, tenant_pool, 9, 40)
    seed(pool, tenant_pool, 10, 41)
    assert [r["run_id"] for r in lane(tenant_pool)] == [40]
    with transaction(tenant_pool, tenant=10) as k:  # asking for installation 9's lane from tenant 10: nothing
        assert (
            repo.prior_lane_analyses(
                k, installation_id=9, repo_id=7, workflow_id=3, branch="main", head_repo_id=7, events=("push",), before_run_id=100
            )
            == []
        )
