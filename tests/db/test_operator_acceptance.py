"""Phase 20: local operator acceptance of the runnable system, stage by stage.

REAL: the web process (uvicorn subprocess, every webhook over loopback HTTP, HMAC on the real path), Postgres
(queue, RLS, purge function), `tracewise.worker.main()` (a fresh runtime per invocation = a process restart),
the analyze handler on the tenant role (audited per transaction), `HTTPProvider` (the model adapter core),
the investigator, validator, renderer and publisher, and the `ops` and `retention` CLIs (subprocesses).
SIMULATED: GitHub (FakeGitHub, injected because the API host is fixed by design), the model endpoint (a fake
speaking a test-defined wire format; provider recorded as `fake`), the git host (local http-backend).
Nothing here is evidence of real GitHub App compatibility or real-model accuracy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import signal
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from tests.context.conftest import make_fetcher
from tests.db.test_analyze_worker import APP_ID, World, head, server  # noqa: F401 - module fixtures
from tests.db.test_lifecycle import inst
from tests.db.test_process_entrypoints import ROOT, SECRET, _env, _stop, _wait_http, _web
from tests.db.test_recovery import run_obj
from tests.investigate.factory import b02_script
from tests.investigate.test_http_adapter import Server, TestWire
from tests.pg import SYSTEM
from tracewise import worker as worker_main
from tracewise.db.session import transaction
from tracewise.github import publish as publish_mod
from tracewise.investigate.http_adapter import AdapterConfig, HTTPProvider
from tracewise.jobs.handlers import analyze as analyze_mod
from tracewise.jobs.handlers.analyze import AnalyzeDeps, make_analyze_handler
from tracewise.jobs.worker import Worker


def post(port: int, event: str, body: dict[str, Any], delivery: str, secret: str = SECRET) -> httpx.Response:
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return httpx.post(
        f"http://127.0.0.1:{port}/webhooks/github",
        content=raw,
        timeout=10,
        headers={"X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig},
    )


def failure(head_sha: str, run_id: int = 55, repo_id: int = 7, name: str = "acme/coffee") -> dict[str, Any]:
    return {
        "action": "completed",
        "installation": {"id": 9},
        "repository": {"id": repo_id, "full_name": name},
        "workflow_run": {**run_obj(run_id, head_sha=head_sha, repo_id=repo_id, name=name), "head_branch": "feature"},
    }


def cli(module: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and module
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def tenant_audit(monkeypatch) -> Iterator[list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
    seen: list[tuple[str, str]] = []
    real = transaction

    @contextmanager
    def audited(pool: Any, *a: Any, **k: Any) -> Iterator[Any]:
        with real(pool, *a, **k) as c:
            r = c.execute("SELECT current_user AS u, current_setting('tracewise.installation_id', true) AS t").fetchone()
            seen.append((r["u"], r["t"]))
            yield c

    monkeypatch.setattr(analyze_mod, "transaction", audited)
    monkeypatch.setattr(publish_mod, "transaction", audited)
    yield seen


def test_local_operator_acceptance(pg, pool, tenant_pool, owner, server, tmp_path, head, tenant_audit) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    model = Server(*b02_script(), *b02_script())  # two analysis attempts (the first one's publication fails)
    model_client = httpx.Client(transport=httpx.MockTransport(model))
    closed: list[str] = []

    def runtime(st: Any, wid: str) -> worker_main.Runtime:  # what build_from_settings wires, with GitHub and model faked
        w.http = w.gh.http()  # fresh process: new HTTP client and token cache
        w.tokens = w.gh.provider(w.http)
        w.gh.next_tokens = [server.token] * 4  # the local git host accepts only its own token
        deps = AnalyzeDeps(
            tenant_pool,
            w.http,
            w.tokens,
            APP_ID,
            provider_factory=lambda: HTTPProvider(
                TestWire(), SecretStr("local-model-key-0001"), AdapterConfig("test-model-1"), client=model_client
            ),
            fetcher_factory=lambda: make_fetcher(server, tmp_path / "ws"),
        )
        return worker_main.Runtime(Worker(pool, {"analyze": make_analyze_handler(deps)}, wid), lambda: closed.append(wid))

    sys_env = _env(DATABASE_URL_SYSTEM=pg.url(SYSTEM), GITHUB_WEBHOOK_SECRET=SECRET)

    # 1. application startup
    web, port = _web(sys_env)
    try:
        _wait_http(port, web)
        assert httpx.get(f"http://127.0.0.1:{port}/readyz").json() == {"status": "ready"}
        # 2-4. signed webhooks, scope, durable queue and deduplication
        assert post(port, "installation", inst("created", repos=[(7, "acme/coffee"), (8, "acme/old")]), "i-1").status_code == 200
        post(
            port,
            "installation_repositories",
            {"action": "removed", "installation": {"id": 9}, "repositories_removed": [{"id": 8, "full_name": "acme/old"}]},
            "i-2",
        )
        assert post(port, "workflow_run", failure(head), "forged", secret="wrong-secret-000000").status_code == 401
        assert post(port, "workflow_run", failure(head, 56, 8, "acme/old"), "oos").json()["outcome"] == "repo_not_in_scope"
        assert post(port, "workflow_run", failure(head), "d-1").json()["outcome"] == "enqueued"
        assert post(port, "workflow_run", failure(head), "d-1").json()["outcome"] == "duplicate_delivery"
        assert post(port, "workflow_run", failure(head), "d-1b").json()["outcome"] == "duplicate_run"
        assert owner.execute("SELECT count(*) FROM job").fetchone() == (1,)
        (jid,) = owner.execute("SELECT id FROM job").fetchone()

        # 5-9. worker startup, claim, tenant-scoped evidence, diagnosis via the adapter, validation, publication,
        #      a transient publication failure, retry after a restart
        w.state.fault("POST", "cr", 502)
        assert worker_main.main(["--once", "--worker-id", "op-1"], build=runtime) == 0
        assert owner.execute("SELECT status FROM job").fetchone() == ("retry_wait",)
        w.ready(jid)
        assert worker_main.main(["--once", "--worker-id", "op-2"], build=runtime) == 0
        assert w.jobrow(jid)["status"] == "succeeded" and closed == ["op-1", "op-2"]
        assert (w.state.count("POST", "cc"), w.state.count("POST", "cr")) == (1, 1)
        assert any(r.url.path.endswith("/actions/jobs/101/logs") for r in w.gh.requests)  # evidence stage ran
        assert len(model.requests) == 4 and {str(r.url) for r in model.requests} == {TestWire.endpoint}
        prov, diag = owner.execute("SELECT provider, diagnosis FROM analysis").fetchone()
        assert prov == "fake" and any("assert 0.21 == 1.21" in pe["excerpt"] for pe in diag["primary_errors"])
        assert diag["status"] == "diagnosed" and diag["problem_location"]["line_start"] == 41  # validated, not abstained
        assert "coffee_shop/pricing.py:41" in w.all_ccs()[0]["body"]
        assert tenant_audit and set(tenant_audit) == {("tracewise_app", "9")}

        # 11. operational reporting (real CLI)
        rep = cli("tracewise.ops", "report", env=sys_env)
        doc = json.loads(rep.stdout)
        assert rep.returncode == 0 and doc["analyses"]["by_outcome"] == {"diagnosed": 1} and doc["jobs"]["retried"] == 1
        assert "acme" not in rep.stdout and SECRET not in rep.stdout + rep.stderr

        # 10. suspension and deletion through the web process
        assert post(port, "installation", inst("suspend"), "s-1").status_code == 200
        assert post(port, "workflow_run", failure(head, 57), "d-2").json()["outcome"] == "installation_inactive"
        assert post(port, "installation", inst("unsuspend"), "s-2").status_code == 200
        assert post(port, "installation", inst("deleted"), "x-1").status_code == 200
        writes = list(w.state.writes)
        assert worker_main.main(["--once", "--worker-id", "op-3"], build=runtime) == 0
        assert w.state.writes == writes  # nothing to do and nothing written after deletion

        # 13. graceful web shutdown and restart
        code, err = _stop(web)
        assert code in (0, -signal.SIGTERM) and "Application shutdown complete." in err and SECRET not in err
        web, port = _web(sys_env)
        _wait_http(port, web)
        assert httpx.get(f"http://127.0.0.1:{port}/readyz").json() == {"status": "ready"}
        assert post(port, "workflow_run", failure(head, 58), "d-3").json()["outcome"] == "installation_inactive"
    finally:
        _stop(web)

    # 12. retention purge (real CLI, real definer function)
    owner.execute("UPDATE installation SET purge_after = now() - interval '1 second' WHERE id = 9")
    ret = cli("tracewise.retention", env=sys_env)
    assert ret.returncode == 0 and json.loads(ret.stdout)["tenants_purged"] == [9]
    for t in ("repository", "workflow_run", "job", "analysis", "publication", "webhook_delivery"):
        assert owner.execute(f"SELECT count(*) FROM {t}").fetchone() == (0,), t  # noqa: S608
    assert owner.execute("SELECT status, purged_at IS NOT NULL FROM installation").fetchone() == ("deleted", True)
    assert {r.url.path for r in w.gh.requests if r.url.path.startswith("/app/installations/")} == {
        "/app/installations/9/access_tokens"
    }
