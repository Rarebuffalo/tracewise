"""HTTP API for the early-access waitlist: `create_app()`. Mounted at /api/waitlist/*.

Same-origin by default (the website and this API share a deployment); extra origins only via
WAITLIST_ALLOWED_ORIGINS. Every mutating route requires a JSON body under 4 KB, checks Origin, is rate-limited, and
answers without revealing whether an address is already on the list.
"""

from __future__ import annotations

import hmac
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracewise.waitlist import ratelimit, service
from tracewise.waitlist.db import Conn, DatabaseUnavailable, get_pool
from tracewise.waitlist.email import Sender, make_sender
from tracewise.waitlist.security import (
    check_form_token,
    check_receipt,
    check_unsubscribe_token,
    decoy_receipt,
    issue_form_token,
    normalize_email,
    normalize_github,
)
from tracewise.waitlist.settings import WaitlistSettings, get_settings

log = logging.getLogger("tracewise.waitlist")
MAX_BODY = 4096
PREFIX = "/api/waitlist"


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=320)
    github: str | None = Field(None, max_length=100)
    updates: bool = False
    website: str = Field("", max_length=200)  # honeypot: people never see it
    form_token: str = Field("", max_length=200)
    turnstile_token: str | None = Field(None, max_length=4096)


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=200)


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt: str = Field(max_length=200)
    ci_failure_freq: Literal["daily", "weekly", "monthly", "rarely"]


BASE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _json(body: dict[str, Any] | None, status: int = 200, extra: dict[str, str] | None = None) -> Response:
    headers = {**BASE_HEADERS, **(extra or {})}
    if body is None:
        return Response(status_code=status, headers=headers)
    return JSONResponse(body, status_code=status, headers=headers)


