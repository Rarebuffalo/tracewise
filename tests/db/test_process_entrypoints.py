"""Phase 18: the real process entry points, run as subprocesses against the disposable cluster.

Web: `uvicorn --factory tracewise.web.asgi:create_runtime_app` on loopback. Worker: `python -m tracewise.worker`.
No job that could reach GitHub is ever queued for a subprocess (the GitHub API host is fixed by design): the only
job a subprocess sees has an unknown kind and fails permanently before any network call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.github_fake import test_key_pem as _key_pem
from tests.pg import APP, OWNER, SYSTEM

ROOT = Path(__file__).resolve().parents[2]
SECRET = "local-test-webhook-secret-0001"
TABLES = (
    "installation",
    "repository",
    "webhook_delivery",
    "workflow_run",
    "job",
    "analysis",
    "publication",
    "usage_event",
    "audit_event",
    "failure_signature",
    "recovery_checkpoint",
    "redelivery_request",
)


def _env(**over: str) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DATABASE_URL", "GITHUB_", "OPENAI_", "LLM_", "TW_"))}
    return {**base, **over}


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _counts(owner: Any) -> dict[str, int]:
    return {t: owner.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}  # noqa: S608


def _web(env: dict[str, str]) -> tuple[subprocess.Popen[str], int]:
    port = _port()
    p = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "tracewise.web.asgi:create_runtime_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return p, port


def _wait_http(port: int, p: subprocess.Popen[str], timeout: float = 20.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if p.poll() is not None:
            raise AssertionError(f"web process exited early: {p.returncode}")
        try:
            httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=0.5)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise AssertionError("web process did not start")


def _stop(p: subprocess.Popen[str], sig: int = signal.SIGTERM) -> tuple[int, str]:
    p.send_signal(sig)
    try:
        _, err = p.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
        raise AssertionError("process did not stop on signal") from None
    return p.returncode, err


# ------------------------------------------------------------------------------------------------ web


def test_web_refuses_to_start_without_configuration(pg) -> None:  # type: ignore[no-untyped-def]
    p, _ = _web(_env(DATABASE_URL_SYSTEM=pg.url(SYSTEM)))
    _, err = p.communicate(timeout=30)
    assert p.returncode != 0 and "missing: GITHUB_WEBHOOK_SECRET" in err
    p, _ = _web(_env(GITHUB_WEBHOOK_SECRET="short"))
    _, err = p.communicate(timeout=30)
    assert p.returncode != 0 and "DATABASE_URL_SYSTEM" in err and "short" not in err.replace("shorter", "")


def test_web_starts_serves_and_stops_cleanly_without_side_effects(pg, owner) -> None:  # type: ignore[no-untyped-def]
    before = _counts(owner)
    rev = owner.execute("SELECT version_num FROM alembic_version").fetchone()
    p, port = _web(_env(DATABASE_URL_SYSTEM=pg.url(SYSTEM), GITHUB_WEBHOOK_SECRET=SECRET))
    try:
        _wait_http(port, p)
        assert _counts(owner) == before  # startup writes nothing and never migrates
        assert owner.execute("SELECT version_num FROM alembic_version").fetchone() == rev
        base = f"http://127.0.0.1:{port}"
        assert httpx.get(base + "/healthz").json() == {"status": "ok"}
        assert httpx.get(base + "/readyz").json() == {"status": "ready"}
        body = json.dumps({"zen": "x"}).encode()
        sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        r = httpx.post(
            base + "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "ping", "X-GitHub-Delivery": "p-1", "X-Hub-Signature-256": sig},
        )
        assert r.status_code == 200
        bad = httpx.post(
            base + "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "ping", "X-GitHub-Delivery": "p-2", "X-Hub-Signature-256": "sha256=00"},
        )
        assert bad.status_code == 401
        for path in ("/docs", "/openapi.json", "/redoc"):
            assert httpx.get(base + path).status_code == 404
    finally:
        code, err = _stop(p)
    # uvicorn shuts down gracefully, then re-raises the signal it handled: -SIGTERM after a completed shutdown.
    assert code in (0, -signal.SIGTERM) and "Application shutdown complete." in err, err[-800:]
    assert SECRET not in err and "Traceback" not in err


def test_web_readiness_reports_an_unreachable_database_without_crashing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"postgresql://tracewise_system:pw-should-not-leak@/tracewise?host={tmp_path / 'none'}&port=5432"
    p, port = _web(_env(DATABASE_URL_SYSTEM=url, GITHUB_WEBHOOK_SECRET=SECRET))
    try:
        _wait_http(port, p)
        r = httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=10)
        assert (r.status_code, r.json()) == (503, {"status": "unavailable"})
        assert httpx.get(f"http://127.0.0.1:{port}/healthz").status_code == 200
    finally:
        code, err = _stop(p)
    assert code in (0, -signal.SIGTERM) and "Application shutdown complete." in err
    assert "pw-should-not-leak" not in err


def test_readiness_requires_this_builds_schema(pool) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from tracewise.config import Settings
    from tracewise.web.app import create_app

    st = Settings(github_webhook_secret=SecretStr(SECRET))
    with TestClient(create_app(st, pool, schema_head="9999")) as c:
        assert (c.get("/readyz").status_code, c.get("/readyz").json()) == (503, {"status": "schema_mismatch"})
    closed: list[bool] = []
    with TestClient(create_app(st, pool, schema_head="0009", on_shutdown=lambda: closed.append(True))) as c:
        assert c.get("/readyz").json() == {"status": "ready"}
    assert closed == [True]  # the lifespan hook ran on shutdown


# ------------------------------------------------------------------------------------------------ worker


@pytest.fixture(scope="module")
def key_path(tmp_path_factory) -> str:  # type: ignore[no-untyped-def]
    p = tmp_path_factory.mktemp("key") / "app.pem"
    p.write_bytes(_key_pem())
    p.chmod(0o600)
    return str(p)


def _worker_env(pg: Any, key_path: str, **over: str) -> dict[str, str]:
    return _env(
        **{
            "TW_ENV": "test",
            "LLM_PROVIDER": "fake",
            "DATABASE_URL": pg.url(APP),
            "DATABASE_URL_SYSTEM": pg.url(SYSTEM),
            "GITHUB_APP_ID": "123",
            "GITHUB_APP_PRIVATE_KEY_PATH": key_path,
            **over,
        }
    )


def _worker(env: dict[str, str], *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "tracewise.worker", "--idle-sleep", "0.1", *args],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _worker_to_file(env: dict[str, str], log_path: Any, *args: str) -> subprocess.Popen[str]:
    f = open(log_path, "w")
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "tracewise.worker", "--idle-sleep", "0.1", *args],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=f,
        text=True,
    )


def _wait_event(p: subprocess.Popen[str], log_path: Any, name: str, timeout: float = 30.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if f'"event": "{name}"' in Path(log_path).read_text():
            return
        if p.poll() is not None:
            raise AssertionError(f"worker exited ({p.returncode}) before {name}")
        time.sleep(0.05)
    raise AssertionError(f"no {name} within {timeout}s")


def _events(err: str) -> list[str]:
    out = []
    for line in err.splitlines():
        try:
            out.append(json.loads(line).get("event"))
        except ValueError:
            continue
    return [e for e in out if e]


@pytest.mark.parametrize(
    ("over", "needle", "code"),
    [
        ({"DATABASE_URL": ""}, "missing: DATABASE_URL", 2),
        ({"GITHUB_APP_ID": ""}, "invalid configuration (GITHUB_APP_ID)", 2),
        ({"GITHUB_APP_ID": "not-a-number"}, "invalid configuration (GITHUB_APP_ID)", 2),
        ({"TW_ENV": "local"}, "LLM_PROVIDER=fake is only allowed with TW_ENV=test", 2),
        ({"GITHUB_APP_PRIVATE_KEY_PATH": "/nonexistent/key.pem"}, "readable RSA private key", 2),
        ({"DATABASE_URL": "SAME"}, "must be different roles", 2),
        ({"DATABASE_URL": "SYSTEM2"}, "not subject to row-level security", 2),  # system role as tenant
        ({"DATABASE_URL_SYSTEM": "APP2"}, "not the BYPASSRLS system role", 2),  # tenant role as system
        ({"DATABASE_URL_SYSTEM": "OWNER"}, "not the BYPASSRLS system role", 2),
        ({"DATABASE_URL": "OWNER"}, "not subject to row-level security", 2),
        ({"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "placeholder-not-a-key"}, "LLM_PROVIDER=openai", 2),
    ],
)
def test_worker_refuses_unsafe_configuration(pg, owner, key_path, over, needle, code) -> None:  # type: ignore[no-untyped-def]
    env = _worker_env(pg, key_path)
    urls = {
        "SAME": env["DATABASE_URL_SYSTEM"],
        "SYSTEM2": pg.url(SYSTEM) + "&application_name=x",  # same role as DATABASE_URL_SYSTEM, different URL
        "APP2": pg.url(APP) + "&application_name=x",
        "OWNER": pg.url(OWNER),
    }
    for k, v in over.items():
        env[k] = urls.get(v, v)
    p = _worker(env)
    out, err = p.communicate(timeout=60)
    assert p.returncode == code, err[-600:]
    assert needle in err, err[-600:]
    assert "placeholder-not-a-key" not in err + out and "BEGIN" not in err


def test_worker_with_unreachable_database_exits_1_without_leaking(pg, key_path, tmp_path) -> None:  # type: ignore[no-untyped-def]
    bad = f"postgresql://tracewise_system:pw-should-not-leak@/tracewise?host={tmp_path / 'none'}&port=5432"
    p = _worker(_worker_env(pg, key_path, DATABASE_URL_SYSTEM=bad))
    _, err = p.communicate(timeout=60)
    assert p.returncode == 1 and "database unavailable" in err and "pw-should-not-leak" not in err


def test_worker_starts_idles_and_stops_gracefully(pg, owner, key_path, tmp_path) -> None:  # type: ignore[no-untyped-def]
    before = _counts(owner)
    log_path = tmp_path / "worker.log"
    p = _worker_to_file(_worker_env(pg, key_path), log_path)
    _wait_event(p, log_path, "worker.started")
    time.sleep(0.5)  # idle a few loops
    assert p.poll() is None
    assert _counts(owner) == before  # idle: no writes
    p.send_signal(signal.SIGTERM)
    assert p.wait(timeout=20) == 0
    ev = _events(Path(log_path).read_text())
    assert ev.index("worker.starting") < ev.index("worker.started") < ev.index("worker.stopping") < ev.index("worker.stopped")


def test_sigterm_during_startup_is_graceful(pg, owner, key_path, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Phase 41: handlers are installed before connecting/validating, so an early stop exits 0 without claiming."""
    owner.execute("INSERT INTO job (kind, installation_id, dedupe_key, payload) VALUES ('no_such_kind', 9, 'early', '{}')")
    log_path = tmp_path / "worker.log"
    p = _worker_to_file(_worker_env(pg, key_path), log_path)
    _wait_event(p, log_path, "worker.starting")
    p.send_signal(signal.SIGTERM)  # while it is still validating roles, schema and keys
    assert p.wait(timeout=30) == 0
    ev = _events(Path(log_path).read_text())
    assert "worker.stopped" in ev and "job.claimed" not in ev
    assert owner.execute("SELECT status, attempts FROM job").fetchone() == ("queued", 0)  # nothing was claimed


def test_worker_records_a_permanent_failure_once_and_does_not_spin(pg, owner, key_path) -> None:  # type: ignore[no-untyped-def]
    owner.execute("INSERT INTO job (kind, installation_id, dedupe_key, payload) VALUES ('no_such_kind', 9, 'k', '{}')")
    p = _worker(_worker_env(pg, key_path), "--once")
    _, err = p.communicate(timeout=60)
    assert p.returncode == 0, err[-600:]
    row = owner.execute("SELECT status, attempts, last_error FROM job").fetchone()
    assert row[0] == "dead" and row[1] == 1 and "no handler" in row[2]
    ev = _events(err)
    assert ev.count("job.claimed") == 1 and "job.failed" in ev and "job.succeeded" not in ev
    p2 = _worker(_worker_env(pg, key_path), "--once")  # dead is final: nothing is claimed again
    _, err2 = p2.communicate(timeout=60)
    assert p2.returncode == 0 and "job.claimed" not in _events(err2)
