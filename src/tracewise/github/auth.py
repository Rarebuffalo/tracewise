"""GitHub App authentication (T-301; FS-INS-2, FS-SEC-5, ADR-16).

* App JWT: RS256, `iat` backdated 60 s for clock skew, lifetime 9 min (GitHub max is 10).
* Installation tokens are minted **per repository and per purpose** (`repository_ids=[repo]`,
  `permissions=<scope>`), verified against what was requested, cached **in memory only**, keyed
  by (installation, repo, scope) so a token is never reused for another installation or repo,
  registered with the log scrubber while alive and dropped 5 minutes before expiry.
* The private key is read from a file path at startup and held as a parsed key object; the
  PEM bytes, JWTs and tokens are never logged, persisted or put in exception messages.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from tracewise.github.endpoints import ANALYSIS_SCOPE, APP_PERMISSIONS, PUBLISH_SCOPE, Access
from tracewise.github.errors import InstallationUnavailable, TokenScopeError
from tracewise.logging import secret_filter

if TYPE_CHECKING:
    from tracewise.github.client import GitHubHTTP

JWT_LIFETIME_S = 9 * 60
JWT_BACKDATE_S = 60
REFRESH_MARGIN_S = 5 * 60
SCOPES: dict[str, dict[str, Access]] = {"analysis": ANALYSIS_SCOPE, "publish": PUBLISH_SCOPE}


class AppCredentials:
    """App ID + RSA private key. `repr` never shows key material."""

    def __init__(self, app_id: int, private_key: RSAPrivateKey) -> None:
        self.app_id = app_id
        self._key = private_key

    @classmethod
    def from_pem_file(cls, app_id: int, path: Path) -> AppCredentials:
        key = load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("GitHub App private key must be RSA")
        return cls(app_id, key)

    def __repr__(self) -> str:
        return f"AppCredentials(app_id={self.app_id}, key=<hidden>)"

    def app_jwt(self, now: float | None = None) -> str:
        t = int(now if now is not None else time.time())
        token = jwt.encode(
            {"iat": t - JWT_BACKDATE_S, "exp": t + JWT_LIFETIME_S, "iss": str(self.app_id)}, self._key, algorithm="RS256"
        )
        secret_filter.register(token)
        return token


@dataclass(frozen=True)
class InstallationToken:
    installation_id: int
    repo_id: int
    scope: str
    value: str = field(repr=False)
    expires_at: float
    permissions: dict[str, str]


class TokenProvider:
    """Mints and caches scoped installation tokens. Thread-safe; memory-only."""

    def __init__(self, creds: AppCredentials, http: GitHubHTTP, clock: Callable[[], float] = time.time) -> None:
        self._creds, self._http, self._clock = creds, http, clock
        self._cache: dict[tuple[int, int, str], InstallationToken] = {}
        self._lock = threading.Lock()

    def token(self, installation_id: int, repo_id: int, scope: str) -> InstallationToken:
        if scope not in SCOPES:
            raise ValueError(f"unknown token scope {scope!r}")
        key = (installation_id, repo_id, scope)
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached.expires_at - self._clock() > REFRESH_MARGIN_S:
                return cached
            if cached:
                self._evict(key)
            tok = self._mint(installation_id, repo_id, scope)
            self._cache[key] = tok
            return tok

    def invalidate(self, installation_id: int, repo_id: int, scope: str) -> None:
        with self._lock:
            self._evict((installation_id, repo_id, scope))

    def drop_installation(self, installation_id: int) -> None:
        """On uninstall/suspend (T-701): forget every token of that installation."""
        with self._lock:
            for key in [k for k in self._cache if k[0] == installation_id]:
                self._evict(key)

    def _evict(self, key: tuple[int, int, str]) -> None:
        old = self._cache.pop(key, None)
        if old:
            secret_filter.unregister(old.value)

    def _mint(self, installation_id: int, repo_id: int, scope: str) -> InstallationToken:
        requested = SCOPES[scope]
        assert all(APP_PERMISSIONS.get(p) in (a, "write") for p, a in requested.items())
        body = {"repository_ids": [repo_id], "permissions": dict(requested)}
        try:
            doc = self._http.app_call(
                "create_installation_token", self._creds.app_jwt(self._clock()), {"installation_id": installation_id}, body
            )
        except InstallationUnavailable:
            raise
        token = doc.get("token")
        if not isinstance(token, str) or not token:
            raise TokenScopeError("token response missing token")
        secret_filter.register(token)
        granted = doc.get("permissions") or {}
        _verify_scope(requested, granted, doc, repo_id)
        return InstallationToken(installation_id, repo_id, scope, token, _parse_expiry(doc.get("expires_at")), dict(granted))


def _verify_scope(requested: dict[str, Access], granted: Any, doc: dict[str, Any], repo_id: int) -> None:
    """Fail closed if GitHub granted anything beyond the request, or a different repository set."""
    if not isinstance(granted, dict):
        raise TokenScopeError("token response missing permissions")
    for perm, level in granted.items():
        want = requested.get(perm)
        if want is None or (want == "read" and level != "read"):
            raise TokenScopeError(f"token granted unrequested access: {perm}={level}")
    if doc.get("repository_selection") != "selected":
        raise TokenScopeError("token is not limited to selected repositories")
    repos = doc.get("repositories")
    if repos is not None and [r.get("id") for r in repos] != [repo_id]:
        raise TokenScopeError("token repositories differ from the requested repository")


def _parse_expiry(raw: Any) -> float:
    if not isinstance(raw, str):
        raise TokenScopeError("token response missing expires_at")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
