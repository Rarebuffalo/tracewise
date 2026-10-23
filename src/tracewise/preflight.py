"""Local preflight for the live validation stages (T-801/T-802; LIVE-VALIDATION-PLAN S0-S3). Offline by design.

`python -m tracewise.preflight [--process web|worker|all] [--database]`

Checks the configuration a live run needs and prints one line per check (name, result, a fixed explanation),
never a value. It has no GitHub client and makes no network call: it cannot start a live action. With `--database`
it also connects, read-only, to the configured databases to check the role contracts and the schema revision.
Items only GitHub can confirm (App permissions, events, webhook URL) are listed as `manual`.

Exit codes: 0 every check passed (warnings allowed); 2 at least one check failed; 3 the settings themselves are
invalid.
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tracewise.config import Settings, invalid_fields

PLACEHOLDER_MARKERS = ("<", ">", "change-me", "changeme", "placeholder", "example", "xxxx")
MANUAL = (
    "GitHub App permissions are exactly: Actions read, Contents read, Metadata read, Pull requests write, Checks write",
    "GitHub App subscribes to the workflow_run event (installation events are always sent)",
    "Webhook URL is the test deployment's POST /webhooks/github over HTTPS, with the same secret as GITHUB_WEBHOOK_SECRET",
    "The App is installed only on the approved test organisation's repositories (LIVE-VALIDATION-PLAN preconditions)",
)


@dataclass(frozen=True)
class Check:
    name: str
    result: str  # pass | warn | fail | manual
    detail: str


def _user(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlsplit(url).username
    except ValueError:
        return None


def _looks_placeholder(value: str) -> bool:
    v = value.lower()
    return any(m in v for m in PLACEHOLDER_MARKERS)


def config_checks(st: Settings, process: str) -> list[Check]:
    out: list[Check] = []
    add = out.append
    system = st.database_url_system.get_secret_value() if st.database_url_system else None
    tenant = st.database_url.get_secret_value() if st.database_url else None
    migrations = st.database_url_migrations.get_secret_value() if st.database_url_migrations else None

    add(
        Check(
            "database_url_system",
            "pass" if system else "fail",
            "system-plane URL is set" if system else "DATABASE_URL_SYSTEM is missing",
        )
    )
    if process in ("worker", "all"):
        if not tenant:
            add(Check("database_url", "fail", "DATABASE_URL (tenant plane) is missing"))
        elif tenant == system or (_user(tenant) and _user(tenant) == _user(system)):
            add(Check("database_url", "fail", "DATABASE_URL and DATABASE_URL_SYSTEM must use different roles"))
        else:
            add(Check("database_url", "pass", "tenant-plane URL is set and uses a different role"))
    if migrations:
        same = migrations in (system, tenant) or _user(migrations) in {_user(system), _user(tenant)} - {None}
        add(
            Check(
                "database_url_migrations",
                "fail" if same else "pass",
                "the migration URL must use the owner role, not a runtime role" if same else "migration URL is separate",
            )
        )
    else:
        add(
            Check(
                "database_url_migrations",
                "warn",
                "DATABASE_URL_MIGRATIONS unset: migrations need the owner URL passed explicitly",
            )
        )

    if process in ("web", "all"):
        secret = st.github_webhook_secret.get_secret_value() if st.github_webhook_secret else ""
        if not secret:
            add(Check("github_webhook_secret", "fail", "GITHUB_WEBHOOK_SECRET is missing"))
        elif len(secret) < 16:
            add(Check("github_webhook_secret", "fail", "GITHUB_WEBHOOK_SECRET is shorter than 16 characters"))
        elif _looks_placeholder(secret):
            add(Check("github_webhook_secret", "fail", "GITHUB_WEBHOOK_SECRET looks like a placeholder"))
        else:
            add(Check("github_webhook_secret", "pass", "webhook secret is set and not a placeholder"))

    if process in ("worker", "all"):
        add(
            Check(
                "github_app_id",
                "pass" if (st.github_app_id or 0) > 0 else "fail",
                "App id is set" if (st.github_app_id or 0) > 0 else "GITHUB_APP_ID is missing or not positive",
            )
        )
        add(_key_check(st.github_app_private_key_path))
        if shutil.which("git"):
            add(Check("git_binary", "pass", "git is available for code context"))
        else:
            add(Check("git_binary", "warn", "git is not installed: code context uses the slower contents API"))
        if st.llm_provider == "fake":
            if st.tw_env == "test":
                add(
                    Check(
                        "llm_provider",
                        "warn",
                        "fake provider (TW_ENV=test): no root cause is named (inconclusive or could_not_complete)",
                    )
                )
            else:
                add(Check("llm_provider", "fail", "LLM_PROVIDER=fake is refused outside TW_ENV=test"))
        else:
            add(Check("llm_provider", "fail", "LLM_PROVIDER=openai is not enabled in this build (MODEL-ADAPTER §2b)"))
    if st.analysis_quota_monthly is None:
        add(Check("analysis_quota_monthly", "warn", "no monthly analysis quota configured (owner decision)"))
    else:
        add(Check("analysis_quota_monthly", "pass", "monthly analysis quota is configured"))
    out.extend(Check(f"manual_{i + 1}", "manual", text) for i, text in enumerate(MANUAL))
    return out


def _key_check(path: Path | None) -> Check:
    name = "github_app_private_key"
    if path is None:
        return Check(name, "fail", "GITHUB_APP_PRIVATE_KEY_PATH is missing")
    try:
        st = path.stat()
    except OSError:
        return Check(name, "fail", "private key file is not readable")
    if not stat.S_ISREG(st.st_mode):
        return Check(name, "fail", "private key path is not a regular file")
    if st.st_mode & 0o077:
        return Check(name, "fail", "private key file must be readable by its owner only (chmod 600)")
    if _inside_a_repository(path):
        return Check(name, "fail", "private key file is inside a git working tree; keep it outside (it must never be committed)")
    from tracewise.github.auth import AppCredentials

    try:
        AppCredentials.from_pem_file(1, path)
    except Exception:  # never echo the parser's message: it may quote the file
        return Check(name, "fail", "private key file is not an RSA private key in PEM format")
    return Check(name, "pass", "private key file is RSA PEM with owner-only permissions")


def _inside_a_repository(path: Path) -> bool:
    """Whether the file lies in a git working tree: this source tree, or any directory above it with `.git`."""
    target = path.resolve()
    roots = {Path(__file__).resolve().parents[2]}
    roots |= {d for d in (target.parent, *target.parents) if (d / ".git").exists()}
    return any(target.is_relative_to(r) and (r / ".git").exists() for r in roots)


def _definer_check(pool: Any) -> Check:
    """The SECURITY DEFINER purge must be owned by a non-superuser (migrations run as the owner role, not a superuser)."""
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT coalesce(bool_or(r.rolsuper), false) AS superuser_owned FROM pg_proc p
               JOIN pg_roles r ON r.oid = p.proowner
               WHERE p.pronamespace = 'public'::regnamespace AND p.prosecdef"""
        ).fetchone()
    if row and row["superuser_owned"]:
        return Check("definer_owner", "fail", "a SECURITY DEFINER function is owned by a superuser: migrate as the owner role")
    return Check("definer_owner", "pass", "SECURITY DEFINER functions are owned by a non-superuser")


