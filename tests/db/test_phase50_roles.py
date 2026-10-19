"""Phase 50, Batches C and D: the web process and the ops CLI enforce the system-plane role contract
(`require_system_plane`, already used by the worker). Disposable local PostgreSQL only; no credentials beyond the
test cluster's.

C: with the tenant role, /readyz said "ready" while every webhook got a 500; with the owner role the web process ran
   with owner rights. Startup now refuses a reachable wrong role, and readiness never reports ready on one.
D: with the tenant role, RLS hid every row, so `ops alerts` printed "insufficient_data" and exited 0, suppressing a
   firing alert. A role mismatch is now a distinct non-zero failure, never "no data".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.db.test_observability import _job
from tests.db.test_process_entrypoints import SECRET, _env, _stop, _wait_http, _web
from tests.pg import APP, OWNER, SYSTEM
from tracewise import ops
from tracewise.config import Settings
from tracewise.db.migrate import head_revision
from tracewise.db.session import make_pool
from tracewise.web.app import create_app


def app_for(pg: Any, role: str) -> tuple[TestClient, Any]:
    p = make_pool(pg.url(role), min_size=1, max_size=2)
    st = Settings(github_webhook_secret=SECRET)  # type: ignore[arg-type]
    return TestClient(create_app(st, p, schema_head=head_revision(), required_role="system")), p


# ------------------------------------------------------------------ C: readiness


@pytest.mark.parametrize(
    "role, expected", [(SYSTEM, (200, "ready")), (APP, (503, "wrong_database_role")), (OWNER, (503, "wrong_database_role"))]
)
def test_c_readiness_requires_the_system_role(pg, owner, role: str, expected: tuple[int, str]) -> None:  # type: ignore[no-untyped-def]
    client, p = app_for(pg, role)
    try:
        with client as c:
            r = c.get("/readyz")
            assert (r.status_code, r.json()["status"]) == expected
            assert pg.url(role) not in r.text and "password" not in r.text
    finally:
        p.close()


def test_c_readiness_with_an_unreachable_database_is_unavailable_not_wrong_role(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = make_pool(f"postgresql://tracewise_system@/tracewise?host={tmp_path / 'none'}&port=5432", min_size=0, timeout_s=0.5)
    st = Settings(github_webhook_secret=SECRET)  # type: ignore[arg-type]
    try:
        with TestClient(create_app(st, p, schema_head=head_revision(), required_role="system")) as c:
            r = c.get("/readyz")
            assert (r.status_code, r.json()) == (503, {"status": "unavailable"})
    finally:
        p.close()


# ------------------------------------------------------------------ C: startup


@pytest.mark.parametrize("role", [APP, OWNER])
def test_c_web_refuses_to_start_with_a_wrong_reachable_role(pg, owner, role: str) -> None:  # type: ignore[no-untyped-def]
    p, _ = _web(_env(DATABASE_URL_SYSTEM=pg.url(role), GITHUB_WEBHOOK_SECRET=SECRET))
    _, err = p.communicate(timeout=60)
    assert p.returncode != 0 and "DATABASE_URL_SYSTEM" in err and "BYPASSRLS system role" in err
    assert SECRET not in err and "Traceback" not in err


def test_c_web_with_the_system_role_starts_and_is_ready(pg, owner) -> None:  # type: ignore[no-untyped-def]
    import httpx

    p, port = _web(_env(DATABASE_URL_SYSTEM=pg.url(SYSTEM), GITHUB_WEBHOOK_SECRET=SECRET))
    try:
        _wait_http(port, p, timeout=60)
        assert httpx.get(f"http://127.0.0.1:{port}/readyz").json() == {"status": "ready"}
    finally:
        _stop(p)


# ------------------------------------------------------------------ D: ops CLI


def ops_with(pg: Any, role: str, *argv: str, capsys: Any) -> tuple[int, dict[str, Any]]:
    code = ops.main(list(argv), build=lambda: make_pool(pg.url(role), min_size=1, max_size=2))
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_d_alerts_fire_under_the_system_role(pg, owner, capsys) -> None:  # type: ignore[no-untyped-def]
    for _ in range(12):
        _job(owner, "dead", age_min=0.5, at=datetime.now(UTC))
    code, out = ops_with(pg, SYSTEM, "alerts", capsys=capsys)
    assert (code, out["state"]) == (2, "firing")


@pytest.mark.parametrize("role", [APP, OWNER])
@pytest.mark.parametrize("command", ["alerts", "report"])
def test_d_a_wrong_role_is_a_failure_never_insufficient_data(pg, owner, capsys, role: str, command: str) -> None:  # type: ignore[no-untyped-def]
    for _ in range(12):
        _job(owner, "dead", age_min=0.5, at=datetime.now(UTC))  # an alert that must not be suppressed
    code, out = ops_with(pg, role, command, capsys=capsys)
    assert code == 1 and out == {"error": "wrong_database_role", "command": command}


def test_d_genuinely_insufficient_data_is_still_exit_0(pg, owner, capsys) -> None:  # type: ignore[no-untyped-def]
    code, out = ops_with(pg, SYSTEM, "alerts", capsys=capsys)
    assert (code, out["state"]) == (0, "insufficient_data")


def test_d_database_failure_is_reported_as_unavailable(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    url = f"postgresql://tracewise_system@/tracewise?host={tmp_path / 'none'}&port=5432"
    code = ops.main(["alerts"], build=lambda: make_pool(url, min_size=0, timeout_s=0.5))
    assert code == 1 and json.loads(capsys.readouterr().out.strip().splitlines()[-1])["error"] == "database_unavailable"
