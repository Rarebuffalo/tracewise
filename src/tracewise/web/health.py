"""Liveness and readiness probes. Readiness checks the database; neither leaks configuration."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from tracewise.db.session import DatabaseUnavailable, WrongDatabaseRole, require_system_plane, transaction

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    head = getattr(request.app.state, "schema_head", None)
    required_role = getattr(request.app.state, "required_role", None)

    def ping() -> bool:
        if required_role == "system":
            require_system_plane(request.app.state.pool)  # Phase 50 (C): never "ready" on the wrong role
        with transaction(request.app.state.pool, 2.0) as conn:
            if head is None:
                conn.execute("SELECT 1")
                return True
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            return row is not None and row["version_num"] == head

    try:
        ok = await run_in_threadpool(ping)
    except DatabaseUnavailable:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    except WrongDatabaseRole:  # reachable, but every webhook would fail (tenant role) or run as the owner
        return JSONResponse({"status": "wrong_database_role"}, status_code=503)
    if not ok:  # reachable, but not migrated to this build's schema: not ready (never migrates itself)
        return JSONResponse({"status": "schema_mismatch"}, status_code=503)
    return JSONResponse({"status": "ready"})
