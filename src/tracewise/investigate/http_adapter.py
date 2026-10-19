"""Provider-neutral HTTP model adapter core (T-605 preparation; Phase 19). NOT a real-model integration.

What this module guarantees, independent of any vendor (all verified offline with a fake transport):

* Credentials: the API key is a `SecretStr`, sent only in the codec's auth header, registered with the log
  secret filter, and never part of an exception message or a log field.
* Bounded work: one request per attempt; at most `max_retries` retries (only for 429, 5xx, timeouts and
  transport errors), with capped backoff that never exceeds the investigator's remaining time budget.
  Authentication/permission (401/403) and request errors (other 4xx) fail at once.
* Bounded input: the response body is read with a byte cap; anything larger is refused.
* Strict decoding: the codec turns a JSON document into a `StepResponse` or raises `WireError`. Invalid JSON,
  a wrong shape, an empty answer, or text longer than the request's `max_output_chars` all fail closed as
  `ProviderError`, which the investigator turns into an inconclusive result (never a guessed diagnosis).
* No authority: the adapter returns text and tool-call *requests* only. Tool names and arguments stay untrusted;
  the investigator validates every call against its four read-only tools. Nothing here executes, writes or
  fetches anything other than the codec's single endpoint.
* Error redaction: messages carry the provider, the HTTP status and an error class — never the response body,
  request content, headers or the key.

The vendor wire format lives in a `WireCodec`. **No OpenAI codec ships**: the repository holds no recorded
OpenAI API contract, and guessing one would be unverifiable (docs/MODEL-ADAPTER.md lists exactly what must be
recorded before it is written). `LLM_PROVIDER=openai` therefore still refuses to start.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from pydantic import SecretStr

from tracewise.investigate.provider import ProviderError, ProviderTimeout, StepRequest, StepResponse
from tracewise.logging import secret_filter

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


class WireError(ValueError):
    """The provider's document does not match the codec's contract. Message must not quote the document."""


class ProviderAuthError(ProviderError):
    """401/403: the key is missing, wrong or not allowed. Permanent; never retried."""


class ProviderRequestError(ProviderError):
    """Other 4xx: the request was refused as invalid. Permanent; never retried."""


class ProviderQuotaError(ProviderError):
    """A 429 the vendor documents as quota, billing or spend exhaustion: needs owner action, never retried."""


class ProviderUnavailable(ProviderError):
    """429/5xx/transport failure after the bounded retries."""


class WireCodec(Protocol):
    name: Literal["openai", "fake"]
    endpoint: str

    def auth_headers(self, key: str) -> dict[str, str]: ...

    def encode(self, model: str, request: StepRequest) -> dict[str, Any]: ...

    def decode(self, doc: Any) -> StepResponse: ...


@dataclass(frozen=True)
class AdapterConfig:
    model: str
    max_retries: int = 2
    max_response_bytes: int = 1_000_000
    connect_timeout_s: float = 5.0
    backoff_s: float = 1.0
    max_backoff_s: float = 8.0
    allow_loopback_http: bool = False  # tests only: a local fake endpoint

    def __post_init__(self) -> None:
        if not _MODEL.match(self.model or ""):
            raise ValueError("model name is missing or malformed")
        if not 0 <= self.max_retries <= 3:
            raise ValueError("max_retries must be 0..3")
        if not 1024 <= self.max_response_bytes <= 10_000_000:
            raise ValueError("max_response_bytes out of range")


class HTTPProvider:
    """Implements `tracewise.investigate.provider.Provider` over one HTTPS endpoint."""

    def __init__(
        self,
        codec: WireCodec,
        api_key: SecretStr | None,
        config: AdapterConfig,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rnd: random.Random | None = None,
    ) -> None:
        key = api_key.get_secret_value() if api_key is not None else ""
        if len(key) < 8 or any(c.isspace() for c in key):
            raise ValueError("API key is missing or malformed")
        u = httpx.URL(codec.endpoint)
        loopback = config.allow_loopback_http and u.scheme == "http" and u.host in ("127.0.0.1", "localhost")
        if not (u.scheme == "https" or loopback) or u.userinfo:
            raise ValueError("provider endpoint must be https without credentials")
        self.codec, self.config = codec, config
        self._key = SecretStr(key)
        secret_filter.register(key)
        self._client = client or httpx.Client(follow_redirects=False)
        self._sleep, self._clock = sleep, clock
        self._rnd = rnd or random.Random()  # noqa: S311 - backoff jitter only

    @property
    def name(self) -> Literal["openai", "fake"]:
        return self.codec.name

    @property
    def model(self) -> str:
        return self.config.model

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:
        return f"HTTPProvider(provider={self.codec.name}, model={self.config.model}, key=<hidden>)"

    # ------------------------------------------------------------------ Provider.step

    def step(self, request: StepRequest) -> StepResponse:
        body = json.dumps(self.codec.encode(self.config.model, request)).encode()
        deadline = self._clock() + max(0.0, request.timeout_s)
        attempt = 0
        while True:
            retry_after: float | None = None
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise ProviderTimeout(f"{self.name}: time budget exhausted")
            try:
                status, raw, retry_after = self._post(body, remaining)
            except _TooLarge:
                raise ProviderError(f"{self.name}: response exceeds {self.config.max_response_bytes} bytes") from None
            except httpx.TimeoutException:
                failure: ProviderError = ProviderTimeout(f"{self.name}: request timed out")
            except httpx.TransportError as e:
                failure = ProviderUnavailable(f"{self.name}: transport error ({type(e).__name__})")
            else:
                if 200 <= status < 300:
                    return self._decode(raw, request)
                if status in (401, 403):
                    raise ProviderAuthError(f"{self.name}: authentication refused (HTTP {status})")
                if status == 429 or status >= 500:
                    if self._permanent(status, raw):  # e.g. quota or billing: retrying cannot help
                        raise ProviderQuotaError(f"{self.name}: quota, billing or usage limit (HTTP {status})")
                    failure = ProviderUnavailable(f"{self.name}: HTTP {status}")
                else:
                    raise ProviderRequestError(f"{self.name}: request refused (HTTP {status})")
                if retry_after is not None and retry_after > deadline - self._clock():
                    raise failure  # the provider asks us to wait longer than the investigation may take
            if attempt >= self.config.max_retries:
                raise failure
            attempt += 1
            wait = min(self.config.max_backoff_s, self.config.backoff_s * 2 ** (attempt - 1)) * (0.5 + self._rnd.random() / 2)
            if retry_after is not None:
                wait = max(wait, retry_after)
            if wait >= deadline - self._clock():
                raise failure
            self._sleep(wait)

    def _post(self, body: bytes, remaining: float) -> tuple[int, bytes, float | None]:
        headers = {"content-type": "application/json", **self.codec.auth_headers(self._key.get_secret_value())}
        timeout = httpx.Timeout(remaining, connect=min(self.config.connect_timeout_s, remaining))
        with self._client.stream("POST", self.codec.endpoint, content=body, headers=headers, timeout=timeout) as resp:
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > self.config.max_response_bytes:
                    raise _TooLarge()
                chunks.append(chunk)
            return resp.status_code, b"".join(chunks), _retry_after(resp.headers.get("retry-after"))

    def _permanent(self, status: int, raw: bytes) -> bool:
        """Ask the codec whether a 429/5xx is permanent (its vendor contract); never raises, never quotes the body."""
        check = getattr(self.codec, "is_permanent", None)
        if check is None:
            return False
        try:
            doc = json.loads(raw) if raw else None
        except ValueError:
            doc = None
        try:
            return bool(check(status, doc))
        except Exception:
            return False

    def _decode(self, raw: bytes, request: StepRequest) -> StepResponse:
        try:
            doc = json.loads(raw)
        except ValueError:
            raise ProviderError(f"{self.name}: response is not valid JSON") from None
        try:
            out = self.codec.decode(doc)
        except WireError as e:
            raise ProviderError(f"{self.name}: response does not match the contract ({e})") from None
        if out.text is None and not out.tool_calls:
            raise ProviderError(f"{self.name}: empty response")
        if out.text is not None and len(out.text) > request.max_output_chars:
            raise ProviderError(f"{self.name}: response text exceeds {request.max_output_chars} characters")
        if out.tool_calls and not request.allow_tools:
            raise ProviderError(f"{self.name}: tool calls returned where none are allowed")
        return out


class _TooLarge(Exception):
    """The body exceeded the byte cap: permanent for this request, never retried."""


def _retry_after(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        s = float(v)
    except ValueError:
        return None
    return s if 0 <= s <= 3600 else None
