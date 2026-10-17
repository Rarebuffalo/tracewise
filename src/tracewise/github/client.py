"""GitHub REST client (T-302; FS-LOG-1, FS-LOG-3, FS-ERR-2, FS-SEC-5).

* Only endpoints in `endpoints.ENDPOINTS` can be called (AT-SEC-01), and only against the
  repository a `RepoClient` is bound to, with a token scoped to that repository.
* Rate limits (GitHub REST best practices): `retry-after` → wait that long; `x-ratelimit-remaining: 0`
  → wait until `x-ratelimit-reset`; other secondary limits → wait ≥60 s. Waits up to
  `inline_wait_max_s` happen in-process; longer ones raise `GitHubRetryable(retry_after_s=…)` so
  the job queue reschedules (FS-ERR-2).
* 5xx and transport errors: ≤`max_retries` inline retries with exponential backoff, then retryable.
* 401: token dropped and re-minted once. 403 (not rate limit) → `PermissionDenied` (no retry loop).
  404 → `NotFound`, 410 → `Gone`, 422 → permanent.
* Log download: the API answers 302 with a short-lived signed URL. It is followed only when it
  is https, carries no credentials, and its host is on the allowlist; the request to it carries
  **no** Authorization header and follows no further redirects. Bodies are streamed with a cap.
* JSON bodies are capped (`max_json_bytes`); pagination follows `Link: rel="next"` only on the API
  host and up to `max_pages`.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from tracewise.github import errors as err
from tracewise.github.endpoints import ENDPOINTS, SCOPES, Endpoint, covered
from tracewise.prepass.sanitize import redact

log = logging.getLogger(__name__)

API = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "tracewise-app"
# Observed/assumed log-storage hosts. Not documented by GitHub; verified in the LIVE gate (G-PLAT).
DEFAULT_LOG_HOST_SUFFIXES = (".actions.githubusercontent.com", ".blob.core.windows.net")
_LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
_PERM_HEADER = "x-accepted-github-permissions"


@dataclass(frozen=True)
class Limits:
    max_retries: int = 3
    inline_wait_max_s: float = 10.0
    secondary_default_wait_s: float = 60.0
    max_json_bytes: int = 10 * 1024 * 1024
    max_log_bytes: int = 512 * 1024 * 1024
    max_pages: int = 20
    read_timeout_s: float = 30.0
    connect_timeout_s: float = 5.0


class GitHubHTTP:
    """Transport + error policy. Holds no credentials itself; tokens are passed per call."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        limits: Limits | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        log_host_suffixes: tuple[str, ...] = DEFAULT_LOG_HOST_SUFFIXES,
        rnd: random.Random | None = None,
    ) -> None:
        self.limits = limits or Limits()
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self.limits.read_timeout_s, connect=self.limits.connect_timeout_s)
        )
        self._sleep, self._clock = sleep, clock
        self._log_hosts = log_host_suffixes
        self._rnd = rnd or random.Random()  # noqa: S311 - jitter only

    def close(self) -> None:
        self._client.close()

    # -------------------------------------------------------------- public entry points

    def app_call(self, name: str, app_jwt: str, params: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        ep = ENDPOINTS[name]
        if ep.auth != "app":
            raise ValueError(f"{name} is not an App-JWT endpoint")
        try:
            resp = self._send(ep, _fill(ep.path, params), app_jwt, json_body=body)
        except (err.NotFound, err.PermissionDenied) as e:
            if e.status == 422:
                raise
            raise err.InstallationUnavailable(f"installation token refused ({e.status})", e.status) from None
        except err.GitHubPermanent as e:
            if e.status == 401:
                raise err.InstallationUnavailable("installation token refused (401)", 401) from None
            raise
        doc = self._json(resp)
        if not isinstance(doc, dict):
            raise err.GitHubPermanent(f"{name}: unexpected response shape")
        return doc

    def call(
        self, ep: Endpoint, path: str, token: str, *, query: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        return self._send(ep, path, token, query=query, json_body=json_body)

    def paginate(
        self, ep: Endpoint, path: str, token: str, key: str | None, query: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        q = {"per_page": 100, **(query or {})}
        url: str | None = path
        pages = 0
        while url is not None:
            pages += 1
            if pages > self.limits.max_pages:
                log.warning("pagination cap reached", extra={"tw": {"endpoint": ep.name, "pages": pages - 1}})
                return
            resp = self._send(ep, url, token, query=q if pages == 1 else None)
            doc = self._json(resp)
            items = doc.get(key) if key else doc
            if not isinstance(items, list):
                raise err.GitHubPermanent(f"{ep.name}: unexpected response shape")
            yield from items
            url = self._next_link(resp)

    def stream_log(self, location: str) -> Iterator[str]:
        """Stream a signed log URL without credentials, line by line, capped at `max_log_bytes`."""
        self._check_log_url(location)
        with self._client.stream("GET", location, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as resp:
            if resp.status_code in (404, 410):
                raise (err.Gone if resp.status_code == 410 else err.NotFound)("log blob unavailable", resp.status_code)
            if resp.status_code != 200:
                raise err.GitHubRetryable(f"log download failed ({resp.status_code})")
            size = 0
            truncated = False
            pending = ""
            for chunk in resp.iter_text():
                room = self.limits.max_log_bytes - size
                data = chunk.encode()
                if len(data) > room:
                    chunk = data[:room].decode(errors="ignore")  # keep what fits; drop the partial tail line
                    truncated = True
                size += len(chunk.encode())
                pending += chunk
                *lines, pending = pending.split("\n")
                yield from lines
                if truncated:
                    break
            if pending and not truncated:
                yield pending
            if truncated:
                log.warning("log download truncated at cap", extra={"tw": {"cap_bytes": self.limits.max_log_bytes}})

    # -------------------------------------------------------------- internals

    def _send(
        self,
        ep: Endpoint,
        path_or_url: str,
        token: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = path_or_url if path_or_url.startswith(API + "/") else API + path_or_url
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {token}",
        }
        attempt = 0
        secondary_streak = 0
        while True:
            attempt += 1
            try:
                req = self._client.build_request(ep.method, url, params=query, json=json_body, headers=headers)
                resp = self._client.send(req, follow_redirects=False, stream=True)
            except httpx.TransportError as e:
                if attempt > self.limits.max_retries:
                    raise err.GitHubRetryable(f"{ep.name}: transport error ({type(e).__name__})") from None
                self._sleep(self._backoff(attempt))
                continue
            try:
                body = self._read_capped(resp)
            finally:
                resp.close()
            resp = httpx.Response(resp.status_code, headers=resp.headers, content=body, request=req)
            status = resp.status_code
            self._log(ep, status, resp)
            if status < 300 or (status == 302 and ep.name == "download_job_logs"):
                return resp
            wait = self._rate_limit_wait(resp, secondary_streak)
            if wait is not None:
                secondary_streak += 1
                if wait > self.limits.inline_wait_max_s or secondary_streak > self.limits.max_retries:
                    raise err.GitHubRetryable(f"{ep.name}: rate limited", retry_after_s=wait)
                self._sleep(wait)
                continue
            if status >= 500:
                if attempt > self.limits.max_retries:
                    raise err.GitHubRetryable(f"{ep.name}: server error {status}")
                self._sleep(self._backoff(attempt))
                continue
            raise self._error(ep, resp)

    def _read_capped(self, resp: httpx.Response) -> bytes:
        cap = self.limits.max_json_bytes
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cap:
            raise err.ResponseTooLarge(f"response larger than {cap} bytes")
        out = bytearray()
        for chunk in resp.iter_bytes():
            out += chunk
            if len(out) > cap:
                raise err.ResponseTooLarge(f"response larger than {cap} bytes")
        return bytes(out)

    def _rate_limit_wait(self, resp: httpx.Response, streak: int) -> float | None:
        if resp.status_code not in (403, 429):
            return None
        h = resp.headers
        if (ra := h.get("retry-after")) is not None:
            try:
                return max(0.0, float(ra))
            except ValueError:
                return self.limits.secondary_default_wait_s
        if h.get("x-ratelimit-remaining") == "0" and (reset := h.get("x-ratelimit-reset")):
            try:
                return max(0.0, float(reset) - self._clock()) + 1.0
            except ValueError:
                return self.limits.secondary_default_wait_s
        text = resp.text.lower()
        if resp.status_code == 429 or "secondary rate limit" in text or "rate limit" in text:
            return float(self.limits.secondary_default_wait_s * (2**streak))
        return None

    def _error(self, ep: Endpoint, resp: httpx.Response) -> err.GitHubPermanent:
        status = resp.status_code
        msg = f"{ep.name}: HTTP {status}"
        if status == 401:
            return err.GitHubPermanent(msg, 401)
        if status == 403:
            return err.PermissionDenied(msg, resp.headers.get(_PERM_HEADER) or ep.permission)
        if status == 404:
            return err.NotFound(msg, 404)
        if status == 410:
            return err.Gone(msg, 410)
        if status == 422:
            return err.PermissionDenied(msg, None, 422) if ep.auth == "app" else err.GitHubPermanent(msg, 422)
        return err.GitHubPermanent(msg, status)

    def _backoff(self, attempt: int) -> float:
        return float(min(8.0, 2 ** (attempt - 1)) * self._rnd.uniform(0.8, 1.2))

    def _json(self, resp: httpx.Response) -> Any:
        try:
            return json.loads(resp.content or b"null")
        except ValueError:
            raise err.GitHubPermanent("invalid JSON from GitHub") from None

    def _next_link(self, resp: httpx.Response) -> str | None:
        m = _LINK_NEXT.search(resp.headers.get("link", ""))
        if not m:
            return None
        nxt = m.group(1)
        if not nxt.startswith(API + "/"):
            raise err.UnsafeRedirect("pagination link left the API host")
        return nxt

    def _check_log_url(self, location: str) -> None:
        u = urlsplit(location)
        host = (u.hostname or "").lower()
        if u.scheme != "https" or u.username or u.password or not host:
            raise err.UnsafeRedirect("log redirect must be https without credentials")
        if not any(host.endswith(s) for s in self._log_hosts):
            raise err.UnsafeRedirect(f"log redirect host not allowed: {host}")

    @staticmethod
    def _log(ep: Endpoint, status: int, resp: httpx.Response) -> None:
        log.info(
            "github call",
            extra={
                "tw": {
                    "endpoint": ep.name,
                    "status": status,
                    "request_id": resp.headers.get("x-github-request-id"),
                    "ratelimit_remaining": resp.headers.get("x-ratelimit-remaining"),
                }
            },
        )


def _fill(template: str, params: dict[str, Any]) -> str:
    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in params:
            raise KeyError(f"missing path parameter {key}")
        value = str(params[key])
        if key == "path":
            parts = value.split("/")
            if not value or value.startswith("/") or ".." in parts or "" in parts or "\\" in value:
                raise ValueError("contents path must be repository-relative without '..'")
            return quote(value, safe="/")
        return quote(value, safe="")

    return re.sub(r"\{(\w+)\}", sub, template)


class RepoClient:
    """All installation-token calls for ONE repository of ONE installation, with ONE token scope."""

    def __init__(self, http: GitHubHTTP, tokens: Any, *, installation_id: int, repo_id: int, full_name: str, scope: str) -> None:
        owner, _, repo = full_name.partition("/")
        if not owner or not repo or "/" in repo:
            raise ValueError("full_name must be owner/repo")
        if scope not in SCOPES:
            raise ValueError(f"unknown token scope {scope!r}")
        self.http, self.tokens = http, tokens
        self.installation_id, self.repo_id, self.scope = installation_id, repo_id, scope
        self._owner, self._repo = owner, repo

    def _token(self) -> str:
        return str(self.tokens.token(self.installation_id, self.repo_id, self.scope).value)

    @property
    def full_name(self) -> str:
        return f"{self._owner}/{self._repo}"

    def git_fetch_token(self) -> str:
        """The analysis-scope token for a read-only git fetch of this one repository (T-304)."""
        if self.scope != "analysis":
            raise ValueError("git fetch uses the analysis-scope token only")
        return self._token()

    def invalidate_token(self) -> None:
        self.tokens.invalidate(self.installation_id, self.repo_id, self.scope)

    def _path(self, ep: Endpoint, **params: Any) -> str:
        if not covered(ep.permission, ep.access, SCOPES[self.scope]):
            raise ValueError(f"{ep.name} needs {ep.permission}:{ep.access}, outside the {self.scope!r} token scope")
        if "owner" in params or "repo" in params:
            raise ValueError("a RepoClient is bound to one repository; owner/repo cannot be overridden")
        return _fill(ep.path, {**params, "owner": self._owner, "repo": self._repo})

    def _with_reauth(self, fn: Callable[[str], Any]) -> Any:
        try:
            return fn(self._token())
        except err.GitHubPermanent as e:
            if e.status != 401:
                raise
            self.tokens.invalidate(self.installation_id, self.repo_id, self.scope)
            try:
                return fn(self._token())
            except err.GitHubPermanent as e2:
                if e2.status == 401:
                    raise err.InstallationUnavailable("token rejected after re-mint", 401) from None
                raise

    def request(
        self, name: str, *, query: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, **params: Any
    ) -> Any:
        ep = ENDPOINTS[name]
        if ep.auth != "installation" or ep.paginated:
            raise ValueError(f"{name} must be called via its dedicated method")
        path = self._path(ep, **params)
        resp = self._with_reauth(lambda t: self.http.call(ep, path, t, query=query, json_body=json_body))
        return self.http._json(resp) if resp.status_code != 302 else None

    def paginate(self, name: str, key: str | None, *, query: dict[str, Any] | None = None, **params: Any) -> list[Any]:
        ep = ENDPOINTS[name]
        if not ep.paginated:
            raise ValueError(f"{name} is not paginated")
        path = self._path(ep, **params)
        return list(self._with_reauth(lambda t: list(self.http.paginate(ep, path, t, key, query))))

    # -------------------------------------------------------------- typed helpers used by the pipeline

    def list_jobs(self, run_id: int, attempt: int) -> list[dict[str, Any]]:
        return self.paginate("list_jobs_for_attempt", "jobs", run_id=run_id, attempt=attempt)

    def failed_jobs(self, run_id: int, attempt: int) -> list[dict[str, Any]]:
        """FS-LOG-1: only failed/timed-out jobs are considered for log download."""
        return [j for j in self.list_jobs(run_id, attempt) if j.get("conclusion") in ("failure", "timed_out")]

    def job_log_lines(self, job_id: int) -> Iterator[str]:
        """FS-LOG-1: 302 → signed URL (valid ~1 min), fetched immediately without the token."""
        ep = ENDPOINTS["download_job_logs"]
        path = self._path(ep, job_id=job_id)
        resp = self._with_reauth(lambda t: self.http.call(ep, path, t))
        if resp.status_code != 302:
            raise err.GitHubPermanent("log endpoint did not redirect", resp.status_code)
        location = resp.headers.get("location", "")
        return self.http.stream_log(location)


def safe_error_text(e: BaseException) -> str:
    return redact(str(e))[:300]
