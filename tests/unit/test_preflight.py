"""T-801/T-802 local preflight: config-only, offline, prints check names and fixed explanations, never values."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from tests.github_fake import test_key_pem as key_pem
from tracewise import preflight
from tracewise.config import Settings

SECRET = "s3cr3t-" + "q" * 24
SYS = "postgresql://tracewise_system:pw-system@db/tw"
APP = "postgresql://tracewise_app:pw-app@db/tw"
OWNER = "postgresql://tracewise_owner:pw-owner@db/tw"


def key_file(tmp_path: Path, mode: int = 0o600, content: bytes | None = None, name: str = "app.pem") -> Path:
    p = tmp_path / name
    p.write_bytes(key_pem() if content is None else content)
    p.chmod(mode)
    return p


def settings(tmp_path: Path, **over: Any) -> Settings:
    base: dict[str, Any] = {
        "tw_env": "test",
        "database_url": APP,
        "database_url_system": SYS,
        "database_url_migrations": OWNER,
        "github_webhook_secret": SECRET,
        "github_app_id": 123,
        "github_app_private_key_path": key_file(tmp_path, name="default.pem"),
        "llm_provider": "fake",
        "analysis_quota_monthly": 100,
    }
    base.update(over)
    return Settings(_env_file=None, **base)


def results(st: Settings, process: str = "all") -> dict[str, str]:
    return {c.name: c.result for c in preflight.config_checks(st, process)}


def test_a_complete_test_configuration_passes_with_only_the_fake_provider_warning(tmp_path: Path) -> None:
    r = results(settings(tmp_path))
    assert not [n for n, v in r.items() if v == "fail"]
    assert r["llm_provider"] == "warn" and sum(v == "manual" for v in r.values()) == len(preflight.MANUAL)


@pytest.mark.parametrize(
    ("over", "check"),
    [
        ({"database_url_system": None}, "database_url_system"),
        ({"database_url": None}, "database_url"),
        ({"database_url": SYS}, "database_url"),
        ({"database_url": "postgresql://tracewise_system:other@db2/tw"}, "database_url"),
        ({"database_url_migrations": APP}, "database_url_migrations"),
        ({"github_webhook_secret": None}, "github_webhook_secret"),
        ({"github_webhook_secret": "short"}, "github_webhook_secret"),
        ({"github_webhook_secret": "<your-webhook-secret-here>"}, "github_webhook_secret"),
        ({"github_webhook_secret": "change-me-change-me-change-me"}, "github_webhook_secret"),
        ({"github_app_id": None}, "github_app_id"),
        ({"github_app_id": 0}, "github_app_id"),
        ({"github_app_private_key_path": None}, "github_app_private_key"),
        ({"github_app_private_key_path": Path("/nonexistent/app.pem")}, "github_app_private_key"),
        ({"tw_env": "staging"}, "llm_provider"),
    ],
)
def test_each_missing_or_malformed_input_fails_its_own_check(tmp_path: Path, over: dict[str, Any], check: str) -> None:
    assert results(settings(tmp_path, **over))[check] == "fail"


def test_the_private_key_must_be_owner_only_and_an_rsa_pem(tmp_path: Path) -> None:
    loose = settings(tmp_path, github_app_private_key_path=key_file(tmp_path, mode=0o644))
    assert results(loose)["github_app_private_key"] == "fail"
    junk = settings(tmp_path, github_app_private_key_path=key_file(tmp_path, content=b"-----BEGIN NOTHING-----\nAAAA\n"))
    assert results(junk)["github_app_private_key"] == "fail"
    d = tmp_path / "dir"
    d.mkdir(mode=0o700)
    assert results(settings(tmp_path, github_app_private_key_path=d))["github_app_private_key"] == "fail"


def test_process_scoping(tmp_path: Path) -> None:
    web = results(settings(tmp_path, database_url=None, github_app_id=None), "web")
    assert "database_url" not in web and "github_app_id" not in web and web["github_webhook_secret"] == "pass"
    worker = results(settings(tmp_path, github_webhook_secret=None), "worker")
    assert "github_webhook_secret" not in worker and worker["github_app_id"] == "pass"


def test_an_unset_quota_and_migration_url_are_warnings_not_failures(tmp_path: Path) -> None:
    r = results(settings(tmp_path, analysis_quota_monthly=None, database_url_migrations=None))
    assert r["analysis_quota_monthly"] == "warn" and r["database_url_migrations"] == "warn"


def test_output_never_contains_a_configured_value_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    st = settings(tmp_path)
    assert preflight.main([], settings=lambda: st) == 0
    bad = settings(tmp_path, github_webhook_secret="change-me-change-me-change-me", database_url=SYS)
    assert preflight.main([], settings=lambda: bad) == 2
    out = capsys.readouterr().out
    for value in (SECRET, "pw-system", "pw-app", "pw-owner", "change-me", str(tmp_path), "BEGIN"):
        assert value not in out
    lines = [json.loads(line) for line in out.splitlines()]
    assert lines[-1]["summary"]["failed"] >= 2


def test_invalid_settings_exit_3_naming_fields_only(capsys: pytest.CaptureFixture[str]) -> None:
    def boom() -> Settings:
        return Settings(_env_file=None, github_app_id="not-a-number-pw-x")

    assert preflight.main([], settings=boom) == 3
    out = capsys.readouterr().out
    assert "GITHUB_APP_ID" in out and "pw-x" not in out


def test_preflight_imports_no_network_client() -> None:
    tree = ast.parse(Path(preflight.__file__).read_text())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {m for m in mods if m.split(".")[0] in {"httpx", "requests", "socket", "urllib3", "http"}}
    assert not {m for m in mods if m.startswith(("tracewise.github.client", "tracewise.github.http", "tracewise.investigate"))}


def test_a_private_key_inside_a_git_working_tree_fails(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    (repo / "keys").mkdir()
    inside = key_file(repo / "keys", name="app.pem")
    assert results(settings(tmp_path, github_app_private_key_path=inside))["github_app_private_key"] == "fail"
    outside = key_file(tmp_path, name="outside.pem")
    assert results(settings(tmp_path, github_app_private_key_path=outside))["github_app_private_key"] == "pass"


def test_a_missing_git_binary_is_a_worker_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    assert results(settings(tmp_path), "worker").get("git_binary") in ("pass", "warn")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    r = results(settings(tmp_path), "worker")
    assert r["git_binary"] == "warn" and "git_binary" not in results(settings(tmp_path), "web")