def create_app(
    settings: WaitlistSettings | None = None, *, pool: ConnectionPool[Conn] | None = None, sender: Sender | None = None
) -> FastAPI:
    s = settings or get_settings()
    secret = s.secret_bytes()
    _sender = sender or make_sender(
        s.waitlist_email_mode,
        file_dir=s.waitlist_email_file_dir,
        api_key=s.resend_api_key.get_secret_value() if s.resend_api_key else None,
        sender=s.waitlist_email_from,
        reply_to=s.waitlist_email_reply_to,
    )

    def _pool() -> ConnectionPool[Conn]:
        if pool is not None:
            return pool
        if s.waitlist_database_url is None:
            raise DatabaseUnavailable("WAITLIST_DATABASE_URL is not set")
        return get_pool(s.waitlist_database_url.get_secret_value())

    blocked = s.signup_block_reason()
    if blocked:
        log.warning("waitlist.signups_closed", extra={"reason": blocked})

    app = FastAPI(title="Tracewise waitlist", docs_url=None, redoc_url=None, openapi_url=None)
    router = APIRouter(prefix=PREFIX)

    # ------------------------------------------------------------ request helpers
    def client_ip(req: Request) -> str:
        if s.trust_proxy():
            for h in ("x-vercel-forwarded-for", "x-forwarded-for", "x-real-ip"):
                v = req.headers.get(h)
                if v:
                    return v.split(",")[0].strip()[:64]
        return req.client.host if req.client else "unknown"

    def origin_ok(req: Request) -> bool:
        origin = req.headers.get("origin")
        if origin is None:
            return True  # not a browser request; still rate-limited
        o = urlparse(origin)
        host = req.headers.get("x-forwarded-host") if s.trust_proxy() else None
        host = (host or req.headers.get("host") or "").split(",")[0].strip()
        return (o.netloc != "" and o.netloc == host) or origin.rstrip("/") in s.allowed_origins()

    def cors_headers(req: Request) -> dict[str, str]:
        origin = req.headers.get("origin")
        if origin and origin.rstrip("/") in s.allowed_origins():
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        return {}

    async def read_json(req: Request, model: type[BaseModel]) -> tuple[BaseModel | None, Response | None]:
        if not origin_ok(req):
            return None, _json({"error": "forbidden_origin"}, 403)
        ctype = req.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return None, _json({"error": "unsupported_media_type"}, 415)
        declared = req.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY):
            return None, _json({"error": "too_large"}, 413)
        raw = await req.body()
        if len(raw) > MAX_BODY:
            return None, _json({"error": "too_large"}, 413)
        try:
            return model.model_validate(json.loads(raw)), None
        except (ValueError, ValidationError):
            return None, _json({"error": "invalid_request"}, 422, cors_headers(req))

    def guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(req: Request) -> Response:
            try:
                result: Response = await fn(req)
                return result
            except DatabaseUnavailable:
                log.error("waitlist.database_unavailable")
                return _json({"error": "unavailable"}, 503, {**cors_headers(req), "Retry-After": "30"})

        wrapper.__name__ = fn.__name__
        return wrapper

    def deliver_now(ids: list[uuid.UUID]) -> None:
        """Best-effort immediate delivery; failures stay in the outbox for the retry job."""
        if not ids:
            return
        try:
            service.process_outbox(_pool(), s, _sender, ids=ids, limit=len(ids), budget_s=6.0)
        except Exception as e:  # never fail the user's request because email delivery failed
            log.error("waitlist.inline_delivery_error", extra={"error": type(e).__name__})

    # ------------------------------------------------------------ routes
    @router.get("/health")
    async def health() -> Response:
        return _json({"ok": True, "email_mode": s.waitlist_email_mode, "accepting_signups": blocked is None})

    @router.get("/form")
    @guarded
    async def form(req: Request) -> Response:
        if blocked:
            return _json({"error": "signups_closed"}, 503, cors_headers(req))
        ratelimit.hit(_pool(), secret, ratelimit.FORM_PER_IP, client_ip(req))
        return _json({"form_token": issue_form_token(secret)}, 200, cors_headers(req))

    @router.post("/signup")
    @guarded
    async def signup(req: Request) -> Response:
        body, err = await read_json(req, SignupIn)
        if err is not None:
            return err
        assert isinstance(body, SignupIn)
        if blocked:  # nothing is stored: a signup we can't confirm by email would only be a broken promise
            return _json({"error": "signups_closed"}, 503, cors_headers(req))
        ok = _json({"status": "check_email", "receipt": decoy_receipt()}, 202, cors_headers(req))
        if body.website.strip():
            log.info("waitlist.signup_honeypot")
            return ok
        check = check_form_token(secret, body.form_token)
        if check == "invalid":
            return _json({"error": "form_expired"}, 400, cors_headers(req))
        if check == "too_fast":
            log.info("waitlist.signup_too_fast")
            return ok
        email = normalize_email(body.email)
        if email is None:
            return _json({"error": "invalid_email"}, 422, cors_headers(req))
        try:
            github = normalize_github(body.github)
        except ValueError:
            return _json({"error": "invalid_github"}, 422, cors_headers(req))
        ip = client_ip(req)
        if s.waitlist_turnstile_secret is not None:
            if not body.turnstile_token or not service.verify_turnstile(
                s.waitlist_turnstile_secret.get_secret_value(), body.turnstile_token, ip
            ):
                return _json({"error": "challenge_failed"}, 400, cors_headers(req))
        p = _pool()
        if not ratelimit.hit(p, secret, ratelimit.SIGNUP_PER_IP, ip):
            # Visible, so a real person on a busy shared network knows to try later instead of silently not joining.
            log.info("waitlist.signup_rate_limited", extra={"limit": "ip"})
            return _json({"error": "rate_limited"}, 429, {**cors_headers(req), "Retry-After": "3600"})
        if not ratelimit.hit(p, secret, ratelimit.SIGNUP_PER_EMAIL, email):
            log.info("waitlist.signup_rate_limited", extra={"limit": "email"})
            return ok  # silent per address: reveals nothing about it, and stores or sends nothing
        result = service.signup(p, s, email, github, body.updates)
        deliver_now(result.outbox_ids)
        return _json({"status": "check_email", "receipt": result.receipt}, 202, cors_headers(req))

    @router.post("/confirm")
    @guarded
    async def confirm(req: Request) -> Response:
        body, err = await read_json(req, TokenIn)
        if err is not None:
            return err
        assert isinstance(body, TokenIn)
        p = _pool()
        if not ratelimit.hit(p, secret, ratelimit.CONFIRM_PER_IP, client_ip(req)):
            return _json({"error": "rate_limited"}, 429, {**cors_headers(req), "Retry-After": "3600"})
        result = service.confirm(p, s, body.token.strip())
        deliver_now(result.outbox_ids)
        out: dict[str, Any] = {"status": result.status}
        if result.receipt:
            out["receipt"] = result.receipt
        return _json(out, 200, cors_headers(req))

    @router.post("/profile")
    @guarded
    async def profile(req: Request) -> Response:
        body, err = await read_json(req, ProfileIn)
        if err is not None:
            return err
        assert isinstance(body, ProfileIn)
        p = _pool()
        if not ratelimit.hit(p, secret, ratelimit.PROFILE_PER_IP, client_ip(req)):
            return _json({"error": "rate_limited"}, 429, cors_headers(req))
        sid = check_receipt(secret, body.receipt)
        if sid is not None:
            service.set_ci_frequency(p, sid, body.ci_failure_freq)
        return _json(None, 204, cors_headers(req))  # identical whether or not the receipt matched a signup

    @router.post("/unsubscribe")
    @guarded
    async def unsubscribe(req: Request) -> Response:
        body, err = await read_json(req, TokenIn)
        if err is not None:
            return err
        assert isinstance(body, TokenIn)
        p = _pool()
        if not ratelimit.hit(p, secret, ratelimit.UNSUBSCRIBE_PER_IP, client_ip(req)):
            return _json({"error": "rate_limited"}, 429, cors_headers(req))
        sid = check_unsubscribe_token(secret, body.token.strip())
        removed = sid is not None and service.delete_signup(p, sid)
        return _json({"status": "removed" if removed else "not_found"}, 200, cors_headers(req))

    @router.get("/count")
    @guarded
    async def count(req: Request) -> Response:
        data = service.public_count(_pool())
        return _json(
            data, 200, {**cors_headers(req), "Cache-Control": "public, max-age=300, s-maxage=600, stale-while-revalidate=3600"}
        )

    @router.get("/internal/outbox")
    @guarded
    async def outbox(req: Request) -> Response:
        """Retry job: Vercel Cron (Authorization: Bearer $CRON_SECRET), or any scheduler you point at it."""
        expected = s.cron_secret.get_secret_value() if s.cron_secret else ""
        given = req.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(given.encode(), f"Bearer {expected}".encode()):
            return _json({"error": "unauthorized"}, 401)
        p = _pool()
        stats = service.process_outbox(p, s, _sender, limit=25, budget_s=20.0)
        purged = service.purge(p)
        return _json({"delivery": stats, "purged": purged, "email_mode": s.waitlist_email_mode})

    @router.options("/{path:path}")
    async def preflight(req: Request, path: str) -> Response:
        h = cors_headers(req)
        if h:
            h.update(
                {
                    "Access-Control-Allow-Methods": "GET, POST",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Max-Age": "600",
                }
            )
        return _json(None, 204, h)

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def not_found(req: Request, path: str) -> Response:
        return _json({"error": "not_found"}, 404, cors_headers(req))  # never falls through to the website

    app.include_router(router)
    return app
