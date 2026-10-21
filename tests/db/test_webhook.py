"""T-106 webhook: AT-EVT-01/02/03 (filter), AT-EVT-05 (fast 2xx, atomic), AT-EVT-06 (idempotency),
AT-SEC-02 (signature, size), invalid payloads, database failures."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tracewise.config import Settings
from tracewise.db.session import make_pool
from tracewise.jobs import queue
from tracewise.web import ingest
from tracewise.web.app import create_app

SHA = "d73fa1cdcb0e5f4a7b9c1d2e3f405162738495a6"


def payload(
    conclusion: str = "failure", action: str = "completed", run_id: int = 37632626982, attempt: int = 1, head_repo_id: int = 1001
) -> dict[str, Any]:
    """Synthetic `workflow_run` payload shaped like GitHub's documented example (no real data)."""
    repo = {"id": 1001, "full_name": "acme/app", "private": False}
    return {
        "action": action,
        "installation": {"id": 4242},
        "repository": repo,
        "workflow_run": {
            "id": run_id,
            "name": "Tests",
            "run_attempt": attempt,
            "workflow_id": 555,
            "head_sha": SHA,
            "head_branch": "feature/x",
            "event": "pull_request",
            "status": "completed" if action == "completed" else "in_progress",
            "conclusion": conclusion if action == "completed" else None,
            "pull_requests": [],
            "repository": repo,
            "head_repository": {"id": head_repo_id, "full_name": "acme/app" if head_repo_id == 1001 else "fork/app"},
        },
    }


@pytest.fixture
def secret() -> str:
    return secrets.token_hex(16)  # per-test random value; not a credential


@pytest.fixture
def client(pool, secret) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app(Settings(github_webhook_secret=SecretStr(secret)), pool)
    with TestClient(app) as c:
        yield c


def post(
    client: TestClient,
    secret: str,
    body: dict[str, Any] | bytes,
    *,
    delivery: str | None = None,
    event: str = "workflow_run",
    sig: str | None = None,
) -> Any:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery or secrets.token_hex(8),
        "X-Hub-Signature-256": sig if sig is not None else "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
        "Content-Type": "application/json",
    }
    return client.post("/webhooks/github", content=raw, headers=headers)


