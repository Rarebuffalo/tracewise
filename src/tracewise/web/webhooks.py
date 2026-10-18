"""POST /webhooks/github (T-106; FS-EVT-1..4, FS-SEC-1 ingress).

Order of checks (nothing is parsed before the signature is verified):
  1. Declared Content-Length > 25 MB → 413 without reading.
  2. Body read with a hard 25 MB cap → 413.
  3. No webhook secret configured → 503 (fail closed).
  4. `X-Hub-Signature-256` HMAC-SHA256 over the raw body, constant-time → 401.
  5. Missing/invalid `X-GitHub-Delivery` or `X-GitHub-Event` → 400.
  6. JSON / schema validation → 400 (recorded as `rejected`).
  7. One DB transaction (ingest). Database unavailable → 503, nothing persisted, GitHub shows a
     failed delivery that the recovery job (T-702) redelivers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from tracewise.contracts import WorkflowRunEvent
from tracewise.db.session import DatabaseUnavailable
from tracewise.web.ingest import ingest_workflow_run, record_other
from tracewise.web.lifecycle import (
    InstallationEvent,
    InstallationRepositoriesEvent,
    process_installation,
    process_installation_repositories,
)

MAX_BODY = 25 * 1024 * 1024
_DELIVERY_ID = re.compile(r"^[A-Za-z0-9-]{1,200}$")
_EVENT = re.compile(r"^[a-z_]{1,64}$")

log = logging.getLogger(__name__)
router = APIRouter()


def _resp(status: int, outcome: str, **extra: object) -> JSONResponse:
    return JSONResponse({"outcome": outcome, **extra}, status_code=status)


def verify_signature(secret: bytes, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.strip().encode())


async def _read_capped(request: Request) -> bytes | None:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY):
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/webhooks/github")
async def github_webhook(request: Request) -> JSONResponse:
    state = request.app.state
    body = await _read_capped(request)
    if body is None:
        return _resp(413, "too_large")
    secret: bytes | None = state.webhook_secret
    if not secret:
        log.error("webhook secret not configured; refusing deliveries")
        return _resp(503, "not_configured")
    if not verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        log.warning("webhook signature rejected")
        return _resp(401, "bad_signature")
    delivery_id = request.headers.get("x-github-delivery", "")
    event = request.headers.get("x-github-event", "")
    if not _DELIVERY_ID.match(delivery_id) or not _EVENT.match(event):
        return _resp(400, "bad_headers")
    log_ctx = {"delivery_id": delivery_id, "event": event}

    if event == "ping":
        return _resp(200, "pong")
    try:
        doc = json.loads(body)
        if not isinstance(doc, dict):
            raise ValueError("payload is not an object")
    except ValueError:
        return await _reject(request, delivery_id, event, log_ctx, "invalid_json")
    action = doc.get("action") if isinstance(doc.get("action"), str) else None
    inst_raw = doc.get("installation", {}).get("id") if isinstance(doc.get("installation"), dict) else None
    inst = inst_raw if isinstance(inst_raw, int) else None

    try:
        if event in ("installation", "installation_repositories"):  # T-701
            model = InstallationEvent if event == "installation" else InstallationRepositoriesEvent
            try:
                lev = model.model_validate(doc)
            except ValidationError:
                return await _reject(request, delivery_id, event, log_ctx, "invalid_payload", action, inst)
            fn = process_installation if event == "installation" else process_installation_repositories
            lres = await _run_sync(request, fn, delivery_id, lev)
            log.info("lifecycle event", extra={"tw": {**log_ctx, "outcome": lres.outcome, "cancelled": lres.cancelled_jobs}})
            return _resp(200, lres.outcome, cancelled_jobs=lres.cancelled_jobs)
        if event != "workflow_run":
            new = await _run_sync(request, record_other, delivery_id, event, action, inst, "ignored")
            return _resp(202, "ignored" if new else "duplicate_delivery")
        try:
            parsed = WorkflowRunEvent.model_validate(doc)
        except ValidationError:
            return await _reject(request, delivery_id, event, log_ctx, "invalid_payload", action, inst)
        result = await _run_sync(request, ingest_workflow_run, delivery_id, parsed)
    except DatabaseUnavailable:
        log.error("database unavailable; delivery not recorded", extra={"tw": log_ctx})
        return _resp(503, "unavailable")
    log.info("webhook ingested", extra={"tw": {**log_ctx, "outcome": result.outcome, "job_id": result.job_id}})
    status = 202 if result.outcome == "enqueued" else 200
    return _resp(status, result.outcome, job_id=result.job_id)


async def _reject(
    request: Request,
    delivery_id: str,
    event: str,
    log_ctx: dict[str, str],
    why: str,
    action: str | None = None,
    inst: int | None = None,
) -> JSONResponse:
    log.warning("webhook payload rejected", extra={"tw": {**log_ctx, "reason": why}})
    try:
        await _run_sync(request, record_other, delivery_id, event, action, inst, "rejected")
    except DatabaseUnavailable:
        pass  # rejection is still reported; nothing else depends on the record
    return _resp(400, why)


async def _run_sync(request: Request, fn, *args):  # type: ignore[no-untyped-def]
    """Run blocking DB work in the threadpool so the event loop keeps accepting deliveries."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, request.app.state.pool, *args)
