"""T-702 recovery (FS-EVT-5, AT-REL-03), offline: fake GitHub (deliveries + runs), disposable Postgres, the real
ingestion path and, end to end, the real worker and publisher. No network; no real credentials."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.github_fake import FakeGitHub, jresp
from tracewise import recovery as rec
from tracewise.config import Settings
from tracewise.contracts import WorkflowRunEvent
from tracewise.db import repositories as repo
from tracewise.db.session import DatabaseUnavailable, transaction
from tracewise.github.auth import AppCredentials
from tracewise.web.app import create_app
from tracewise.web.ingest import ingest_workflow_run

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
SHA = "a" * 40


def clock() -> datetime:
    return NOW


def delivery(
    did: int,
    guid: str,
    *,
    event: str = "workflow_run",
    status: int = 503,
    inst: int | None = 9,
    age: timedelta = timedelta(minutes=30),
    action: str | None = "completed",
) -> dict[str, Any]:
    return {
        "id": did,
        "guid": guid,
        "delivered_at": (NOW - age).isoformat().replace("+00:00", "Z"),
        "redelivery": False,
        "duration": 0.1,
        "status": "failed",
        "status_code": status,
        "event": event,
        "action": action,
        "installation_id": inst,
        "repository_id": 7,
    }


class Hub:
    """Fake GitHub for recovery: cursor-paginated failed deliveries, redelivery endpoint, workflow-run listing."""

    def __init__(self, gh: FakeGitHub | None = None) -> None:
        self.gh = gh or FakeGitHub()
        if gh is None:
            self.gh.add_token_route()
        self.deliveries: list[dict[str, Any]] = []
        self.redelivered: list[int] = []
        self.runs: dict[int, list[dict[str, Any]]] = {}
        self.faults: dict[str, list[Any]] = {"list": [], "redeliver": [], "runs": []}
        self.page_size = 100
        self.gh.route("GET", r"^/app/hook/deliveries$", self._list)
        self.gh.route("POST", r"^/app/hook/deliveries/\d+/attempts$", self._redeliver)
        self.gh.route("GET", r"^/repos/[^/]+/[^/]+/actions/runs$", self._runs)

    def _fault(self, kind: str) -> httpx.Response | None:
        if self.faults[kind]:
            f = self.faults[kind].pop(0)
            if f == "rate_limit":
                return jresp(
                    403,
                    {"message": "API rate limit exceeded"},
                    {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(self.gh.now) + 600)},
                )
            return jresp(int(f), {"message": "fault"})
        return None

    def _list(self, req: httpx.Request) -> httpx.Response:
        if (f := self._fault("list")) is not None:
            return f
        assert req.url.params.get("status") == "failure" and req.headers["authorization"].startswith("Bearer ey")
        start = int(req.url.params.get("cursor", "0"))
        page = self.deliveries[start : start + self.page_size]
        headers = {}
        if start + self.page_size < len(self.deliveries):
            headers["link"] = (
                f'<https://api.github.com/app/hook/deliveries?status=failure&cursor={start + self.page_size}>; rel="next"'
            )
        return jresp(200, page, headers)

    def _redeliver(self, req: httpx.Request) -> httpx.Response:
        if (f := self._fault("redeliver")) is not None:
            return f
        self.redelivered.append(int(req.url.path.split("/")[-2]))
        return jresp(202, {})

    def _runs(self, req: httpx.Request) -> httpx.Response:
        if (f := self._fault("runs")) is not None:
            return f
        repo_name = "/".join(req.url.path.split("/")[2:4])
        rid = {"acme/coffee": 7, "acme/lib": 8, "other/app": 70}.get(repo_name, 0)
        want = req.url.params.get("status")
        assert req.url.params.get("created", "").startswith(">=")
        return jresp(200, {"total_count": 0, "workflow_runs": [r for r in self.runs.get(rid, []) if r["conclusion"] == want]})

    def http(self) -> Any:
        return self.gh.http()


def run_obj(
    run_id: int,
    *,
    conclusion: str = "failure",
    head_sha: str = SHA,
    repo_id: int = 7,
    name: str = "acme/coffee",
    attempt: int = 1,
) -> dict[str, Any]:
    r = {"id": repo_id, "full_name": name}
    return {
        "id": run_id,
        "run_attempt": attempt,
        "workflow_id": 3,
        "head_sha": head_sha,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": conclusion,
        "repository": r,
        "head_repository": r,
        "created_at": (NOW - timedelta(hours=1)).isoformat(),
    }


def creds() -> AppCredentials:
    from tests.github_fake import test_key

    return AppCredentials(123, test_key())


def setup_tenants(pool: Any) -> None:
    with transaction(pool) as c:
        repo.set_installation_status(c, 9, "active", "acme")
        repo.repository_added(c, 7, 9, "acme/coffee")
        repo.repository_added(c, 8, 9, "acme/lib")
        repo.set_installation_status(c, 10, "active", "other")
        repo.repository_added(c, 70, 10, "other/app")


def redeliver(pool: Any, hub: Hub, **kw: Any) -> rec.RecoverySummary:
    return rec.redeliver_failed_deliveries(pool, hub.http(), creds(), now=kw.pop("now", clock), **kw)


def sweep(pool: Any, hub: Hub, **kw: Any) -> rec.RecoverySummary:
    http = hub.http()
    return rec.sweep_failed_runs(pool, http, hub.gh.provider(http), now=clock, **kw)


def count(owner: Any, sql: str, *a: Any) -> int:
    return int(owner.execute(sql, a).fetchone()[0])


# ---------------------------------------------------------------- (a) redelivery


def test_failed_unrecorded_delivery_is_redelivered_once(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(11, "g-1"), delivery(12, "g-1", age=timedelta(minutes=20))]  # two failed attempts, one GUID
    s = redeliver(pool, hub)
    assert (s.completed, s.candidates, s.redelivered, hub.redelivered) == (True, 1, 1, [12])  # latest attempt
    assert owner.execute("SELECT attempts, github_delivery_id, last_status FROM redelivery_request").fetchone() == (
        1,
        12,
        "requested",
    )
    assert (
        owner.execute("SELECT value FROM recovery_checkpoint WHERE key='deliveries:high_water'")
        .fetchone()[0]
        .startswith("2026-10-18T11:40")
    )


def test_skips_received_succeeded_unhandled_inactive_old_and_malformed(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    with transaction(pool) as c:
        repo.insert_delivery(c, "g-received", "workflow_run", "completed", 9, "enqueued")
        repo.set_installation_status(c, 10, "suspended")
    hub = Hub()
    hub.deliveries = [
        delivery(1, "g-received"),
        delivery(2, "g-ok"),
        delivery(3, "g-ok", status=200, age=timedelta(minutes=5)),
        delivery(4, "g-push", event="push"),
        delivery(5, "g-inactive", inst=10),
        delivery(6, "g-lifecycle", event="installation", inst=10, action="deleted"),  # lifecycle still redelivered
        delivery(7, "g-old", age=timedelta(days=4)),
        {"id": "x", "guid": None},
    ]
    s = redeliver(pool, hub)
    assert hub.redelivered == [6]
    assert s.already_received == 1 and dict(s.skipped) == {
        "succeeded_later": 1,
        "unhandled_event": 1,
        "installation_inactive": 1,
        "malformed": 1,
    }


def test_cooldown_attempt_cap_and_resume(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(21, "g-2")]
    t = NOW
    for expected in (1, 1, 2, 2, 3, 3):  # passes 8 min apart, 15-min cooldown: requests at 0, 16, 32 min; cap is 3
        s = redeliver(pool, hub, now=lambda t=t: t)
        assert count(owner, "SELECT attempts FROM redelivery_request") == expected
        t += timedelta(minutes=8)
    assert s.skipped.get("max_attempts") == 1 and hub.redelivered == [21, 21, 21]


def test_rate_limits_stop_cleanly_and_the_next_pass_resumes(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(31, "g-a"), delivery(32, "g-b"), delivery(33, "g-c")]
    hub.faults["list"] = ["rate_limit"]
    s1 = redeliver(pool, hub)
    assert (s1.completed, s1.stopped, hub.redelivered) == (False, "rate_limited", [])
    assert count(owner, "SELECT count(*) FROM recovery_checkpoint") == 0  # nothing advanced
    calls = {"n": 0}  # the first redelivery succeeds, the second is rate limited
    real = hub._redeliver

    def flaky(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 2:
            return jresp(
                403, {"message": "rate limit"}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(hub.gh.now) + 600)}
            )
        return real(req)

    hub.gh.routes.insert(0, ("POST", re.compile(r"^/app/hook/deliveries/\d+/attempts$"), flaky))
    s2 = redeliver(pool, hub)
    assert (s2.stopped, s2.redelivered, hub.redelivered) == ("rate_limited", 1, [31])
    assert count(owner, "SELECT count(*) FROM recovery_checkpoint") == 0
    s3 = redeliver(pool, hub)  # resumes: g-a is in cooldown, g-b and g-c are requested
    assert (s3.completed, sorted(hub.redelivered)) == (True, [31, 32, 33]) and s3.skipped["cooldown"] == 1


def test_pagination_page_cap_and_request_cap(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.page_size = 2
    hub.deliveries = [delivery(100 + i, f"g-{i}") for i in range(5)]
    s = redeliver(pool, hub)  # follows the cursor across 3 pages
    assert (s.completed, s.scanned, len(hub.redelivered)) == (True, 5, 5)
    hub2 = Hub()
    hub2.deliveries = [delivery(200 + i, f"h-{i}") for i in range(250)]
    s2 = redeliver(pool, hub2, max_pages=2)
    assert (s2.stopped, s2.scanned, s2.completed) == ("page_cap", 200, False)
    assert (
        count(owner, "SELECT count(*) FROM recovery_checkpoint WHERE key='deliveries:high_water'") == 1
    )  # from the first pass only
    hub3 = Hub()
    hub3.deliveries = [delivery(300 + i, f"k-{i}") for i in range(5)]
    s3 = redeliver(pool, hub3, max_requests=2)
    assert (s3.stopped, len(hub3.redelivered)) == ("request_cap", 2)


def test_rel03a_redelivered_webhook_runs_once_end_to_end(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    hub = Hub(w.gh)
    guid = "lost-" + secrets.token_hex(4)
    hub.deliveries = [delivery(41, guid)]
    assert redeliver(pool, hub).redelivered == 1
    secret = secrets.token_hex(16)
    body = {
        "action": "completed",
        "installation": {"id": 9},
        "repository": {"id": 7, "full_name": "acme/coffee"},
        "workflow_run": {
            "id": 55,
            "run_attempt": 1,
            "workflow_id": 3,
            "head_sha": head,
            "head_branch": "feature",
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
            "repository": {"id": 7, "full_name": "acme/coffee"},
            "head_repository": {"id": 7, "full_name": "acme/coffee"},
        },
    }
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    with TestClient(create_app(Settings(github_webhook_secret=SecretStr(secret)), pool)) as c:  # GitHub's redelivery arrives
        for _ in range(2):
            c.post(
                "/webhooks/github",
                content=raw,
                headers={"X-GitHub-Event": "workflow_run", "X-Hub-Signature-256": sig, "X-GitHub-Delivery": guid},
            )
    w.run()
    assert (
        count(owner, "SELECT count(*) FROM job") == 1 and count(owner, "SELECT count(*) FROM job WHERE status='succeeded'") == 1
    )
    assert (len(w.all_ccs()), len(w.state.check_runs)) == (1, 1)
    again = redeliver(pool, hub, now=lambda: NOW + timedelta(hours=1))
    assert again.already_received == 1 and again.redelivered == 0  # recorded now: never redelivered again


# ---------------------------------------------------------------- (b) failed-run sweep


def test_rel03b_undelivered_failed_run_is_found_and_published_once(pool, owner, server, tmp_path, head) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    hub = Hub(w.gh)
    hub.runs[7] = [run_obj(55, head_sha=head, name="acme/coffee"), run_obj(60, conclusion="success", head_sha=head)]
    s = sweep(pool, hub)
    assert (s.completed, s.enqueued, s.repos_swept) == (True, 1, 1)
    assert owner.execute("SELECT delivery_id, outcome FROM webhook_delivery").fetchall() == [("sweep-7-55-1", "enqueued")]
    w.run()
    assert (len(w.all_ccs()), len(w.state.check_runs)) == (1, 1)
    s2 = sweep(pool, hub)  # repeat: dedupe, no new job, no new publication
    assert (s2.enqueued, s2.duplicates) == (0, 1)
    assert count(owner, "SELECT count(*) FROM job") == 1 and (len(w.all_ccs()), len(w.state.check_runs)) == (1, 1)


def test_sweep_respects_scope_and_ownership(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    owner.execute("UPDATE repository SET enabled=false WHERE id=8")
    owner.execute("UPDATE installation SET status='suspended' WHERE id=10")
    hub = Hub()
    hub.runs = {7: [run_obj(1)], 8: [run_obj(2, repo_id=8, name="acme/lib")], 70: [run_obj(3, repo_id=70, name="other/app")]}
    s = sweep(pool, hub)
    assert s.repos_swept == 1 and s.enqueued == 1  # only acme/coffee: lib is disabled, installation 10 suspended
    assert [r[0] for r in owner.execute("SELECT (payload->>'repo_id')::int FROM job").fetchall()] == [7]
    hub.runs[7] = [run_obj(4, repo_id=70, name="other/app")]  # a listing naming a foreign repository is not trusted
    s2 = sweep(pool, hub)
    assert count(owner, "SELECT count(*) FROM job") == 1 and (s2.enqueued + s2.duplicates) == 0


def test_sweep_skips_non_failed_and_malformed_runs(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.runs[7] = [run_obj(5), {**run_obj(6), "head_sha": "not-a-sha"}, run_obj(7, conclusion="timed_out")]
    s = sweep(pool, hub, max_repos=1)
    assert (s.enqueued, s.skipped["malformed"]) == (2, 1)


def test_rate_limited_sweep_resumes_from_the_unfinished_repo(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.runs = {7: [run_obj(1)], 8: [run_obj(2, repo_id=8, name="acme/lib")], 70: [run_obj(3, repo_id=70, name="other/app")]}
    calls = {"n": 0}
    real = hub._runs

    def flaky(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 3:  # repo 7 needs 2 calls (failure, timed_out); fail the first call for repo 8
            return jresp(
                403, {"message": "rate limit"}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(hub.gh.now) + 600)}
            )
        return real(req)

    hub.gh.routes.insert(0, ("GET", re.compile(r"^/repos/[^/]+/[^/]+/actions/runs$"), flaky))
    s1 = sweep(pool, hub)
    assert (s1.completed, s1.stopped, s1.repos_swept, s1.enqueued) == (False, "rate_limited", 1, 1)
    assert owner.execute("SELECT value FROM recovery_checkpoint WHERE key='sweep:repo_cursor'").fetchone() == ("7",)
    s2 = sweep(pool, hub)
    assert (s2.completed, s2.enqueued) == (True, 2)  # 8 and 70, nothing skipped
    assert sorted(r[0] for r in owner.execute("SELECT (payload->>'repo_id')::int FROM job").fetchall()) == [7, 8, 70]


def test_refused_token_for_one_repo_does_not_stop_the_sweep(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub(FakeGitHub())

    def mint(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if req.url.path.endswith("/9/access_tokens"):
            return jresp(404, {"message": "Not Found"})  # installation 9 uninstalled on GitHub's side
        return jresp(
            201,
            {
                "token": "ghs_fake" + "y" * 32,
                "expires_at": "2099-01-01T00:00:00Z",
                "permissions": body["permissions"],
                "repository_selection": "selected",
                "repositories": [{"id": i} for i in body["repository_ids"]],
            },
        )

    hub.gh.route("POST", r"^/app/installations/\d+/access_tokens$", mint)
    hub.runs = {70: [run_obj(3, repo_id=70, name="other/app")]}
    s = sweep(pool, hub)
    assert s.completed and s.errors["InstallationUnavailable"] == 2 and s.enqueued == 1


def test_interrupted_sweep_reruns_without_duplicates(pool, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.runs = {7: [run_obj(1), run_obj(2)]}
    real = rec.ingest_workflow_run
    calls = {"n": 0}

    def once_broken(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise DatabaseUnavailable("simulated outage")
        return real(*a, **k)

    monkeypatch.setattr(rec, "ingest_workflow_run", once_broken)
    with pytest.raises(DatabaseUnavailable):
        sweep(pool, hub)
    assert count(owner, "SELECT count(*) FROM job") == 1
    assert count(owner, "SELECT count(*) FROM recovery_checkpoint") == 0  # repo 7 not finished: cursor not advanced
    monkeypatch.setattr(rec, "ingest_workflow_run", real)
    s = sweep(pool, hub)
    assert (s.enqueued, s.duplicates) == (1, 1) and count(owner, "SELECT count(*) FROM job") == 2


def test_sweep_concurrent_with_webhook_yields_one_job(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.runs = {7: [run_obj(77)]}
    ev = WorkflowRunEvent.model_validate(
        {
            "action": "completed",
            "installation": {"id": 9},
            "repository": {"id": 7, "full_name": "acme/coffee"},
            "workflow_run": run_obj(77),
        }
    )
    barrier = threading.Barrier(2)
    out: dict[str, Any] = {}

    def a() -> None:
        barrier.wait()
        out["webhook"] = ingest_workflow_run(pool, "real-77", ev).outcome

    def b() -> None:
        barrier.wait()
        out["sweep"] = sweep(pool, hub, max_repos=1)

    ts = [threading.Thread(target=a), threading.Thread(target=b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert count(owner, "SELECT count(*) FROM job") == 1
    assert {out["webhook"], "enqueued" if out["sweep"].enqueued else "duplicate_run"} == {"enqueued", "duplicate_run"}


# ---------------------------------------------------------------- entry point


def test_entry_point_refuses_without_project_config_and_reports_summaries(pool, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tracewise import config

    config.get_settings.cache_clear()
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    with pytest.raises(SystemExit, match="project App only"):
        rec.main(["both"])
    config.get_settings.cache_clear()
    setup_tenants(pool)
    hub = Hub()
    hub.runs = {7: [run_obj(1)]}
    assert rec.main(["runs"], build=lambda: (pool, hub.http(), creds())) == 0
    assert count(owner, "SELECT count(*) FROM job") == 1
    hub.faults["list"] = ["rate_limit"]
    assert rec.main(["deliveries"], build=lambda: (pool, hub.http(), creds())) == 1  # incomplete pass → non-zero


def test_hostile_delivery_items_and_status_codes_never_abort_the_pass(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    bad_code = delivery(2, "g-badcode")
    bad_code["status_code"] = "abc"
    list_code = delivery(3, "g-badcode", age=timedelta(minutes=20))
    list_code["status_code"] = [200]
    bool_code = delivery(4, "g-bool")
    bool_code["status_code"] = True  # never "succeeded"
    hub.deliveries = [5, "x", None, [1], bad_code, list_code, bool_code, delivery(6, "g-good")]
    s = redeliver(pool, hub)
    assert s.skipped["malformed"] == 4 and "succeeded_later" not in s.skipped
    assert sorted(hub.redelivered) == [
        3,
        4,
        6,
    ]  # the latest attempt of each; unproven success is not success: redelivery stays deduplicated


@pytest.mark.parametrize("kind", ["deliveries", "sweep"])
def test_an_overlapping_pass_of_the_same_kind_is_refused_without_touching_github(pool, owner, kind) -> None:  # type: ignore[no-untyped-def]
    """Cron overlap: a second pass must not repeat redelivery POSTs or overwrite the first pass's checkpoint."""
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(1, "g-overlap")]
    with transaction(pool) as other:  # the first pass, still running
        other.execute("SELECT pg_advisory_xact_lock(%s)", (rec.PASS_LOCKS[kind],))
        s = redeliver(pool, hub) if kind == "deliveries" else sweep(pool, hub)
        assert (s.stopped, s.completed) == ("locked", False)
        assert hub.redelivered == [] and hub.gh.requests == []  # nothing reached GitHub, not even a token mint
    after = redeliver(pool, hub) if kind == "deliveries" else sweep(pool, hub)
    assert after.stopped != "locked"  # released with the first pass's transaction
    if kind == "deliveries":
        assert hub.redelivered == [1]


def test_different_kinds_do_not_block_each_other(pool, owner) -> None:  # type: ignore[no-untyped-def]
    setup_tenants(pool)
    hub = Hub()
    hub.deliveries = [delivery(1, "g-kinds")]
    with transaction(pool) as other:
        other.execute("SELECT pg_advisory_xact_lock(%s)", (rec.PASS_LOCKS["sweep"],))
        assert redeliver(pool, hub).stopped != "locked" and hub.redelivered == [1]
