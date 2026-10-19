"""Phase 50, Batch B: repository transfer between installations (migration 0010).

Before 0010 the run, publication and failure-signature keys were global. After a repository moved to another
installation, the new tenant's write for the same PR, commit or run hit the old tenant's RLS-hidden row: an
AssertionError (publication) or an RLS USING violation (run), retried until the job went dead. Keys are now per
installation. Disposable local PostgreSQL only.
"""

# ruff: noqa: F811  (pytest fixtures `server` and `head` are imported, then requested by name)
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401
from tests.pg import APP, OWNER, SYSTEM, ephemeral
from tracewise.db import repositories as repo
from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import make_pool, transaction

SHA = "a" * 40


def persist(tenant_pool: Any, inst: int, run: int, attempt: int, repo_id: int = 11) -> tuple[int, int]:
    with transaction(tenant_pool, tenant=inst) as k:
        pk = repo.find_workflow_run(k, inst, repo_id, run, attempt) or repo.insert_workflow_run(
            k,
            installation_id=inst,
            repo_id=repo_id,
            run_id=run,
            attempt=attempt,
            workflow_id=5,
            head_sha=SHA,
            head_branch="main",
            head_repo_id=repo_id,
            event="pull_request",
            conclusion="failure",
        )
        aid = repo.upsert_analysis(
            k, installation_id=inst, run_pk=pk, status="inconclusive", category=None, confidence_band=None, diagnosis=None
        )
    return pk, aid


def publish_pr(tenant_pool: Any, inst: int, aid: int, gid: int) -> dict[str, Any]:
    with transaction(tenant_pool, tenant=inst) as k:
        row = repo.reserve_publication(
            k, installation_id=inst, analysis_id=aid, surface="pr_comment", target_key=repo.pr_comment_key(11, 7, 5)
        )
        if row["state"] != "published":
            repo.mark_published(k, row["id"], aid, gid)
        return dict(row)


@pytest.fixture
def two_tenants(pool: Any) -> None:
    with transaction(pool) as k:
        repo.set_installation_status(k, 1, "active", "a")
        repo.set_installation_status(k, 2, "active", "b")
        repo.repository_added(k, 11, 1, "a/r")


def transfer(pool: Any) -> None:
    with transaction(pool) as k:
        repo.repository_added(k, 11, 2, "b/r")  # GitHub transfer: the repository appears under installation 2


def test_new_installation_publishes_on_the_same_pr_after_a_transfer(pool, tenant_pool, owner, two_tenants) -> None:  # type: ignore[no-untyped-def]
    _, a1 = persist(tenant_pool, 1, 100, 1)
    r1 = publish_pr(tenant_pool, 1, a1, 999)
    transfer(pool)
    _, a2 = persist(tenant_pool, 2, 200, 1)
    r2 = publish_pr(tenant_pool, 2, a2, 1001)  # previously: AssertionError, retried until dead
    assert r2["id"] != r1["id"] and r2["installation_id"] == 2
    rows = owner.execute("SELECT installation_id, github_id, state FROM publication ORDER BY id").fetchall()
    assert rows == [(1, 999, "published"), (2, 1001, "published")]  # the old tenant's row is untouched


def test_a_pre_transfer_run_seen_again_by_the_new_installation_gets_its_own_row(pool, tenant_pool, owner, two_tenants) -> None:  # type: ignore[no-untyped-def]
    pk1, _ = persist(tenant_pool, 1, 100, 1)
    transfer(pool)
    pk2, _ = persist(tenant_pool, 2, 100, 1)  # previously: RLS USING violation on the hidden row
    assert pk1 != pk2
    owned = owner.execute("SELECT id, installation_id FROM workflow_run ORDER BY id").fetchall()
    assert owned == [(pk1, 1), (pk2, 2)]  # historical rows keep their original tenant


def test_repeated_deliveries_and_publication_retries_within_one_installation_stay_single(
    pool, tenant_pool, owner, two_tenants
) -> None:  # type: ignore[no-untyped-def]
    a = [persist(tenant_pool, 1, 100, 1) for _ in range(3)]
    assert len({pk for pk, _ in a}) == 1 and len({aid for _, aid in a}) == 1
    first = publish_pr(tenant_pool, 1, a[0][1], 999)
    again = publish_pr(tenant_pool, 1, a[0][1], 999)
    assert first["id"] == again["id"]
    assert owner.execute("SELECT count(*) FROM publication").fetchone() == (1,)
    assert owner.execute("SELECT count(*) FROM workflow_run").fetchone() == (1,)


def test_a_tenant_cannot_write_or_see_another_installations_rows(pool, tenant_pool, owner, two_tenants) -> None:  # type: ignore[no-untyped-def]
    _, a1 = persist(tenant_pool, 1, 100, 1)
    publish_pr(tenant_pool, 1, a1, 999)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(tenant_pool, tenant=2) as k:
        repo.insert_workflow_run(
            k,
            installation_id=1,  # forged installation id
            repo_id=11,
            run_id=300,
            attempt=1,
            workflow_id=5,
            head_sha=SHA,
            head_branch="main",
            head_repo_id=11,
            event="push",
            conclusion="failure",
        )
    with transaction(tenant_pool, tenant=2) as k:
        assert repo.find_workflow_run(k, 2, 11, 100, 1) is None
        assert repo.find_workflow_run(k, 1, 11, 100, 1) is None  # even when asking for the other tenant explicitly
        assert k.execute("SELECT count(*) AS n FROM publication").fetchone()["n"] == 0


