"""Phase 51: the documented backup procedure (OPERATIONS §8: `pg_dump` before any migration) actually restores a
working, still-isolated database. Two disposable local clusters; no production database.

Source: migrated to head, populated through the runtime roles (two tenants, runs, an analysis, a publication, a
queued job). Backup: `pg_dump -Fc` as the owner. Target: a fresh cluster with the same three roles (as the
deployment provisioning would create them), restored with `pg_restore`. The restored database must be at the same
revision, hold the same rows, keep RLS and grants, keep the definer purge function's pinned search_path, and still
isolate tenants.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.db.test_privilege_matrix import documented
from tests.db.test_privilege_matrix import live as live_privileges
from tests.pg import APP, OWNER, SYSTEM, _bin, ephemeral
from tracewise.db import repositories as repo
from tracewise.db.migrate import head_revision, upgrade
from tracewise.db.session import make_pool, require_system_plane, require_tenant_plane, transaction

SHA = "b" * 40
TABLES = ["installation", "repository", "workflow_run", "analysis", "publication", "job", "webhook_delivery"]


@pytest.fixture(scope="module")
def clusters() -> Iterator[tuple[Any, Any]]:
    src, dst = ephemeral(), ephemeral()
    try:
        yield src, dst
    finally:
        src.stop()
        dst.stop()


def populate(c: Any) -> None:
    upgrade(c.url(OWNER))
    sysp, ten = make_pool(c.url(SYSTEM)), make_pool(c.url(APP))
    try:
        with transaction(sysp) as k:
            for inst in (1, 2):
                repo.set_installation_status(k, inst, "active", f"org{inst}")
                repo.repository_added(k, 10 + inst, inst, f"org{inst}/r")
        for inst in (1, 2):
            with transaction(ten, tenant=inst) as k:
                pk = repo.insert_workflow_run(
                    k,
                    installation_id=inst,
                    repo_id=10 + inst,
                    run_id=500,
                    attempt=1,
                    workflow_id=3,
                    head_sha=SHA,
                    head_branch="main",
                    head_repo_id=10 + inst,
                    event="push",
                    conclusion="failure",
                )
                aid = repo.upsert_analysis(
                    k, installation_id=inst, run_pk=pk, status="inconclusive", category=None, confidence_band=None, diagnosis=None
                )
                row = repo.reserve_publication(
                    k, installation_id=inst, analysis_id=aid, surface="check_run", target_key=repo.check_run_key(10 + inst, 500)
                )
                repo.mark_published(k, row["id"], aid, 7000 + inst)
    finally:
        sysp.close()
        ten.close()


def counts(url: str) -> dict[str, int]:
    with psycopg.connect(url) as k:
        return {t: k.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}  # type: ignore[index]  # noqa: S608


def test_a_pg_dump_backup_restores_a_working_isolated_database(clusters, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    src, dst = clusters
    populate(src)
    dump = tmp_path / "tracewise.dump"
    subprocess.run(  # noqa: S603 - fixed argv, local socket
        [_bin("pg_dump"), "-Fc", "-f", str(dump), "-d", src.url(OWNER)], check=True, capture_output=True
    )
    subprocess.run(  # noqa: S603
        [_bin("pg_restore"), "--exit-on-error", "-d", dst.url(OWNER), str(dump)], check=True, capture_output=True
    )

    assert counts(dst.url(OWNER)) == counts(src.url(OWNER))
    with psycopg.connect(src.url(OWNER)) as a, psycopg.connect(dst.url(OWNER)) as b:
        assert live_privileges(b) == live_privileges(a) == documented()  # grants survive, exactly as documented
    with psycopg.connect(dst.url(OWNER)) as k:
        assert k.execute("SELECT version_num FROM alembic_version").fetchone() == (head_revision(),)
        rls = {r[0] for r in k.execute("SELECT relname FROM pg_class WHERE relrowsecurity AND relkind = 'r'")}
        assert {"installation", "repository", "workflow_run", "analysis", "publication", "job"} <= rls
        cfg = k.execute("SELECT proconfig, prosecdef FROM pg_proc WHERE proname = 'tracewise_purge'").fetchone()
        assert cfg is not None and cfg[1] is True and "search_path=pg_catalog, public, pg_temp" in cfg[0]

    sysp, ten = make_pool(dst.url(SYSTEM)), make_pool(dst.url(APP))
    try:
        require_system_plane(sysp)  # the restored grants still satisfy both role contracts
        require_tenant_plane(ten)
        with transaction(ten, tenant=1) as k:  # tenant isolation survives the restore
            assert k.execute("SELECT count(*) AS n FROM publication").fetchone()["n"] == 1
            assert k.execute("SELECT count(*) AS n FROM workflow_run WHERE installation_id = 2").fetchone()["n"] == 0
        with transaction(ten) as k:  # no tenant context: nothing visible
            assert k.execute("SELECT count(*) AS n FROM workflow_run").fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(ten) as k:
            k.execute("SELECT * FROM recovery_checkpoint")  # still revoked from the tenant role
    finally:
        sysp.close()
        ten.close()
