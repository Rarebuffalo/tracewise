"""ASGI entry point for the web process (T-1002 local foundation).

Run with an ASGI server, using the factory so nothing happens at import time:

    uvicorn --factory tracewise.web.asgi:create_runtime_app --host 127.0.0.1 --port 8000

Startup validates configuration and fails with the names of the missing settings only (never values). It never runs
migrations or maintenance. The database pool is the SYSTEM plane (`DATABASE_URL_SYSTEM`; webhook intake must
record deliveries before any tenant is known); it must be the BYPASSRLS system role, as for the worker: a reachable
wrong role refuses startup. Readiness (`/readyz`) requires the database to be reachable, the role to be the system
role AND the schema at this build's revision; liveness (`/healthz`) does not touch the database.
"""

from __future__ import annotations

from fastapi import FastAPI

from tracewise.config import Settings, get_settings, invalid_fields
from tracewise.db.migrate import head_revision
from tracewise.db.session import DatabaseUnavailable, WrongDatabaseRole, make_pool, require_system_plane
from tracewise.logging import configure_cli


class ConfigError(SystemExit):
    """Startup refused: message names the missing or invalid settings, never their values."""


def validate_web(st: Settings) -> None:
    missing = [
        n
        for n, v in (("GITHUB_WEBHOOK_SECRET", st.github_webhook_secret), ("DATABASE_URL_SYSTEM", st.database_url_system))
        if not v
    ]
    if missing:
        raise ConfigError("web process refused to start; missing: " + ", ".join(missing))
    if len(st.github_webhook_secret.get_secret_value()) < 16:  # type: ignore[union-attr]
        raise ConfigError("web process refused to start: GITHUB_WEBHOOK_SECRET is shorter than 16 characters")


def create_runtime_app() -> FastAPI:
    configure_cli()
    try:
        st = get_settings()
    except Exception as e:  # pydantic validation: report field names only
        raise ConfigError(f"web process refused to start: invalid configuration ({invalid_fields(e)})") from None
    validate_web(st)
    from tracewise.web.app import create_app

    pool = make_pool(st.database_url_system.get_secret_value())  # type: ignore[union-attr]
    try:  # the same role contract as the worker (T-705); an unreachable database is left to /readyz
        require_system_plane(pool)
    except WrongDatabaseRole as e:
        pool.close()
        raise ConfigError(f"web process refused to start: DATABASE_URL_SYSTEM {e}") from None
    except DatabaseUnavailable:
        pass
    return create_app(st, pool, schema_head=head_revision(), on_shutdown=pool.close, required_role="system")