def test_signature_upsert_is_per_installation(pool, tenant_pool, owner, two_tenants) -> None:  # type: ignore[no-untyped-def]
    pk1, _ = persist(tenant_pool, 1, 100, 1)
    transfer(pool)
    pk2, _ = persist(tenant_pool, 2, 200, 1)
    for inst, pk in ((1, pk1), (2, pk2)):
        with transaction(tenant_pool, tenant=inst) as k:
            n = repo.record_signature(
                k, repo_id=11, installation_id=inst, fingerprint="0123456789abcdef", normalized_message="m", run_pk=pk
            )
        assert n == 1
    assert owner.execute("SELECT installation_id FROM failure_signature ORDER BY 1").fetchall() == [(1,), (2,)]


def test_a_stale_job_from_the_previous_installation_ends_without_writes(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]
    w = World(pool, owner, server, tmp_path / "ws", head)  # installation 9 owns repository 7
    jid = w.enqueue()
    with transaction(pool) as k:
        repo.set_installation_status(k, 10, "active", "newowner")
        repo.repository_added(k, 7, 10, "newowner/coffee")  # transferred before the job ran
    w.run()
    j = w.jobrow(jid)
    # The established _load contract (test_16): a repository that belongs to another installation is a permanent
    # mismatch. No retries, no GitHub write, never a crash or an AssertionError.
    assert j["status"] == "dead" and "not part of the job's installation" in j["last_error"] and j["attempts"] == 1
    assert w.state.writes == []


# ------------------------------------------------------------------ the migration itself


@pytest.fixture(scope="module")
def cluster() -> Iterator[Any]:
    c = ephemeral()
    try:
        yield c
    finally:
        c.stop()


def _seed_at_0009(c: Any) -> None:
    with psycopg.connect(c.url(OWNER), autocommit=True) as k:
        k.execute("INSERT INTO installation (id, account_login, status) VALUES (1, 'a', 'active'), (2, 'b', 'active')")
        k.execute("INSERT INTO repository (id, installation_id, full_name) VALUES (11, 1, 'a/r')")
        k.execute(
            "INSERT INTO workflow_run (installation_id, repo_id, github_run_id, run_attempt, head_sha, event, conclusion)"
            " VALUES (1, 11, 100, 1, %s, 'push', 'failure')",
            (SHA,),
        )
        k.execute("INSERT INTO analysis (installation_id, run_pk, status) SELECT 1, id, 'inconclusive' FROM workflow_run")
        k.execute(
            "INSERT INTO publication (installation_id, analysis_id, surface, target_key, github_id, state)"
            " SELECT 1, id, 'pr_comment', '11:pr7:5', 999, 'published' FROM analysis"
        )


def test_migration_preserves_data_and_refuses_a_lossy_downgrade(cluster) -> None:  # type: ignore[no-untyped-def]
    url = cluster.url(OWNER)
    upgrade(url, "0009")
    _seed_at_0009(cluster)
    with psycopg.connect(url) as k:
        before = k.execute("SELECT installation_id, target_key, github_id, state FROM publication").fetchall()
    upgrade(url, "head")
    with psycopg.connect(url, autocommit=True) as k:
        assert k.execute("SELECT installation_id, target_key, github_id, state FROM publication").fetchall() == before
        cons = {
            r[0]
            for r in k.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid IN "
                "('workflow_run'::regclass, 'publication'::regclass, 'failure_signature'::regclass)"
            )
        }
        assert {"workflow_run_installation_run_key", "publication_installation_target_key", "failure_signature_pkey"} <= cons
        # After a transfer, installation 2 legitimately holds the same old key: a downgrade would have to lose data.
        k.execute(
            "INSERT INTO workflow_run (installation_id, repo_id, github_run_id, run_attempt, head_sha, event, conclusion)"
            " VALUES (2, 11, 100, 1, %s, 'push', 'failure')",
            (SHA,),
        )
    with pytest.raises(Exception, match="downgrade 0010 refused"):
        downgrade(url, "0009")
    with psycopg.connect(url, autocommit=True) as k:
        assert k.execute("SELECT count(*) FROM workflow_run").fetchone() == (2,)  # nothing was deleted
        k.execute("DELETE FROM workflow_run WHERE installation_id = 2")  # the operator resolves it explicitly
    downgrade(url, "0009")  # now reversible, data intact
    with psycopg.connect(url) as k:
        assert k.execute("SELECT installation_id, target_key, github_id, state FROM publication").fetchall() == before
    upgrade(url, "head")


def test_runtime_pools_work_on_the_migrated_cluster(cluster) -> None:  # type: ignore[no-untyped-def]
    upgrade(cluster.url(OWNER), "head")
    sysp, ten = make_pool(cluster.url(SYSTEM)), make_pool(cluster.url(APP))
    try:
        with transaction(sysp) as k:
            repo.set_installation_status(k, 3, "active", "c")
            repo.repository_added(k, 33, 3, "c/r")
        pk, aid = persist(ten, 3, 7, 1, repo_id=33)
        assert pk > 0 and aid > 0
    finally:
        sysp.close()
        ten.close()
