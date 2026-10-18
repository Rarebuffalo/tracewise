"""Cross-phase integration (T-701 lifecycle, T-702 recovery, T-705 RLS, queue, worker and publication), offline.

Signed webhooks go through the real FastAPI app on the system plane. Recovery runs on the system plane against
the fake GitHub API. The real worker runs the analyze handler on the RLS-restricted tenant pool (`tracewise_app`).
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import inst, repos_ev, send
from tests.db.test_recovery import Hub, delivery, redeliver, run_obj, sweep
from tracewise.config import Settings
from tracewise.db import repositories as repo
from tracewise.db.session import transaction
from tracewise.web.app import create_app


def _client(pool: Any) -> Any:
    secret = secrets.token_hex(16)
    c = TestClient(create_app(Settings(github_webhook_secret=SecretStr(secret)), pool))
    c.secret = secret  # type: ignore[attr-defined]
    return c


def _jobs(owner: Any) -> dict[int, tuple[str, str | None]]:
    return {r[0]: (r[1], r[2]) for r in owner.execute("SELECT id, status, last_error FROM job ORDER BY id")}


def test_uninstall_then_recovery_and_late_events_never_resurrect_work(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    queued = w.enqueue()
    retrying = w.enqueue(attempt=2)
    owner.execute("UPDATE job SET status='retry_wait', attempts=1 WHERE id=%s", (retrying,))
    orphan = w.enqueue(attempt=3)  # a worker died holding it: running with an expired lease
    owner.execute(
        "UPDATE job SET status='running', attempts=1, locked_by='ghost', locked_until=now() - interval '1 minute' WHERE id=%s",
        (orphan,),
    )
    with _client(pool) as c:
        r = send(c, "installation", inst("deleted"))
        assert r.json() == {"outcome": "processed", "cancelled_jobs": 2}
        assert _jobs(owner)[orphan][0] == "running"  # left to its lease owner / the reaper

        # Recovery after the uninstall: a failed workflow_run delivery and a failed run on GitHub.
        hub = Hub(w.gh)
        hub.deliveries = [delivery(41, "lost-after-uninstall")]
        hub.runs[7] = [run_obj(56, head_sha=head)]
        rd = redeliver(pool, hub)
        assert (rd.redelivered, dict(rd.skipped)) == (0, {"installation_inactive": 1}) and hub.redelivered == []
        sw = sweep(pool, hub)
        assert (sw.completed, sw.repos_swept, sw.enqueued) == (True, 0, 0)

        # GitHub redelivers anyway, and lifecycle events arrive late and out of order.
        body = {
            "action": "completed",
            "installation": {"id": 9},
            "repository": {"id": 7, "full_name": "acme/coffee"},
            "workflow_run": {
                **run_obj(57, head_sha=head),
                "repository": {"id": 7, "full_name": "acme/coffee"},
            },
        }
        assert send(c, "workflow_run", body, "lost-after-uninstall").json()["outcome"] == "installation_inactive"
        for late in (inst("created", repos=[(7, "acme/coffee")]), inst("unsuspend"), inst("new_permissions_accepted")):
            send(c, "installation", late)
        send(c, "installation_repositories", repos_ev("added", [(7, "acme/coffee")]))
    assert owner.execute("SELECT status FROM installation WHERE id=9").fetchone() == ("deleted",)

    w.run(1)  # the reaper reclaims the orphan; the handler re-checks scope on the tenant plane and cancels
    assert not w.worker().run_once()  # nothing else is runnable
    jobs = _jobs(owner)
    assert jobs == {
        queued: ("cancelled", "cancelled_uninstalled"),
        retrying: ("cancelled", "cancelled_uninstalled"),
        orphan: ("cancelled", "cancelled_uninstalled"),
    }
    assert w.state.writes == [] and w.provider_calls == 0
    assert [r.url.path for r in w.gh.requests if r.url.path.startswith("/app/installations/")] == []
    assert owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,)
    assert owner.execute("SELECT count(*) FROM publication").fetchone() == (0,)
    sw2 = sweep(pool, hub)
    assert (sw2.enqueued, owner.execute("SELECT count(*) FROM job").fetchone()) == (0, (3,))


def test_sweep_across_tenants_lifecycle_then_worker_under_rls(pool, tenant_pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    with transaction(pool) as c:
        repo.set_installation_status(c, 10, "active", "other")
        repo.repository_added(c, 70, 10, "other/app")
    hub = Hub(w.gh)
    hub.runs[7] = [run_obj(55, head_sha=head)]
    hub.runs[70] = [run_obj(700, head_sha=head, repo_id=70, name="other/app")]
    s = sweep(pool, hub)  # system plane: crosses tenants by design
    assert (s.completed, s.enqueued, s.repos_swept) == (True, 2, 2)

    # The tenant plane sees each installation's swept rows only.
    for me, other in ((9, 10), (10, 9)):
        with transaction(tenant_pool, tenant=me) as c:
            for t in ("workflow_run", "job", "webhook_delivery", "repository"):
                ids = {r["installation_id"] for r in c.execute(f"SELECT installation_id FROM {t}").fetchall()}  # noqa: S608
                assert ids == {me}, (t, ids)
            assert c.execute("SELECT count(*) AS n FROM job WHERE installation_id = %s", (other,)).fetchone() == {"n": 0}

    with _client(pool) as c:  # installation 10 is suspended before its job runs
        assert send(c, "installation", inst("suspend", 10)).json() == {"outcome": "processed", "cancelled_jobs": 1}
    w.run(1)
    assert not w.worker().run_once()
    statuses = {r[0]: r[1] for r in owner.execute("SELECT installation_id, status FROM job")}
    assert statuses == {9: "succeeded", 10: "cancelled"}
    assert (len(w.all_ccs()), len(w.state.check_runs)) == (1, 1)
    with transaction(tenant_pool, tenant=10) as c:
        assert c.execute("SELECT count(*) AS n FROM analysis").fetchone() == {"n": 0}
        assert c.execute("SELECT count(*) AS n FROM publication").fetchone() == {"n": 0}
    with transaction(tenant_pool, tenant=9) as c:
        assert c.execute("SELECT count(*) AS n FROM analysis").fetchone() == {"n": 1}
        assert c.execute("SELECT count(*) AS n FROM publication WHERE state = 'published'").fetchone() == {"n": 2}
    with transaction(pool) as c:  # unsuspend does not resurrect the cancelled job
        repo.set_installation_status(c, 10, "active")
    assert not w.worker().run_once()
    assert {r[0]: r[1] for r in owner.execute("SELECT installation_id, status FROM job")} == statuses
    s2 = sweep(pool, hub)  # a later sweep: run already recorded, no new job
    assert (s2.enqueued, s2.duplicates) == (0, 2)
