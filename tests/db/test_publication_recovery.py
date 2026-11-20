"""F1 / D-14: a validated diagnosis whose publication did not complete is published by the next attempt (or an
operator requeue) instead of being investigated again, never erased, and never left invisible. Offline: disposable
PostgreSQL, fake GitHub, scripted provider."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

from typing import Any

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_attempt_fencing import SLOW_BEAT, make_world
from tests.pg import OPERATOR
from tracewise import ops
from tracewise.db.session import make_pool
from tracewise.requeue import requeue


def world(pool: Any, owner: Any, server: Any, tmp_path: Any, head: str, tenant_pool: Any) -> World:
    return make_world(pool, owner, server, tmp_path, head, tenant_pool)


def fail_check_runs(w: World, n: int) -> None:
    w.state.fault("POST", "cr", *([503] * n))


def run(w: World, jid: int) -> dict[str, Any]:
    w.owner.execute("UPDATE job SET run_after = now() WHERE id = %s", (jid,))
    assert w.worker("w", heartbeat_s=SLOW_BEAT).run_once()
    return w.jobrow(jid)


def diagnosis(owner: Any) -> Any:
    return owner.execute("SELECT status, diagnosis IS NOT NULL, publish_result IS NOT NULL FROM analysis").fetchone()


def test_a_retry_after_the_work_deadline_publishes_the_diagnosis_without_investigating(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 1)
    assert run(w, jid)["status"] == "retry_wait"
    assert diagnosis(owner) == ("diagnosed", True, False)  # diagnosed and persisted, publication incomplete
    reads = len(w.gh.calls("GET", r"/actions/"))
    # Only 30 s of the job remain: the work deadline (less the 60 s reserve) has passed.
    owner.execute("UPDATE job SET deadline_at = now() + interval '30 seconds' WHERE id = %s", (jid,))
    j = run(w, jid)
    assert (j["status"], j["result"]["outcome"], j["result"]["resumed"]) == ("succeeded", "diagnosed", True)
    assert len(w.gh.calls("GET", r"/actions/")) == reads and w.provider_calls == 1  # no collection, no model call
    assert w.state.count("POST", "cr") == 1 and len(w.all_ccs()) == 1  # completed, nothing duplicated
    assert diagnosis(owner) == ("diagnosed", True, True)


def test_an_attempt_past_the_job_deadline_publishes_the_pending_report_instead_of_a_notice(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    """Before F1 this path published "could not complete" and overwrote the valid diagnosis with an empty row."""
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 1)
    run(w, jid)
    owner.execute("UPDATE job SET deadline_at = now() - interval '1 second' WHERE id = %s", (jid,))
    j = run(w, jid)
    assert (j["status"], j["result"]["outcome"]) == ("succeeded", "diagnosed")
    (cr,) = w.state.check_runs
    assert "could not complete" not in cr["output"]["title"].lower()
    assert diagnosis(owner) == ("diagnosed", True, True)


def test_a_completed_analysis_is_never_overwritten_by_a_late_notice(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    assert run(w, jid)["status"] == "succeeded"
    # Lost completion, then claimed after the deadline: nothing is pending, and nothing may replace the analysis.
    owner.execute(
        "UPDATE job SET status = 'retry_wait', finished_at = NULL, deadline_at = now() - interval '1 second' WHERE id = %s",
        (jid,),
    )
    j = run(w, jid)
    assert j["status"] == "dead"
    assert diagnosis(owner) == ("diagnosed", True, True)  # before F1: ('could_not_complete', False, False)
    assert w.state.count("POST", "cr") == 1


def test_a_publication_that_keeps_failing_is_visible_and_an_operator_requeue_completes_it(  # type: ignore[no-untyped-def]
    pg, pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 3)
    for _ in range(3):
        j = run(w, jid)
    assert j["status"] == "dead" and w.state.check_runs == []
    owner.execute("UPDATE analysis SET updated_at = now() - interval '1 hour'")
    r = ops.report(pool)
    assert r["publication_incomplete"]["analyses"] == 1  # discoverable, never an invisible terminal state
    assert r["queue"]["running_lease_expired"] == 0 and r["jobs"]["by_status"].get("dead") == 1
    op = make_pool(pg.url(OPERATOR), min_size=1, max_size=1)
    try:
        rq = requeue(op, jid, reason="transient_outage")
    finally:
        op.close()
    assert rq.outcome == "requeued"
    j = run(w, rq.new_job_id)
    assert (j["status"], j["result"]["resumed"]) == ("succeeded", True)
    assert w.provider_calls == 1 and w.state.count("POST", "cr") == 1  # published once, never re-investigated
    assert ops.report(pool)["publication_incomplete"]["analyses"] == 0


def test_a_record_that_no_longer_validates_is_investigated_afresh(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 1)
    run(w, jid)
    owner.execute('UPDATE analysis SET diagnosis = diagnosis || \'{"status": "not-a-status"}\'')
    j = run(w, jid)
    assert j["status"] == "succeeded" and "resumed" not in j["result"] and w.provider_calls == 2


def test_a_changed_pr_association_is_never_published_to_from_the_old_report(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool, caplog
) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    jid = w.enqueue()
    w.state.fault("POST", "prc", 503)  # the PR comment fails once: the analysis (for PR 12) stays pending
    assert run(w, jid)["status"] == "retry_wait" and w.state.pr_comments[12] == []
    w.state.commit_pulls[w.head] = [w.state.pr(13, w.head)]  # PR 12 closed, the commit is now in PR 13
    j = run(w, jid)
    assert j["status"] == "succeeded" and "resumed" not in j["result"] and w.provider_calls == 2  # investigated afresh
    assert w.state.pr_comments[12] == [] and len(w.state.pr_comments[13]) == 1
    assert any(getattr(r, "tw", {}).get("reason") == "association_changed" for r in caplog.records)


def test_a_rerun_of_the_workflow_never_reuses_the_previous_attempts_pending_report(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 1)
    run(w, jid)  # run attempt 1: diagnosed, publication pending
    owner.execute("UPDATE job SET status = 'dead', finished_at = now() WHERE id = %s", (jid,))
    jid2 = w.enqueue(attempt=2)  # the user re-ran the workflow: a new run attempt
    j = run(w, jid2)
    assert j["status"] == "succeeded" and "resumed" not in j["result"] and w.provider_calls == 2
    pending = owner.execute(
        "SELECT w.run_attempt FROM analysis a JOIN workflow_run w ON w.id = a.run_pk WHERE a.publish_result IS NULL"
    ).fetchall()
    assert pending == [(1,)]  # attempt 1's report stays its own; only its own job or a requeue may resume it


def test_a_record_for_another_commit_is_never_resumed(pool, owner, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    jid = w.enqueue()
    fail_check_runs(w, 1)
    run(w, jid)
    owner.execute("UPDATE analysis SET diagnosis = jsonb_set(diagnosis, '{run,head_sha}', to_jsonb(%s::text))", ("b" * 40,))
    j = run(w, jid)
    assert j["status"] == "succeeded" and "resumed" not in j["result"] and w.provider_calls == 2


def test_a_removed_pr_association_is_never_published_to_from_the_old_report(  # type: ignore[no-untyped-def]
    pool, owner, server, tmp_path, head, tenant_pool
) -> None:
    w = world(pool, owner, server, tmp_path, head, tenant_pool)
    w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    jid = w.enqueue()
    w.state.fault("POST", "prc", 503)
    assert run(w, jid)["status"] == "retry_wait"
    w.state.commit_pulls[w.head] = []  # the PR was closed and the commit is in no PR now
    j = run(w, jid)
    assert j["status"] == "succeeded" and "resumed" not in j["result"] and w.provider_calls == 2
    assert w.state.pr_comments[12] == [] and len(w.all_ccs()) == 1  # D-4: the commit comment, never the old PR
