"""T-701 installation lifecycle (FS-INS-3, FS-INS-4; AT-INS-03, AT-INS-04), offline: signed webhooks through
the real FastAPI app, a disposable Postgres, and the real worker with the fake GitHub API."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.db.test_analyze_worker import World, call, final, head, server  # noqa: F401 - module fixtures
from tests.github_fake import jresp
from tracewise.config import Settings
from tracewise.contracts import WorkflowRunEvent
from tracewise.db.session import transaction
from tracewise.jobs import queue
from tracewise.web.app import create_app
from tracewise.web.ingest import ingest_workflow_run
from tracewise.web.lifecycle import InstallationEvent, process_installation

SHA = "e" * 40


@pytest.fixture
def client(pool) -> Any:  # type: ignore[no-untyped-def]
    secret = secrets.token_hex(16)
    with TestClient(create_app(Settings(github_webhook_secret=SecretStr(secret)), pool)) as c:
        c.secret = secret  # type: ignore[attr-defined]
        yield c


def send(c: Any, event: str, body: dict[str, Any], delivery: str | None = None) -> Any:
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(c.secret.encode(), raw, hashlib.sha256).hexdigest()
    return c.post(
        "/webhooks/github",
        content=raw,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig, "X-GitHub-Delivery": delivery or secrets.token_hex(8)},
    )


def inst(action: str, iid: int = 9, repos: list[tuple[int, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"action": action, "installation": {"id": iid, "account": {"login": "acme"}}}
    if repos is not None:
        body["repositories"] = [{"id": i, "full_name": n} for i, n in repos]
    return body


def repos_ev(action: str, ids: list[tuple[int, str]], iid: int = 9) -> dict[str, Any]:
    key = "repositories_added" if action == "added" else "repositories_removed"
    return {"action": action, "installation": {"id": iid}, key: [{"id": i, "full_name": n} for i, n in ids]}


def failure(repo_id: int = 7, iid: int = 9, run_id: int = 55, name: str = "acme/app") -> dict[str, Any]:
    r = {"id": repo_id, "full_name": name}
    return {
        "action": "completed",
        "installation": {"id": iid},
        "repository": r,
        "workflow_run": {
            "id": run_id,
            "run_attempt": 1,
            "workflow_id": 3,
            "head_sha": SHA,
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
            "repository": r,
            "head_repository": r,
        },
    }


def q(owner: Any, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    return owner.execute(sql, args).fetchall()  # type: ignore[no-any-return]


def enqueue(pool: Any, iid: int, repo_id: int, key: str, status: str = "queued", owner: Any = None) -> int:
    with transaction(pool) as c:
        jid = queue.enqueue(c, kind="analyze", installation_id=iid, dedupe_key=key, payload={"repo_id": repo_id}, run_key=key)
    assert jid is not None
    if status != "queued":
        owner.execute("UPDATE job SET status=%s WHERE id=%s", (status, jid))
    return jid


def test_created_grants_repositories_and_is_idempotent(client, owner) -> None:  # type: ignore[no-untyped-def]
    body = inst("created", repos=[(7, "acme/app"), (8, "acme/lib")])
    r1 = send(client, "installation", body, "d-1")
    r2 = send(client, "installation", body, "d-1")
    assert (r1.json()["outcome"], r2.json()["outcome"]) == ("processed", "duplicate_delivery")
    assert q(owner, "SELECT id, status, account_login FROM installation") == [(9, "active", "acme")]
    assert q(owner, "SELECT id, installation_id, removed_at FROM repository ORDER BY id") == [(7, 9, None), (8, 9, None)]
    assert q(owner, "SELECT outcome FROM webhook_delivery") == [("processed",)]
    assert q(owner, "SELECT action FROM audit_event") == [("installation.created",)]


def test_suspend_stops_new_jobs_and_unsuspend_restores_without_resurrection(client, owner, pool) -> None:  # type: ignore[no-untyped-def]
    send(client, "installation", inst("created", repos=[(7, "acme/app")]))
    queued = enqueue(pool, 9, 7, "a")
    waiting = enqueue(pool, 9, 7, "b", "retry_wait", owner)
    other = enqueue(pool, 10, 70, "c")
    with transaction(pool) as c:
        running = queue.claim(c, "w1")  # claims the oldest ready job
    assert running is not None
    r = send(client, "installation", inst("suspend"))
    assert r.json() == {"outcome": "processed", "cancelled_jobs": 1}
    states = dict(q(owner, "SELECT id, status FROM job"))
    assert states[waiting] == "cancelled" and states[other] == "queued" and states[running.id] == "running"
    assert queued == running.id  # the running one is left to its lease owner (it re-checks before writing)
    assert send(client, "workflow_run", failure()).json()["outcome"] == "installation_inactive"
    assert send(client, "installation", inst("unsuspend")).json()["outcome"] == "processed"
    assert q(owner, "SELECT status FROM installation WHERE id=9") == [("active",)]
    assert dict(q(owner, "SELECT id, status FROM job"))[waiting] == "cancelled"  # never resurrected
    assert send(client, "workflow_run", failure(run_id=56)).json()["outcome"] == "enqueued"


def test_deleted_schedules_purge_cancels_pending_and_is_terminal(client, owner, pool) -> None:  # type: ignore[no-untyped-def]
    send(client, "installation", inst("created", repos=[(7, "acme/app")]))
    jid = enqueue(pool, 9, 7, "a")
    assert send(client, "installation", inst("deleted")).json() == {"outcome": "processed", "cancelled_jobs": 1}
    status, days = q(owner, "SELECT status, extract(epoch FROM purge_after - deleted_at) / 86400 FROM installation")[0]
    assert status == "deleted" and round(float(days)) == 7  # FS-INS-3 / AT-INS-03: purge scheduled
    assert q(owner, "SELECT status, last_error FROM job WHERE id=%s", jid) == [("cancelled", "cancelled_uninstalled")]
    first = q(owner, "SELECT deleted_at FROM installation")[0][0]
    send(client, "installation", inst("deleted"))  # replayed with a new delivery id: idempotent
    for late in (inst("created", repos=[(7, "acme/app")]), inst("unsuspend")):
        send(client, "installation", late)  # out-of-order: must not resurrect
    assert q(owner, "SELECT status, deleted_at FROM installation") == [("deleted", first)]
    r = send(client, "installation_repositories", repos_ev("added", [(9, "acme/x")]))
    assert r.json() == {"outcome": "processed", "cancelled_jobs": 0}  # recorded, but a no-op for a deleted installation
    assert q(owner, "SELECT count(*) FROM repository WHERE id=9") == [(0,)]
    assert send(client, "workflow_run", failure()).json()["outcome"] == "installation_inactive"


def test_ins04_removed_repo_then_failure_is_repo_not_in_scope(client, owner, pool) -> None:  # type: ignore[no-untyped-def]
    send(client, "installation", inst("created", repos=[(7, "acme/app"), (8, "acme/lib")]))
    j7 = enqueue(pool, 9, 7, "a")
    j8 = enqueue(pool, 9, 8, "b")
    assert send(client, "installation_repositories", repos_ev("removed", [(7, "acme/app")])).json()["cancelled_jobs"] == 1
    states = dict(q(owner, "SELECT id, status FROM job"))
    assert (states[j7], states[j8]) == ("cancelled", "queued")
    r = send(client, "workflow_run", failure(), "late-1")
    assert r.json()["outcome"] == "repo_not_in_scope"
    assert q(owner, "SELECT outcome FROM webhook_delivery WHERE delivery_id='late-1'") == [("repo_not_in_scope",)]
    assert q(owner, "SELECT count(*) FROM job WHERE status='queued' AND (payload->>'repo_id')::int=7") == [(0,)]
    send(client, "installation_repositories", repos_ev("added", [(7, "acme/app")]))
    assert send(client, "workflow_run", failure(run_id=57)).json()["outcome"] == "enqueued"


def test_removal_only_touches_owned_repos_and_disabled_flag_survives(client, owner) -> None:  # type: ignore[no-untyped-def]
    send(client, "installation", inst("created", repos=[(7, "acme/app")]))
    send(client, "installation", inst("created", iid=10, repos=[(70, "other/app")]))
    send(client, "installation_repositories", repos_ev("removed", [(70, "other/app")], iid=9))  # not 9's repo
    assert q(owner, "SELECT removed_at FROM repository WHERE id=70") == [(None,)]
    owner.execute("UPDATE repository SET enabled=false WHERE id=7")
    send(client, "installation_repositories", repos_ev("removed", [(7, "acme/app")]))
    send(client, "installation_repositories", repos_ev("added", [(7, "acme/app")]))
    assert q(owner, "SELECT enabled, removed_at FROM repository WHERE id=7") == [(False, None)]
    assert send(client, "workflow_run", failure()).json()["outcome"] == "repo_disabled"


@pytest.mark.parametrize(
    ("event", "body"),
    [
        ("installation", {"action": "exploded", "installation": {"id": 9}}),
        ("installation", {"action": "created"}),
        ("installation", {"action": "created", "installation": {"id": -1}}),
        (
            "installation_repositories",
            {"action": "added", "installation": {"id": 9}, "repositories_added": [{"id": 1, "full_name": "../../etc"}]},
        ),
    ],
)
def test_invalid_lifecycle_payloads_change_nothing(client, owner, event, body) -> None:  # type: ignore[no-untyped-def]
    r = send(client, event, body, "bad-1")
    assert (r.status_code, r.json()["outcome"]) == (400, "invalid_payload")
    assert q(owner, "SELECT count(*) FROM installation") == [(0,)] and q(owner, "SELECT count(*) FROM repository") == [(0,)]
    assert q(owner, "SELECT outcome FROM webhook_delivery") == [("rejected",)]


def test_unhandled_action_is_recorded_ignored(client, owner) -> None:  # type: ignore[no-untyped-def]
    assert send(client, "installation", inst("new_permissions_accepted")).json()["outcome"] == "ignored"
    assert q(owner, "SELECT count(*) FROM installation") == [(0,)]


def test_stale_queued_job_is_cancelled_before_any_work(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    jid = w.enqueue()
    process_installation(pool, "del-1", InstallationEvent.model_validate(inst("deleted")))
    assert q(owner, "SELECT status, last_error FROM job WHERE id=%s", jid) == [("cancelled", "cancelled_uninstalled")]
    assert not w.worker().run_once()  # nothing to claim
    assert w.state.writes == [] and w.provider_calls == 0


def test_ins03_uninstalled_mid_job_no_publication(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    def uninstall_during_investigation(req):  # type: ignore[no-untyped-def]
        process_installation(pool, "del-mid", InstallationEvent.model_validate(inst("deleted")))
        return final()

    w = World(
        pool,
        owner,
        server,
        tmp_path / "ws",
        head,
        scripts=[[call("read_file", "r", path="coffee_shop/pricing.py", start=30, end=41), uninstall_during_investigation]],
    )
    jid = w.enqueue()
    assert w.worker().run_once()
    assert q(owner, "SELECT status, last_error FROM job WHERE id=%s", jid) == [("cancelled", "cancelled_uninstalled")]
    assert w.state.writes == [] and q(owner, "SELECT count(*) FROM publication") == [(0,)]
    assert q(owner, "SELECT count(*) FROM analysis") == [(0,)]
    assert q(owner, "SELECT status, purge_after IS NOT NULL FROM installation") == [("deleted", True)]


def test_token_refused_mid_job_is_cancelled_uninstalled(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    w.gh.routes.insert(
        0,
        (
            "POST",
            __import__("re").compile(r"^/app/installations/\d+/access_tokens$"),
            lambda r: jresp(404, {"message": "Not Found"}),
        ),
    )
    jid = w.enqueue()
    assert w.worker().run_once()
    assert q(owner, "SELECT status, last_error FROM job WHERE id=%s", jid) == [("cancelled", "cancelled_uninstalled")]
    assert w.state.writes == []


def test_deletion_racing_ingestion_never_publishes(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    ev = WorkflowRunEvent.model_validate(
        {**failure(name="acme/coffee"), "repository": {"id": 7, "full_name": "acme/coffee"}}
        | {
            "workflow_run": {
                **failure()["workflow_run"],
                "head_sha": head,
                "repository": {"id": 7, "full_name": "acme/coffee"},
                "head_repository": {"id": 7, "full_name": "acme/coffee"},
            }
        }
    )
    barrier = threading.Barrier(2)
    results: dict[str, Any] = {}

    def ingest() -> None:
        barrier.wait()
        results["ingest"] = ingest_workflow_run(pool, "race-1", ev).outcome

    def delete() -> None:
        barrier.wait()
        results["delete"] = process_installation(pool, "race-2", InstallationEvent.model_validate(inst("deleted"))).outcome

    threads = [threading.Thread(target=ingest), threading.Thread(target=delete)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert results["delete"] == "processed" and results["ingest"] in ("enqueued", "installation_inactive")
    w.worker().run_once()  # whatever survived the race must not publish
    assert w.state.writes == []
    assert q(owner, "SELECT count(*) FROM job WHERE status NOT IN ('cancelled')") == [(0,)]
