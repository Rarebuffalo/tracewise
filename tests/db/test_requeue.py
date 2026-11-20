"""I-6: operator re-run of one dead analysis job: authenticated, authorised, audited, bounded, atomic, never a second
active attempt. Decided by `tracewise_requeue` (migration 0013). Offline: disposable PostgreSQL; the end-to-end case
uses the fake GitHub and a scripted provider."""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.pg import APP, OPERATOR, OUTSIDER, OWNER, SYSTEM
from tracewise import ops
from tracewise.db.session import Conn, make_pool, transaction
from tracewise.jobs import queue
from tracewise.requeue import DEFAULT_MAX_RERUNS, NotAuthorised, OperatorMismatch, requeue

ACTOR = f"operator:{OPERATOR}"


@pytest.fixture
def op_pool(pg: Any, owner: Any) -> Iterator[ConnectionPool[Conn]]:
    """The operator's OWN login (member of tracewise_operator)."""
    p = make_pool(pg.url(OPERATOR), min_size=1, max_size=8)
    try:
        yield p
    finally:
        p.close()


def dead_job(pool: Any, owner: Any, *, key: str = "analyze:7:55:1", repo_enabled: bool = True) -> int:
    with transaction(pool) as c:
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (9, 'acme', 'active') ON CONFLICT DO NOTHING")
        c.execute(
            "INSERT INTO repository (id, installation_id, full_name, enabled) VALUES (7, 9, 'acme/coffee', %s)"
            " ON CONFLICT (id) DO UPDATE SET enabled = EXCLUDED.enabled",
            (repo_enabled,),
        )
        jid = queue.enqueue(c, kind="analyze", installation_id=9, dedupe_key=key, payload={"repo_id": 7}, run_key="7:55")
    assert jid is not None
    owner.execute(
        "UPDATE job SET status = 'dead', attempts = 3, finished_at = now(), last_error = 'attempts exhausted' WHERE id = %s",
        (jid,),
    )
    return jid


def rq(pool: Any, jid: int, **kw: Any) -> Any:
    return requeue(pool, jid, reason=kw.pop("reason", "transient_outage"), **kw)


def snapshot(owner: Any) -> tuple[Any, ...]:
    return (
        owner.execute("SELECT id, status, attempts, dedupe_key, finished_at FROM job ORDER BY id").fetchall(),
        owner.execute("SELECT count(*) FROM audit_event").fetchone(),
    )


# ------------------------------------------------------------------ identity and authorisation


