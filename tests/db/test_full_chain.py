"""Phase 15: independently verified full chain, for push and pull-request runs.

Real: FastAPI app and HMAC check, Postgres queue, worker, tenant-plane analysis under RLS (verified per
transaction), evidence collection, the validator and renderer, the publisher, recovery and the purge function.
SIMULATED (never evidence of external behaviour): GitHub API (FakeGitHub), the model (ScriptedProvider, recorded
as provider `fake`), and the git host (local http-backend).

Each stage leaves a mark the test checks, so the test fails if any stage is skipped: log download requests,
log-derived excerpt in the stored diagnosis, the location from the code context in the published body, the
lease/attempt counts from the retry, the recovery outcomes, and the purge counts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from tests.db.test_analyze_worker import World, head, server  # noqa: F401 - module fixtures
from tests.db.test_cross_phase import _client
from tests.db.test_lifecycle import inst, send
from tests.db.test_recovery import Hub, delivery, redeliver, run_obj, sweep
from tracewise import retention
from tracewise.db.session import transaction
from tracewise.github import publish as publish_mod
from tracewise.jobs.handlers import analyze as analyze_mod


@pytest.fixture
def tenant_tx_audit(monkeypatch) -> Iterator[list[dict[str, Any]]]:  # type: ignore[no-untyped-def]
    """Records the role and RLS context of every analysis/publisher transaction."""
    seen: list[dict[str, Any]] = []
    real = transaction

    @contextmanager
    def audited(pool: Any, *a: Any, **k: Any) -> Iterator[Any]:
        with real(pool, *a, **k) as c:
            r = c.execute("SELECT current_user AS u, current_setting('tracewise.installation_id', true) AS t").fetchone()
            seen.append({"role": r["u"], "tenant": r["t"]})
            yield c

    monkeypatch.setattr(analyze_mod, "transaction", audited)
    monkeypatch.setattr(publish_mod, "transaction", audited)
    yield seen


@pytest.mark.parametrize("kind", ["push", "pull_request"])
def test_verified_full_chain(pool, owner, server, tmp_path, head, tenant_tx_audit, kind) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    w = World(pool, owner, server, tmp_path / "ws", head)
    if kind == "pull_request":
        w.state.commit_pulls[w.head] = [w.state.pr(12, w.head)]
    with _client(pool) as c:
        send(c, "installation", inst("created", repos=[(7, "acme/coffee")]))
        run = {**run_obj(55, head_sha=head), "head_branch": "feature", "event": kind}
        raw = json.dumps(
            {
                "action": "completed",
                "installation": {"id": 9},
                "repository": {"id": 7, "full_name": "acme/coffee"},
                "workflow_run": run,
            }
        ).encode()
        good = "sha256=" + hmac.new(c.secret.encode(), raw, hashlib.sha256).hexdigest()
        tampered = raw.replace(b'"run_attempt": 1', b'"run_attempt": 2')
        h = {"X-GitHub-Event": "workflow_run", "X-GitHub-Delivery": "chain-1"}
        assert c.post("/webhooks/github", content=tampered, headers={**h, "X-Hub-Signature-256": good}).status_code == 401
        assert owner.execute("SELECT count(*) FROM webhook_delivery WHERE delivery_id = 'chain-1'").fetchone() == (0,)
        assert c.post("/webhooks/github", content=raw, headers={**h, "X-Hub-Signature-256": good}).json()["outcome"] == "enqueued"
    (jid,) = owner.execute("SELECT id FROM job").fetchone()

    surface_post = "prc" if kind == "pull_request" else "cc"
    w.state.fault("POST", "cr", 502)
    w.run()
    w.ready(jid)
    w.run()
    j = w.jobrow(jid)
    assert (j["status"], j["attempts"]) == ("succeeded", 2)

    # Stage marks: evidence collected (log fetched through the API and its redirect) ...
    assert any(r.url.path.endswith("/actions/jobs/101/logs") for r in w.gh.requests)
    assert any(r.url.host.endswith("blob.core.windows.net") for r in w.gh.requests)
    # ... diagnosis by the FAKE provider, validated, with a log-derived excerpt ...
    prov, diag = owner.execute("SELECT provider, diagnosis FROM analysis").fetchone()
    assert prov == "fake"
    assert any("assert 0.21 == 1.21" in pe["excerpt"] for pe in diag["primary_errors"])
    # ... and published: exactly one write per surface despite the retry, with the code-context location.
    assert w.state.count("POST", surface_post) == 1 and w.state.count("POST", "cr") == 1
    body = (w.state.pr_comments[12][0] if kind == "pull_request" else w.all_ccs()[0])["body"]
    assert "coffee_shop/pricing.py:41" in body
    if kind == "pull_request":
        assert w.all_ccs() == [] and w.state.count("POST", "cc") == 0  # no commit comment for a matched PR
    else:
        assert w.all_prcs() == []
    assert len(w.state.check_runs) == 1 and w.state.check_runs[0]["conclusion"] == "neutral"

    # Every analysis/publisher transaction ran as the restricted tenant role with installation 9 set.
    assert tenant_tx_audit and all(t == {"role": "tracewise_app", "tenant": "9"} for t in tenant_tx_audit), tenant_tx_audit

    # Recovery through its real paths: nothing new.
    hub = Hub(w.gh)
    hub.deliveries = [delivery(41, "chain-1")]
    hub.runs[7] = [run_obj(55, head_sha=head)]
    assert redeliver(pool, hub).already_received == 1 and hub.redelivered == []
    assert sweep(pool, hub).duplicates == 1

    # Uninstall and purge through the real function.
    with _client(pool) as c:
        send(c, "installation", inst("deleted"))
    owner.execute("UPDATE installation SET purge_after = now() - interval '1 second'")
    s = retention.purge(pool)
    assert s.completed and s.tenants_purged == [9] and s.deleted["tenant_rows"] > 0
    assert owner.execute("SELECT count(*) FROM analysis").fetchone() == (0,)
    writes_before = list(w.state.writes)
    assert not w.worker().run_once() and w.state.writes == writes_before  # prohibited: any write after uninstall
    minted_for = {r.url.path for r in w.gh.requests if r.url.path.startswith("/app/installations/")}
    assert minted_for == {"/app/installations/9/access_tokens"}  # no token for any other installation