def rows(owner, table: str) -> int:  # type: ignore[no-untyped-def]
    return int(owner.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608 - fixed table names


# ---------------------------------------------------------------- AT-EVT-01/02/03


@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
def test_evt01_03_failure_and_timeout_enqueue_one_job(client, secret, owner, conclusion) -> None:  # type: ignore[no-untyped-def]
    r = post(client, secret, payload(conclusion))
    assert r.status_code == 202 and r.json()["outcome"] == "enqueued"
    job = owner.execute("SELECT kind, installation_id, run_key, dedupe_key, payload, status FROM job").fetchall()
    assert len(job) == 1
    kind, inst, run_key, dedupe, pl, status = job[0]
    assert (kind, inst, run_key, dedupe, status) == ("analyze", 4242, "1001:37632626982", "analyze:1001:37632626982:1", "queued")
    assert pl["conclusion"] == conclusion and pl["workflow_id"] == 555 and pl["head_sha"] == SHA
    assert set(pl) == {
        "installation_id",
        "repo_id",
        "repo",
        "run_id",
        "attempt",
        "workflow_id",
        "head_sha",
        "head_branch",
        "head_repo",
        "head_repo_id",
        "event",
        "conclusion",
        "delivery_id",
    }  # identifiers only


@pytest.mark.parametrize(
    "conclusion", ["success", "cancelled", "skipped", "neutral", "action_required", "stale", "startup_failure"]
)
def test_evt02_other_conclusions_no_job(client, secret, owner, conclusion) -> None:  # type: ignore[no-untyped-def]
    r = post(client, secret, payload(conclusion))
    assert r.status_code == 200 and r.json()["outcome"] == "ignored"
    assert rows(owner, "job") == 0 and rows(owner, "webhook_delivery") == 1


def test_fork_run_payload_keeps_head_repo(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    post(client, secret, payload(head_repo_id=777))
    (pl,) = owner.execute("SELECT payload FROM job").fetchone()
    assert (pl["head_repo_id"], pl["head_repo"]) == (777, "fork/app")


# ---------------------------------------------------------------- AT-EVT-06 idempotency


def test_evt06_duplicate_deliveries_and_runs(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    body = payload()
    outcomes = [post(client, secret, body, delivery="dup-1").json()["outcome"] for _ in range(3)]
    assert outcomes == ["enqueued", "duplicate_delivery", "duplicate_delivery"]
    r = post(client, secret, body, delivery="dup-2")  # new delivery, same (repo, run, attempt)
    assert (r.status_code, r.json()["outcome"]) == (200, "duplicate_run")
    r = post(client, secret, payload(action="in_progress"), delivery="dup-3")  # out of order
    assert r.json()["outcome"] == "ignored"
    assert rows(owner, "job") == 1 and rows(owner, "workflow_run") == 1
    assert owner.execute("SELECT delivery_id, outcome FROM webhook_delivery ORDER BY delivery_id").fetchall() == [
        ("dup-1", "enqueued"),
        ("dup-2", "duplicate_run"),
        ("dup-3", "ignored"),
    ]
    r = post(client, secret, payload(attempt=2), delivery="dup-4")  # a re-run attempt is a new analysis
    assert r.json()["outcome"] == "enqueued" and rows(owner, "job") == 2


def test_evt06_concurrent_duplicate_deliveries(pool, secret, owner) -> None:  # type: ignore[no-untyped-def]
    from concurrent.futures import ThreadPoolExecutor

    app = create_app(Settings(github_webhook_secret=SecretStr(secret)), pool)
    with TestClient(app) as c, ThreadPoolExecutor(8) as ex:
        outs = list(ex.map(lambda i: post(c, secret, payload(), delivery=f"c-{i % 3}").json()["outcome"], range(24)))
    assert outs.count("enqueued") == 1
    assert rows(owner, "job") == 1 and rows(owner, "webhook_delivery") == 3


# ---------------------------------------------------------------- AT-EVT-05


def test_evt05_100_deliveries_fast_and_persisted_with_worker_stopped(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    slowest = 0.0
    for i in range(100):
        t0 = time.perf_counter()
        r = post(client, secret, payload(run_id=1000 + i))
        slowest = max(slowest, time.perf_counter() - t0)
        assert r.status_code == 202
    assert slowest < 1.0
    assert rows(owner, "job") == 100
    assert owner.execute(
        "SELECT count(*) FROM webhook_delivery d JOIN job j ON j.id = d.job_id WHERE d.outcome = 'enqueued'"
    ).fetchone() == (100,)


def test_evt05_atomic_rollback_on_mid_transaction_db_failure(client, secret, owner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The DB fails after the delivery and run rows were written but before the job: nothing is kept,
    and a redelivery of the same delivery ID succeeds."""
    real = queue.enqueue

    def broken(*a: Any, **k: Any) -> Any:
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(ingest.queue, "enqueue", broken)
    r = post(client, secret, payload(), delivery="atomic-1")
    assert (r.status_code, r.json()["outcome"]) == (503, "unavailable")
    assert rows(owner, "webhook_delivery") == rows(owner, "workflow_run") == rows(owner, "job") == 0
    monkeypatch.setattr(ingest.queue, "enqueue", real)
    r = post(client, secret, payload(), delivery="atomic-1")
    assert r.json()["outcome"] == "enqueued" and rows(owner, "job") == 1


def test_database_down_returns_503_quickly(pg, secret, tmp_path) -> None:  # type: ignore[no-untyped-def]
    bad = pg.url().replace(str(pg.sock).replace("/", "%2F"), str(tmp_path).replace("/", "%2F"))
    p = make_pool(bad, min_size=0, max_size=1, timeout_s=0.5)
    try:
        with TestClient(create_app(Settings(github_webhook_secret=SecretStr(secret)), p)) as c:
            t0 = time.perf_counter()
            r = post(c, secret, payload())
            assert (r.status_code, r.json()) == (503, {"outcome": "unavailable"})
            assert time.perf_counter() - t0 < 10  # within GitHub's 10 s window
            assert c.get("/readyz").status_code == 503 and c.get("/healthz").status_code == 200
    finally:
        p.close()


# ---------------------------------------------------------------- AT-SEC-02 and invalid input


def test_sec02_signature_failures_no_parse_no_rows(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps(payload()).encode()
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    tampered = body.replace(b"failure", b"failurX")
    for raw, sig in (
        (body, ""),
        (body, "sha256=" + "0" * 64),
        (body, "sha1=abc"),
        (tampered, good),
        (body, "sha256=" + hmac.new(b"other-secret", body, hashlib.sha256).hexdigest()),
    ):
        r = post(client, secret, raw, sig=sig)
        assert (r.status_code, r.json()["outcome"]) == (401, "bad_signature")
    assert rows(owner, "webhook_delivery") == rows(owner, "job") == 0


def test_sec02_oversized_body_413(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    big = b"{" + b" " * (25 * 1024 * 1024) + b"}"
    r = post(client, secret, big)
    assert (r.status_code, r.json()["outcome"]) == (413, "too_large")
    assert rows(owner, "webhook_delivery") == 0


@pytest.mark.parametrize("declared", ["99999999999", "26214401", "-1", "abc"])
def test_declared_length_refused_before_reading(declared) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from starlette.requests import Request

    from tracewise.web.webhooks import _read_capped

    read = False

    async def receive() -> dict[str, Any]:
        nonlocal read
        read = True
        return {"type": "http.request", "body": b"{}", "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/", "headers": [(b"content-length", declared.encode())]}
    assert asyncio.run(_read_capped(Request(scope, receive))) is None
    assert not read


def test_streamed_body_without_length_is_capped(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    def gen() -> Iterator[bytes]:
        chunk = b" " * (1024 * 1024)
        for _ in range(26):
            yield chunk

    r = client.post("/webhooks/github", content=gen(), headers={"X-GitHub-Event": "workflow_run"})
    assert r.status_code == 413 and rows(owner, "webhook_delivery") == 0


@pytest.mark.parametrize(
    ("body", "why"),
    [
        (b"{not json", "invalid_json"),
        (b"[1, 2]", "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        ("bad_sha", "invalid_payload"),
        ("missing_installation", "invalid_payload"),
    ],
)
def test_invalid_payloads_rejected_and_recorded(client, secret, owner, body, why) -> None:  # type: ignore[no-untyped-def]
    if body == "bad_sha":
        p = payload()
        p["workflow_run"]["head_sha"] = "not-a-sha"
        body = json.dumps(p).encode()
    elif body == "missing_installation":
        p = copy.deepcopy(payload())
        del p["installation"]
        body = json.dumps(p).encode()
    r = post(client, secret, body, delivery="bad-1")
    assert (r.status_code, r.json()["outcome"]) == (400, why)
    assert rows(owner, "job") == 0
    assert owner.execute("SELECT outcome FROM webhook_delivery WHERE delivery_id = 'bad-1'").fetchone() == ("rejected",)


@pytest.mark.parametrize("headers", [{"X-GitHub-Delivery": ""}, {"X-GitHub-Delivery": "a b"}, {"X-GitHub-Event": "Bad Event!"}])
def test_bad_headers_400(client, secret, owner, headers) -> None:  # type: ignore[no-untyped-def]
    raw = json.dumps(payload()).encode()
    h = {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "ok-1",
        "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
        **headers,
    }
    r = client.post("/webhooks/github", content=raw, headers=h)
    assert (r.status_code, r.json()["outcome"]) == (400, "bad_headers")
    assert rows(owner, "webhook_delivery") == 0


def test_ping_and_other_events(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    assert post(client, secret, {"zen": "x", "hook_id": 1}, event="ping").json() == {"outcome": "pong"}
    r = post(client, secret, {"action": "created", "installation": {"id": 4242}}, event="check_suite", delivery="i-1")
    assert (r.status_code, r.json()["outcome"]) == (202, "ignored")
    r = post(client, secret, {"action": "created", "installation": {"id": 4242}}, event="check_suite", delivery="i-1")
    assert r.json()["outcome"] == "duplicate_delivery"
    assert rows(owner, "job") == 0


def test_unconfigured_secret_fails_closed(pool) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(Settings(), pool)) as c:
        r = c.post("/webhooks/github", content=b"{}", headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": "sha256=00"})
    assert (r.status_code, r.json()["outcome"]) == (503, "not_configured")


def test_no_secrets_or_signatures_in_logs(client, secret, caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    r = post(client, secret, payload(), delivery="log-1")
    post(client, secret, payload(), sig="sha256=" + "f" * 64)
    assert r.status_code == 202
    text = caplog.text + " ".join(str(getattr(rec, "tw", "")) for rec in caplog.records)
    assert secret not in text and "sha256=" not in text and "log-1" in text


def test_ready_and_no_docs_endpoints(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/readyz").json() == {"status": "ready"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def _mutate(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    p = copy.deepcopy(payload())
    target = p
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = value
    return p


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("workflow_run", "run_attempt"), 0),  # the column's CHECK (run_attempt >= 1) must never be reached
        (("workflow_run", "run_attempt"), 2**31),  # integer column
        (("workflow_run", "id"), 2**63),  # bigint column
        (("workflow_run", "id"), -1),
        (("workflow_run", "id"), "37632626982"),
        (("installation", "id"), True),
        (("repository", "id"), 1.0),
        (("workflow_run", "workflow_id"), False),
    ],
    ids=[
        "attempt-0",
        "attempt-overflow",
        "id-overflow",
        "negative-id",
        "string-id",
        "bool-installation",
        "float-repo",
        "bool-workflow",
    ],
)
def test_out_of_range_or_mistyped_ids_are_rejected_not_a_server_error(client, secret, owner, path, value) -> None:  # type: ignore[no-untyped-def]
    r = post(client, secret, _mutate(path, value), delivery="ids-1")
    assert (r.status_code, r.json()["outcome"]) == (400, "invalid_payload")
    assert rows(owner, "job") == 0
    assert owner.execute("SELECT outcome FROM webhook_delivery WHERE delivery_id = 'ids-1'").fetchone() == ("rejected",)


def test_a_rejected_payload_with_an_unstorable_installation_id_is_still_recorded(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    r = post(client, secret, _mutate(("installation", "id"), 2**70), delivery="ids-2")
    assert r.status_code == 400
    assert owner.execute("SELECT installation_id FROM webhook_delivery WHERE delivery_id = 'ids-2'").fetchone() == (None,)


def test_pathologically_deep_json_is_invalid_json_not_a_crash(client, secret, owner) -> None:  # type: ignore[no-untyped-def]
    r = post(client, secret, b"[" * 100_000 + b"]" * 100_000, delivery="deep-1")
    assert (r.status_code, r.json()["outcome"]) == (400, "invalid_json") and rows(owner, "job") == 0


@pytest.mark.parametrize("value", [2**63, True, 0, "7"])
def test_lifecycle_events_with_bad_ids_are_rejected(client, secret, owner, value) -> None:  # type: ignore[no-untyped-def]
    body = {"action": "created", "installation": {"id": value, "account": {"login": "acme"}}, "repositories": []}
    r = post(client, secret, body, event="installation")
    assert (r.status_code, r.json()["outcome"]) == (400, "invalid_payload") and rows(owner, "installation") == 0
