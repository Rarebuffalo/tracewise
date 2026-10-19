"""FastAPI application factory (T-106). No docs/OpenAPI endpoints are exposed."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from tracewise.config import Settings
from tracewise.db.session import Conn
from tracewise.web import health, webhooks


def create_app(
    settings: Settings,
    pool: ConnectionPool[Conn],
    *,
    schema_head: str | None = None,
    on_shutdown: Callable[[], None] | None = None,
) -> FastAPI:
    """`pool` is the system plane (tracewise_system): ingress records deliveries before any tenant is known (T-705).

    `schema_head`: when set, `/readyz` also requires the database schema to be at this revision.
    `on_shutdown`: called once when the ASGI server shuts down (closes the pool in the runtime factory)."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if on_shutdown is not None:
                on_shutdown()

    app = FastAPI(title="tracewise", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    secret = settings.github_webhook_secret
    app.state.webhook_secret = secret.get_secret_value().encode() if secret else None
    app.state.pool = pool
    app.state.schema_head = schema_head
    app.include_router(webhooks.router)
    app.include_router(health.router)
    return app