def database_checks(st: Settings, process: str) -> list[Check]:
    """Read-only: role contracts and schema revision on the configured databases."""
    from tracewise.db.migrate import head_revision
    from tracewise.db.session import (
        DatabaseUnavailable,
        SchemaMismatch,
        WrongDatabaseRole,
        make_pool,
        require_schema_at,
        require_system_plane,
        require_tenant_plane,
    )

    out: list[Check] = []
    plans: list[tuple[str, str | None, Callable[..., None]]] = [
        ("system_role", st.database_url_system.get_secret_value() if st.database_url_system else None, require_system_plane)
    ]
    if process in ("worker", "all"):
        plans.append(("tenant_role", st.database_url.get_secret_value() if st.database_url else None, require_tenant_plane))
    for name, url, check in plans:
        if not url:
            out.append(Check(name, "fail", "URL not configured"))
            continue
        pool = make_pool(url, min_size=0, max_size=1, timeout_s=3.0)
        try:
            check(pool)
            if name == "system_role":
                require_schema_at(pool, head_revision())
                out.append(Check("schema_revision", "pass", "database is at this build's migration head"))
                out.append(_definer_check(pool))
            out.append(Check(name, "pass", "role satisfies its plane's contract"))
        except DatabaseUnavailable:
            out.append(Check(name, "fail", "database unreachable"))
        except WrongDatabaseRole:
            out.append(Check(name, "fail", "wrong database role for this plane"))
        except SchemaMismatch:
            out.append(Check("schema_revision", "fail", "database is not at this build's migration head; run migrations"))
        except Exception as e:
            out.append(Check(name, "fail", f"database check failed ({type(e).__name__})"))
        finally:
            pool.close()
    return out


def main(argv: list[str] | None = None, settings: Callable[[], Settings] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.preflight")
    ap.add_argument("--process", choices=["web", "worker", "all"], default="all")
    ap.add_argument("--database", action="store_true", help="also check database roles and schema (read-only)")
    a = ap.parse_args(argv)
    try:
        st = (settings or Settings)()
    except Exception as e:
        print(json.dumps({"check": "settings", "result": "fail", "detail": f"invalid configuration ({invalid_fields(e)})"}))
        return 3
    checks = config_checks(st, a.process)
    if a.database:
        checks += database_checks(st, a.process)
    for c in checks:
        print(json.dumps({"check": c.name, "result": c.result, "detail": c.detail}))
    failed = sum(c.result == "fail" for c in checks)
    print(
        json.dumps(
            {
                "summary": {
                    "failed": failed,
                    "warnings": sum(c.result == "warn" for c in checks),
                    "manual": sum(c.result == "manual" for c in checks),
                }
            }
        )
    )
    return 2 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