def test_an_authorised_operator_gets_one_new_linked_attempt_audited_under_their_login(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    r = rq(op_pool, jid)
    assert (r.outcome, r.rerun, r.actor, r.max_reruns) == ("requeued", 1, ACTOR, DEFAULT_MAX_RERUNS)
    new = owner.execute(
        "SELECT status, attempts, deadline_at, dedupe_key, run_key, payload, installation_id FROM job WHERE id = %s",
        (r.new_job_id,),
    ).fetchone()
    assert new == ("queued", 0, None, "analyze:7:55:1:rerun:1", "7:55", {"repo_id": 7}, 9)  # fresh generation, deadline
    assert owner.execute("SELECT status, attempts FROM job WHERE id = %s", (jid,)).fetchone() == ("dead", 3)  # untouched
    actor, action, inst, detail = owner.execute("SELECT actor, action, installation_id, detail FROM audit_event").fetchone()
    assert (actor, action, inst) == (ACTOR, "job.requeued", 9)
    assert detail == {"source_job_id": jid, "new_job_id": r.new_job_id, "reason": "transient_outage", "rerun": 1, "max_reruns": 2}


@pytest.mark.parametrize("role", [SYSTEM, APP, OUTSIDER, OWNER], ids=["system", "tenant", "non-operator", "owner"])
def test_shared_service_roles_and_non_operators_are_refused_without_learning_anything(pg, pool, owner, role) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    before = snapshot(owner)
    p = make_pool(pg.url(role), min_size=1, max_size=1)
    try:
        for target in (jid, 999_999):  # an existing and a missing job: the same refusal, no existence oracle
            with pytest.raises(NotAuthorised) as info:
                rq(p, target)
            assert str(target) not in str(info.value)
    finally:
        p.close()
    assert snapshot(owner) == before


def test_a_service_role_added_to_the_operator_group_is_still_refused(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    owner.execute("GRANT tracewise_operator TO tracewise_system")
    try:
        p = make_pool(pg.url(SYSTEM), min_size=1, max_size=1)
        with pytest.raises(NotAuthorised):
            rq(p, jid)
        p.close()
    finally:
        owner.execute("REVOKE tracewise_operator FROM tracewise_system")


def test_an_unauthenticated_caller_cannot_connect(pg) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(psycopg.OperationalError):  # no such login: PostgreSQL refuses before any SQL runs
        psycopg.connect(pg.url("nobody_at_all"), connect_timeout=5)


def test_a_forged_operator_name_is_refused_and_cannot_reach_the_audit(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    before = snapshot(owner)
    with pytest.raises(OperatorMismatch):
        rq(op_pool, jid, operator="ops_bob")
    assert snapshot(owner) == before
    assert rq(op_pool, jid, operator=OPERATOR).actor == ACTOR  # the matching name is accepted, and changes nothing


def test_set_role_cannot_change_the_recorded_identity(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    """`SET ROLE` changes current_user, not session_user: the audit still names the login that authenticated."""
    owner.execute(f"GRANT tracewise_operator TO {OUTSIDER}")
    owner.execute(f"GRANT {OPERATOR} TO {OUTSIDER}")
    try:
        jid = dead_job(pool, owner)
        with psycopg.connect(pg.url(OUTSIDER)) as c:
            c.execute(f"SET ROLE {OPERATOR}")
            (r,) = c.execute("SELECT tracewise_requeue(%s, 'operator_request', false)", (jid,)).fetchone()
        assert r["actor"] == f"operator:{OUTSIDER}"
    finally:
        owner.execute(f"REVOKE {OPERATOR} FROM {OUTSIDER}")
        owner.execute(f"REVOKE tracewise_operator FROM {OUTSIDER}")


def test_the_tenant_role_cannot_requeue_another_tenants_job(pg, pool, owner) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    with psycopg.connect(pg.url(APP)) as c:
        c.execute("SELECT set_config('tracewise.installation_id', '10', false)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT tracewise_requeue(%s, 'operator_request', false)", (jid,))


# ------------------------------------------------------------------ refusals and bounds


@pytest.mark.parametrize("status", ["queued", "retry_wait", "succeeded", "cancelled"])
def test_only_dead_jobs_can_be_requeued(pool, owner, op_pool, status) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    owner.execute(
        "UPDATE job SET status = %s, finished_at = CASE WHEN %s IN ('succeeded', 'cancelled') THEN now() END WHERE id = %s",
        (status, status, jid),
    )
    assert rq(op_pool, jid).outcome == "not_dead"
    assert owner.execute("SELECT count(*) FROM job").fetchone() == (1,)


def test_a_live_attempt_for_the_same_run_blocks_a_requeue_and_duplicates_are_refused(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    assert rq(op_pool, jid).outcome == "requeued"
    assert rq(op_pool, jid).outcome == "live_job_exists"  # the duplicate request
    assert owner.execute("SELECT count(*) FROM audit_event").fetchone() == (1,)


def test_re_runs_are_bounded_by_the_function_setting(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    for k in range(1, DEFAULT_MAX_RERUNS + 1):
        r = rq(op_pool, jid)
        assert r.outcome == "requeued" and r.rerun == k
        owner.execute("UPDATE job SET status = 'dead', finished_at = now() WHERE id = %s", (r.new_job_id,))
    assert rq(op_pool, jid).outcome == "rerun_limit"
    assert rq(op_pool, r.new_job_id).outcome == "rerun_limit"  # counted against the original, whichever row is named


def test_the_limit_is_owner_configurable_audited_and_cannot_be_raised_by_the_caller(pg, pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)

    def limit(sql: str) -> None:
        owner.execute(
            f"CREATE OR REPLACE FUNCTION tracewise_requeue_max_reruns() RETURNS integer LANGUAGE sql IMMUTABLE "
            f"SET search_path = pg_catalog AS $$ {sql} $$"
        )

    with psycopg.connect(pg.url(OPERATOR)) as c:  # an operator cannot change the policy
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("CREATE OR REPLACE FUNCTION tracewise_requeue_max_reruns() RETURNS integer LANGUAGE sql AS $$ SELECT 9 $$")
    with psycopg.connect(pg.url(OPERATOR)) as c:  # nor shadow it through the search path: the definer's path is fixed
        (r,) = c.execute("SELECT tracewise_requeue(%s, 'operator_request', true)", (jid,)).fetchone()
        assert r["max_reruns"] == DEFAULT_MAX_RERUNS
    limit("SELECT 0")
    try:
        r = rq(op_pool, jid)
        assert (r.outcome, r.max_reruns) == ("rerun_limit", 0)
        limit("SELECT 11")
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            rq(op_pool, jid)
    finally:
        limit("SELECT 2")
    r = rq(op_pool, jid)
    (detail,) = owner.execute("SELECT detail FROM audit_event").fetchone()
    assert r.outcome == "requeued" and detail["max_reruns"] == 2  # the policy in force is part of the record


def test_inactive_installations_disabled_repositories_and_unknown_jobs_are_refused(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner, repo_enabled=False)
    assert rq(op_pool, jid).outcome == "repository_unavailable"
    owner.execute("UPDATE repository SET enabled = true")
    owner.execute("UPDATE installation SET status = 'suspended'")
    assert rq(op_pool, jid).outcome == "installation_inactive"
    assert rq(op_pool, 999_999).outcome == "not_found"
    owner.execute("UPDATE installation SET status = 'active'")
    owner.execute("UPDATE job SET kind = 'other' WHERE id = %s", (jid,))
    assert rq(op_pool, jid).outcome == "unsupported_kind"
    assert owner.execute("SELECT count(*) FROM audit_event").fetchone() == (0,)


def test_the_new_job_never_leaves_the_dead_jobs_installation(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    with transaction(pool) as c:  # repository 8 belongs to another installation
        c.execute("INSERT INTO installation (id, account_login, status) VALUES (10, 'other', 'active')")
        c.execute("INSERT INTO repository (id, installation_id, full_name, enabled) VALUES (8, 10, 'other/x', true)")
    for payload in ('{"repo_id": 8}', '{"repo_id": "7"}', "{}"):
        owner.execute("UPDATE job SET payload = %s::jsonb WHERE id = %s", (payload, jid))
        assert rq(op_pool, jid).outcome == "repository_unavailable"
    owner.execute("UPDATE job SET payload = '{\"repo_id\": 7}' WHERE id = %s", (jid,))
    r = rq(op_pool, jid)
    assert owner.execute("SELECT installation_id FROM job WHERE id = %s", (r.new_job_id,)).fetchone() == (9,)


# ------------------------------------------------------------------ dry run, atomicity, concurrency


def test_dry_run_writes_nothing_and_predicts_the_real_outcome(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    for _ in range(DEFAULT_MAX_RERUNS):
        before = snapshot(owner)
        dry = rq(op_pool, jid, dry_run=True)
        assert snapshot(owner) == before
        real = rq(op_pool, jid)
        assert (dry.outcome, dry.rerun, dry.actor) == ("would_requeue", real.rerun, ACTOR) and real.outcome == "requeued"
        assert rq(op_pool, jid, dry_run=True).outcome == "live_job_exists"
        owner.execute("UPDATE job SET status = 'dead', finished_at = now() WHERE id = %s", (real.new_job_id,))
    assert rq(op_pool, jid, dry_run=True).outcome == rq(op_pool, jid).outcome == "rerun_limit"
    assert owner.execute("SELECT count(*) FROM audit_event").fetchone() == (DEFAULT_MAX_RERUNS,)
    with pytest.raises(ValueError):
        rq(op_pool, jid, reason="because")


def test_a_failure_writing_the_audit_record_leaves_no_new_job(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    before = snapshot(owner)
    owner.execute(
        "CREATE FUNCTION fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit store down'; END $$"
    )
    owner.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_event FOR EACH ROW EXECUTE FUNCTION fail_audit()")
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            rq(op_pool, jid)
    finally:
        owner.execute("DROP TRIGGER fail_audit ON audit_event")
        owner.execute("DROP FUNCTION fail_audit()")
    assert snapshot(owner) == before  # the job insert rolled back with it
    assert rq(op_pool, jid).outcome == "requeued"


def _race(pool: Any, ids: list[int]) -> list[str]:
    gate, out = threading.Barrier(len(ids)), []

    def go(jid: int) -> None:
        gate.wait()
        out.append(rq(pool, jid).outcome)

    threads = [threading.Thread(target=go, args=(j,)) for j in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(out)


def test_concurrent_requeues_of_one_dead_job_create_exactly_one_attempt(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    assert _race(op_pool, [jid] * 4) == ["live_job_exists"] * 3 + ["requeued"]
    assert owner.execute("SELECT count(*) FROM job WHERE status = 'queued'").fetchone() == (1,)
    assert owner.execute("SELECT count(*) FROM audit_event").fetchone() == (1,)


def test_concurrent_requeues_naming_different_dead_rows_of_one_run_create_one_attempt(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    first = rq(op_pool, jid)
    owner.execute("UPDATE job SET status = 'dead', finished_at = now() WHERE id = %s", (first.new_job_id,))
    for _ in range(5):
        outcomes = _race(op_pool, [jid, first.new_job_id, jid])
        assert outcomes.count("requeued") <= 1 and set(outcomes) <= {"requeued", "live_job_exists", "rerun_limit"}
        if "requeued" in outcomes:
            assert "rerun_limit" not in outcomes  # the loser never mislabels a race as the cap
    assert owner.execute("SELECT count(*) FROM job WHERE status = 'queued'").fetchone() == (1,)


def test_a_stale_worker_of_the_dead_job_cannot_write_and_the_new_job_starts_a_fresh_generation(pool, owner, op_pool) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)
    owner.execute("UPDATE job SET locked_by = 'w-old' WHERE id = %s", (jid,))
    new = rq(op_pool, jid).new_job_id
    with transaction(pool) as c:
        assert not queue.Fence(jid, 9, "w-old", 3).owned(c)
        claimed = queue.claim(c, "w-new")
    assert claimed is not None and (claimed.id, claimed.attempts) == (new, 1)


# ------------------------------------------------------------------ CLI and end to end


def test_the_ops_command_uses_the_operators_login_and_exits_by_outcome(pg, pool, owner, capsys) -> None:  # type: ignore[no-untyped-def]
    jid = dead_job(pool, owner)

    def as_role(role: str) -> Any:
        return lambda: make_pool(pg.url(role), min_size=1, max_size=1)

    def system() -> Any:
        raise AssertionError("requeue must not use the system-plane pool")

    argv = ["requeue", "--job-id", str(jid), "--reason", "fixed_permission"]
    assert ops.main(argv, build=system, build_operator=as_role(OPERATOR)) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["outcome"], out["actor"]) == ("requeued", ACTOR)
    assert ops.main(argv, build=system, build_operator=as_role(OPERATOR)) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "live_job_exists"
    assert ops.main(argv, build=system, build_operator=as_role(SYSTEM)) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "not_authorised"}
    assert ops.main([*argv, "--operator", "ops_bob"], build=system, build_operator=as_role(OPERATOR)) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "operator_mismatch"}
    with pytest.raises(SystemExit):
        ops.main(["requeue", "--job-id", str(jid)], build=system, build_operator=as_role(OPERATOR))  # reason required


def test_a_requeued_run_is_analysed_end_to_end(pool, owner, op_pool, server, tmp_path, head, tenant_pool) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.tenant_pool = tenant_pool
    jid = w.enqueue()
    owner.execute(
        "UPDATE job SET status = 'dead', attempts = 3, finished_at = now(), last_error = 'attempts exhausted' WHERE id = %s",
        (jid,),
    )
    r = rq(op_pool, jid)
    assert r.outcome == "requeued"
    assert w.worker("w1").run_once()
    j = w.jobrow(r.new_job_id)
    assert (j["status"], j["attempts"], j["result"]["outcome"]) == ("succeeded", 1, "diagnosed")
    assert w.jobrow(jid)["status"] == "dead"  # the original row keeps its history
