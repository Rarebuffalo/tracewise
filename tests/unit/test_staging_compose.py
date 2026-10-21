"""The staging Compose bundle (deploy/staging) keeps the deployment rules: separate credentials per process, no
published database port, the worker's stop grace, only real CLI entry points, secrets outside the repository."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "deploy" / "staging"


def compose() -> dict[str, Any]:
    doc = yaml.safe_load((BUNDLE / "compose.yaml").read_text())
    assert isinstance(doc, dict)
    return doc


def env_files(svc: dict[str, Any]) -> set[str]:
    v = svc.get("env_file", [])
    return {Path(x).name for x in ([v] if isinstance(v, str) else v)}


def test_each_process_gets_only_its_own_credentials() -> None:
    s = compose()["services"]
    want = {
        "web": {"system.env", "web.env"},
        "worker": {"system.env", "worker.env", "app.env"},
        "migrate": {"migrate.env"},  # the only long-lived consumer of the owner URL
        "preflight": {"system.env", "web.env", "worker.env", "app.env", "migrate.env"},  # checks all of them
        "recovery": {"system.env", "app.env"},
        "retention": {"system.env"},
        "ops": {"system.env"},
    }
    assert {k: env_files(v) for k, v in s.items() if k in want} == want
    with_key = {k for k, v in s.items() if "app.pem" in str(v.get("volumes", []))}
    assert with_key == {"worker", "preflight", "recovery"}
    assert all("pg_superuser_password" not in str(v) for k, v in s.items() if k != "db")


def test_the_proxy_waits_for_web_readiness() -> None:
    assert compose()["services"]["proxy"]["depends_on"] == {"web": {"condition": "service_healthy"}}


def test_database_is_never_published_and_only_the_proxy_listens() -> None:
    s = compose()["services"]
    assert "ports" not in s["db"] and "ports" not in s["web"] and "ports" not in s["worker"]
    assert sorted(s["proxy"]["ports"]) == ["443:443", "80:80"]


def test_worker_stop_grace_covers_the_job_deadline() -> None:
    m = re.fullmatch(r"(\d+)m", compose()["services"]["worker"]["stop_grace_period"])
    assert m and int(m.group(1)) * 60 >= 600


def test_secrets_come_from_a_required_directory_outside_the_bundle() -> None:
    text = (BUNDLE / "compose.yaml").read_text()
    refs = re.findall(r"\$\{TW_SECRETS_DIR[^}]*\}/([\w.]+)", text)
    assert set(refs) == {"pg_superuser_password", "system.env", "web.env", "worker.env", "app.env", "migrate.env", "app.pem"}
    assert "${TW_SECRETS_DIR:?" in text and not list(BUNDLE.glob("*.env")) and not list(BUNDLE.glob("*.pem"))


def test_every_command_is_a_real_entry_point() -> None:
    for name, svc in compose()["services"].items():
        argv = [*(svc.get("entrypoint") or []), *(svc.get("command") or [])]
        if argv[:2] == ["python", "-m"]:
            assert importlib.util.find_spec(argv[2]) is not None, name
        elif argv[:1] == ["uvicorn"]:
            assert "tracewise.web.asgi:create_runtime_app" in argv, name


def test_the_proxy_exposes_only_the_three_routes() -> None:
    caddy = (BUNDLE / "Caddyfile").read_text()
    assert "path /webhooks/github /healthz /readyz" in caddy and "respond 404" in caddy
    assert "request_body" not in caddy  # the app enforces 25 MB; a smaller proxy limit would break GitHub payloads


def test_secret_files_are_never_created_as_directories_when_missing() -> None:
    """A short-syntax bind of a missing file makes Docker create a root-owned directory in its place (seen locally);
    every secret-file mount must refuse instead."""
    for name, svc in compose()["services"].items():
        for v in svc.get("volumes", []):
            if "TW_SECRETS_DIR" in str(v):
                assert isinstance(v, dict) and v["bind"]["create_host_path"] is False and v["read_only"] is True, name
