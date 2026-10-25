"""Guards for the owner-run tools that may reach a real model endpoint (T-605 preparation). NOT provider selection.

Product selection (`investigate/providers.py`) still refuses `LLM_PROVIDER=openai`. The only callers of this module
are owner-run tools: the API smoke harness under `scripts/` and the benchmark's model mode
(`python -m tracewise.bench run --kind model`). Each of them refuses to run under a test runner or CI, needs a written
authorisation reference, and reads the key only from an owner-only file outside the repository.

* `read_key_file`: the only key source. Never the environment, never printed; the value is a `SecretStr`.
* `EndpointBudgetTransport`: allows POST to one endpoint only, refuses a request body over a byte cap, and stops
  after a hard number of requests. A refused request never reaches the inner transport.
* `SecretCanary`: checks output text for the key without handing the key to the caller.

Every refusal message is fixed text written here: never a key, a path's contents, or a provider response.
"""

from __future__ import annotations

import re
import stat
from collections.abc import Mapping
from pathlib import Path

import httpx
from pydantic import SecretStr

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_KEY_FILE_BYTES = 512
_AUTH_REF = re.compile(r"^[A-Za-z0-9._:/ #-]{8,120}$")


class AccessRefused(Exception):
    """A configuration or safety refusal; nothing was sent. The message is fixed text."""


class RequestBudgetExhausted(AccessRefused):
    """The hard request cap was reached; the refused request was not sent."""


class RequestTooLarge(AccessRefused):
    """The serialised request body exceeded the byte cap; the request was not sent."""


def refuse_under_automation(env: Mapping[str, str]) -> None:
    """Real requests are never made by a test runner or CI."""
    if env.get("PYTEST_CURRENT_TEST") or env.get("CI"):
        raise AccessRefused("real model requests are never made by test runners or CI")


def check_authorization_ref(ref: str | None) -> str:
    if not ref:
        raise AccessRefused("an authorization reference is required")
    if not _AUTH_REF.match(ref):
        raise AccessRefused("authorization reference is malformed")
    return ref


def read_key_file(path: str | Path, *, repo_root: Path = REPO_ROOT) -> SecretStr:
    """The only key source: an owner-only regular file outside the repository. Never the environment."""
    p = Path(path)
    if p.is_symlink():
        raise AccessRefused("key file must not be a symlink")
    try:
        st = p.stat()
    except OSError:
        raise AccessRefused("key file is not readable") from None
    if not stat.S_ISREG(st.st_mode):
        raise AccessRefused("key file must be a regular file")
    if st.st_mode & 0o077:
        raise AccessRefused("key file must be readable by its owner only (chmod 600)")
    if p.resolve().is_relative_to(repo_root.resolve()):
        raise AccessRefused("key file must be outside the repository")
    if st.st_size > MAX_KEY_FILE_BYTES:
        raise AccessRefused("key file is too large")
    key = p.read_text(encoding="utf-8").strip()
    if len(key) < 8 or any(c.isspace() for c in key):
        raise AccessRefused("key file content is malformed")
    return SecretStr(key)


class EndpointBudgetTransport(httpx.BaseTransport):
    """POST to exactly one endpoint, a body of at most `max_request_bytes`, at most `max_requests` times in total;
    everything else is refused unsent. The size check reads the actual serialised body handed to the transport."""

    def __init__(self, inner: httpx.BaseTransport, endpoint: str, max_requests: int, *, max_request_bytes: int) -> None:
        if max_requests < 1 or max_request_bytes < 1:
            raise ValueError("max_requests and max_request_bytes must be at least 1")
        self.inner, self.endpoint = inner, endpoint
        self.max_requests, self.max_request_bytes = max_requests, max_request_bytes
        self.sent = 0
        self.refused = 0  # every refused request (wrong host or method, over the cap, or too large)
        self.budget_refused = 0  # refused because the cap was reached: an interrupted evaluation
        self.oversize_refused = 0  # refused because the body exceeded max_request_bytes

    @property
    def exhausted(self) -> bool:
        return self.sent >= self.max_requests

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or str(request.url) != self.endpoint:
            self.refused += 1
            raise AccessRefused("only POST to the provider endpoint is allowed")
        if self.exhausted:
            self.refused += 1
            self.budget_refused += 1
            raise RequestBudgetExhausted("request budget exhausted")
        if len(request.read()) > self.max_request_bytes:
            self.refused += 1
            self.oversize_refused += 1
            raise RequestTooLarge("request body exceeds the size cap")  # fixed text: never the body or a header
        self.sent += 1
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()


class SecretCanary:
    """Answers one question about a secret, whether it appears in some text, without exposing the secret: there is
    no accessor, and neither `repr` nor `str` shows it. Used to refuse writing any output that would contain the key."""

    __slots__ = ("_secret",)

    def __init__(self, secret: SecretStr) -> None:
        if not secret.get_secret_value():
            raise ValueError("an empty secret cannot be checked for")
        self._secret = secret

    def found_in(self, *texts: str) -> bool:
        value = self._secret.get_secret_value()
        return any(value in t for t in texts)

    def __repr__(self) -> str:
        return "SecretCanary(<hidden>)"

    __str__ = __repr__
