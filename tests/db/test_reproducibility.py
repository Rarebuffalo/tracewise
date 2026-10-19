"""Phase 26: another engineer can reproduce the local workflow from the documentation.

1. Consistency: every env var, CLI flag and entry point named in OPERATIONS.md, DEPLOYMENT-BLUEPRINT.md and
   .env.example exists in the code, and every setting is documented somewhere an operator reads.
2. Clean environment: a brand-new cluster built ONLY from scripts/db/provision_roles.sql, migrated by the
   non-superuser owner, then the documented web and worker commands run as subprocesses with the documented
   variables. (Processing a job needs GitHub, whose API host is fixed by design; the processing chain is proven
   in-process by test_operator_acceptance.py.)
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import psycopg
import pytest

from tests.db.test_fresh_install import SCRIPT, Cluster
from tests.db.test_process_entrypoints import ROOT, _env, _stop, _wait_event, _wait_http, _web, _worker_to_file
from tests.github_fake import test_key_pem as _key_pem
from tracewise.config import Settings
from tracewise.db.migrate import upgrade

DOCS = [ROOT / "docs" / "OPERATIONS.md", ROOT / "docs" / "DEPLOYMENT-BLUEPRINT.md", ROOT / "docs" / "IMPLEMENTATION-PLAN.md"]
CLI_MODULES = ("tracewise.worker", "tracewise.recovery", "tracewise.ops", "tracewise.retention")


def _doc_text() -> str:
    return "\n".join(p.read_text() for p in DOCS)


def _flags(module: str) -> set[str]:
    src = (ROOT / "src" / Path(*module.split("."))).with_suffix(".py").read_text()
    return set(re.findall(r'add_argument\("(--[a-z-]+)"', src))


def test_every_documented_variable_exists_and_every_setting_is_documented() -> None:
    settings = {f.upper() for f in Settings.model_fields}
    docs = _doc_text()
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", docs)) & {s for s in settings} | {
        v for v in re.findall(r"\b([A-Z][A-Z0-9_]+)=", docs) if v in settings
    }
    env_example = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.M))
    assert env_example <= settings, env_example - settings  # nothing in .env.example the code would ignore
    assert settings - (documented | env_example) == set(), settings - (documented | env_example)
    referenced = {
        v
        for v in re.findall(
            r"\b(DATABASE_URL(?:_[A-Z0-9_]+)?|(?:GITHUB|LLM|OPENAI|TW|INVESTIGATION|REPORT|LOG)_[A-Z0-9_]+)\b", docs
        )
    }
    unknown = {v for v in referenced if v not in settings and v != "GITHUB_TOKEN_LAB"}  # the removed PAT, named as removed
    assert unknown == set(), unknown  # docs name no variable the code does not read


def test_every_documented_cli_flag_and_entry_point_exists() -> None:
    docs = (ROOT / "docs" / "OPERATIONS.md").read_text() + (ROOT / "docs" / "DEPLOYMENT-BLUEPRINT.md").read_text()
    real = set().union(*(_flags(m) for m in CLI_MODULES)) | {"--factory", "--host", "--port"}  # uvicorn's own flags
    assert set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", docs)) <= real
    for m in CLI_MODULES:
        assert f"python -m {m}" in docs, m
        assert hasattr(importlib.import_module(m), "main")
    assert "tracewise.web.asgi:create_runtime_app" in docs
    assert callable(importlib.import_module("tracewise.web.asgi").create_runtime_app)


@pytest.fixture(scope="module")
def clean() -> Iterator[Cluster]:
    c = Cluster()
    try:
        c.run_script(SCRIPT.read_text())
        upgrade(c.url("tracewise_owner"))  # documented step 2: migrate as the (non-superuser) owner
        yield c
    finally:
        c.stop()


def test_documented_workflow_on_a_clean_environment(clean, tmp_path) -> None:  # type: ignore[no-untyped-def]
    key = tmp_path / "app.pem"
    key.write_bytes(_key_pem())
    key.chmod(0o600)
    secret = "repro-webhook-secret-000001"
    web_env = _env(DATABASE_URL_SYSTEM=clean.url("tracewise_system"), GITHUB_WEBHOOK_SECRET=secret)
    worker_env = _env(
        DATABASE_URL=clean.url("tracewise_app"),
        DATABASE_URL_SYSTEM=clean.url("tracewise_system"),
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_PATH=str(key),
        LLM_PROVIDER="fake",
        TW_ENV="test",
    )

    # Worker: role validation passes on the template's roles; idle; graceful stop.
    wlog = tmp_path / "worker.log"
    w = _worker_to_file(worker_env, wlog)
    _wait_event(w, wlog, "worker.started")  # role validation passed on the template's roles
    w.send_signal(signal.SIGTERM)
    assert w.wait(timeout=20) == 0 and '"worker.stopped"' in wlog.read_text()
    # Invalid role assignment on the clean install: refused, no credential in the output.
    bad = subprocess.run(
        [sys.executable, "-m", "tracewise.worker", "--once"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**worker_env, "DATABASE_URL": clean.url("tracewise_owner")},
        timeout=60,
        check=False,
    )
    assert bad.returncode == 2 and "not subject to row-level security" in bad.stderr

    # Web: readiness on the clean schema; signed install + ping; forged refused.
    web, port = _web(web_env)
    try:
        _wait_http(port, web)
        base = f"http://127.0.0.1:{port}"
        assert httpx.get(base + "/readyz").json() == {"status": "ready"}

        def send(event: str, body: dict[str, object], delivery: str, s: str = secret) -> httpx.Response:
            raw = json.dumps(body).encode()
            sig = "sha256=" + hmac.new(s.encode(), raw, hashlib.sha256).hexdigest()
            return httpx.post(
                base + "/webhooks/github",
                content=raw,
                headers={"X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig},
            )

        inst = {
            "action": "created",
            "installation": {"id": 41, "account": {"login": "org"}},
            "repositories": [{"id": 410, "full_name": "org/repo"}],
        }
        assert send("installation", inst, "r-1").json()["outcome"] == "processed"
        assert send("installation", inst, "r-2", s="not-the-secret-0000").status_code == 401
    finally:
        _stop(web)
    with psycopg.connect(clean.url("tracewise_app")) as c:  # tenant role without context sees nothing (RLS)
        assert c.execute("SELECT count(*) FROM installation").fetchone() == (0,)
    with psycopg.connect(clean.url("tracewise_system")) as c:
        assert c.execute("SELECT id, status FROM installation").fetchall() == [(41, "active")]
        assert c.execute("SELECT count(*) FROM webhook_delivery").fetchone() == (1,)  # the forged one was not recorded
    for module, args in (("tracewise.ops", ("report",)), ("tracewise.retention", ())):
        p = subprocess.run(  # noqa: S603
            [sys.executable, "-m", module, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=_env(DATABASE_URL_SYSTEM=clean.url("tracewise_system")),
            timeout=60,
            check=False,
        )
        assert p.returncode == 0, (module, p.stderr[-400:])
