"""FastAPI application factory (T-106). No docs/OpenAPI endpoints are exposed."""

from __future__ import annotations

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from tracewise.config import Settings
from tracewise.db.session import Conn
from tracewise.web import health, webhooks


def create_app(settings: Settings, pool: ConnectionPool[Conn]) -> FastAPI:
    app = FastAPI(title="tracewise", docs_url=None, redoc_url=None, openapi_url=None)
    secret = settings.github_webhook_secret
    app.state.webhook_secret = secret.get_secret_value().encode() if secret else None
    app.state.pool = pool
    app.include_router(webhooks.router)
    app.include_router(health.router)
    return app
