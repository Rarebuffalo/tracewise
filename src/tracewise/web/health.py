"""Liveness and readiness probes. Readiness checks the database; neither leaks configuration."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from tracewise.db.session import DatabaseUnavailable, transaction

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    def ping() -> None:
        with transaction(request.app.state.pool, 2.0) as conn:
            conn.execute("SELECT 1")

    try:
        await run_in_threadpool(ping)
    except DatabaseUnavailable:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready"})
