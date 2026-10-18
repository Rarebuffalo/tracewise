"""Phase 11/12: the documented `python -m tracewise.*` entry points, run as real subprocesses against the
disposable cluster (non-production roles, no passwords). Checks JSON logging is configured (events reach
stderr through the scrubbing filter), exit codes, and safe failure for missing or unreachable databases."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.pg import APP, SYSTEM

ROOT = Path(__file__).resolve().parents[2]


def cli(module: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DATABASE_URL", "GITHUB_", "OPENAI_", "LLM_"))}
    return subprocess.run(  # noqa: S603 - fixed interpreter and module
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        env={**base, **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def events(stderr: str) -> list[dict[str, Any]]:
    out = []
    for line in stderr.splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict) and "event" in doc:
            out.append(doc)
    return out


def test_retention_cli_logs_json_events_and_succeeds(pg, owner) -> None:  # type: ignore[no-untyped-def]
    p = cli("tracewise.retention", env={"DATABASE_URL_SYSTEM": pg.url(SYSTEM), "GITHUB_WEBHOOK_SECRET": "cli-test-secret-xyz"})
    assert p.returncode == 0, p.stderr[-500:]
    assert json.loads(p.stdout)["completed"] is True
    names = [e["event"] for e in events(p.stderr)]
    assert "retention.finished" in names  # INFO events reach stderr: logging is configured
    assert "cli-test-secret-xyz" not in p.stderr + p.stdout


def test_ops_cli_report_and_alert(pg, owner) -> None:  # type: ignore[no-untyped-def]
    env = {"DATABASE_URL_SYSTEM": pg.url(SYSTEM)}
    r = cli("tracewise.ops", "report", env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["latency"]["end_to_end_s"]["n"] == 0
    a = cli("tracewise.ops", "alerts", env=env)
    doc = json.loads(a.stdout)
    assert a.returncode == 0 and doc["state"] == "insufficient_data" and doc["threshold_status"] == "provisional"
    bad = cli("tracewise.ops", "alerts", "--threshold", "5", env=env)
    assert bad.returncode != 0 and "threshold must be" in bad.stderr


def test_unreachable_database_fails_closed_with_no_url_in_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"postgresql://tracewise_system@/tracewise?host={tmp_path / 'nosuch'}&port=5432"
    for module, args in (("tracewise.retention", ()), ("tracewise.ops", ("report",))):
        p = cli(module, *args, env={"DATABASE_URL_SYSTEM": url})
        assert p.returncode == 1, (module, p.returncode, p.stderr[-300:])
        assert str(tmp_path) not in p.stdout
        assert "Traceback" not in p.stderr


def test_missing_configuration_is_refused(pg) -> None:  # type: ignore[no-untyped-def]
    for module, args, needle in (
        ("tracewise.retention", (), "DATABASE_URL_SYSTEM"),
        ("tracewise.ops", ("report",), "DATABASE_URL_SYSTEM"),
        ("tracewise.recovery", ("both",), "DATABASE_URL_SYSTEM"),
    ):
        p = cli(module, *args, env={"DATABASE_URL": pg.url(APP)})  # only the tenant URL: must not be used instead
        assert p.returncode != 0 and needle in p.stderr, (module, p.stderr[-300:])


def test_tenant_role_url_given_as_system_url_fails_closed(pg, owner) -> None:  # type: ignore[no-untyped-def]
    p = cli("tracewise.retention", env={"DATABASE_URL_SYSTEM": pg.url(APP)})  # wrong role: no EXECUTE on the purge
    assert p.returncode == 1 and json.loads(p.stdout)["error"] == "InsufficientPrivilege"
