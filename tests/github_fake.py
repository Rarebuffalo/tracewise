"""In-process fake of the GitHub REST API on `httpx.MockTransport` (no network).

Routes are (method, regex) → handler returning `httpx.Response`. Every request is recorded so
tests can assert on paths, bodies and headers (e.g. that no token reaches the log host).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tracewise.github.auth import AppCredentials, TokenProvider
from tracewise.github.client import GitHubHTTP, Limits

RECORDED = Path(__file__).parent / "fixtures" / "github" / "recorded"
Handler = Callable[[httpx.Request], httpx.Response]

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # throwaway, generated per test session


def test_key() -> rsa.RSAPrivateKey:
    return _KEY


def test_key_pem() -> bytes:
    return _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def recorded(name: str) -> Any:
    return json.loads((RECORDED / name).read_text())


def jresp(status: int, body: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body if body is not None else {}, headers=headers or {})


class FakeGitHub:
    def __init__(self) -> None:
        self.routes: list[tuple[str, re.Pattern[str], Handler]] = []
        self.requests: list[httpx.Request] = []
        self.minted = 0
        self.token_ttl_s = 3600.0
        self.now = 1_800_000_000.0
        self.next_tokens: list[str] = []  # optional: tokens to hand out (e.g. a local git server's token)

    def route(self, method: str, pattern: str, handler: Handler | httpx.Response | list[httpx.Response]) -> None:
        if isinstance(handler, httpx.Response):
            resp = handler
            handler = lambda _r: resp  # noqa: E731
        elif isinstance(handler, list):
            seq = list(handler)
            handler = lambda _r: seq.pop(0) if len(seq) > 1 else seq[0]  # noqa: E731
        self.routes.append((method, re.compile(pattern), handler))

    def add_token_route(
        self, *, permissions_override: dict[str, str] | None = None, selection: str = "selected", status: int = 201
    ) -> None:
        def mint(req: httpx.Request) -> httpx.Response:
            if status != 201:
                return jresp(status, {"message": "nope"})
            body = json.loads(req.content)
            self.minted += 1
            exp = datetime.fromtimestamp(self.now + self.token_ttl_s, UTC).isoformat().replace("+00:00", "Z")
            return jresp(
                201,
                {
                    "token": self.next_tokens.pop(0) if self.next_tokens else f"ghs_fake{self.minted:04d}" + "x" * 30,
                    "expires_at": exp,
                    "permissions": permissions_override if permissions_override is not None else body["permissions"],
                    "repository_selection": selection,
                    "repositories": [{"id": i} for i in body["repository_ids"]],
                },
            )

        self.route("POST", r"^/app/installations/\d+/access_tokens$", mint)

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        target = req.url.path if req.url.host == "api.github.com" else f"//{req.url.host}{req.url.path}"
        for method, pat, h in self.routes:
            if method == req.method and pat.search(target):
                return h(req)
        return jresp(404, {"message": "Not Found (fake)"})

    def http(self, sleeps: list[float] | None = None, **limits: Any) -> GitHubHTTP:
        client = httpx.Client(transport=httpx.MockTransport(self.handle))
        rec = sleeps if sleeps is not None else []
        return GitHubHTTP(client, limits=Limits(**limits), sleep=rec.append, clock=lambda: self.now)

    def provider(self, http: GitHubHTTP, app_id: int = 123) -> TokenProvider:
        return TokenProvider(AppCredentials(app_id, _KEY), http, clock=lambda: self.now)

    def calls(self, method: str, pattern: str) -> list[httpx.Request]:
        p = re.compile(pattern)
        return [r for r in self.requests if r.method == method and p.search(r.url.path)]
