"""T-301: App JWT and scoped, memory-only installation tokens (FS-INS-2, FS-SEC-5; AT-SEC-05; AT-LOG-01 scope part).
All keys are generated in-process; no network, no real credentials."""

from __future__ import annotations

import json
import logging

import jwt
import pytest

from tests.github_fake import FakeGitHub, test_key, test_key_pem
from tracewise.github.auth import JWT_BACKDATE_S, JWT_LIFETIME_S, AppCredentials
from tracewise.github.endpoints import ANALYSIS_SCOPE, APP_PERMISSIONS, PUBLISH_SCOPE
from tracewise.github.errors import InstallationUnavailable, PermissionDenied, TokenScopeError
from tracewise.logging import JsonFormatter, secret_filter


def test_app_jwt_claims_and_signature() -> None:
    creds = AppCredentials(123, test_key())
    tok = creds.app_jwt(now=1_800_000_000)
    claims = jwt.decode(tok, test_key().public_key(), algorithms=["RS256"], options={"verify_exp": False, "verify_iat": False})
    assert claims == {"iss": "123", "iat": 1_800_000_000 - JWT_BACKDATE_S, "exp": 1_800_000_000 + JWT_LIFETIME_S}
    assert jwt.get_unverified_header(tok)["alg"] == "RS256"
    assert claims["exp"] - claims["iat"] <= 600  # GitHub maximum


def test_key_loaded_from_file_and_hidden(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "app.pem"
    p.write_bytes(test_key_pem())
    creds = AppCredentials.from_pem_file(7, p)
    assert "PRIVATE" not in repr(creds) and "<hidden>" in repr(creds)
    assert creds.app_jwt()


def test_token_request_is_scoped_to_repo_and_permissions() -> None:
    gh = FakeGitHub()
    gh.add_token_route()
    tp = gh.provider(gh.http())
    t = tp.token(42, 1001, "analysis")
    (req,) = gh.calls("POST", r"/app/installations/42/access_tokens")
    body = json.loads(req.content)
    assert body == {"repository_ids": [1001], "permissions": ANALYSIS_SCOPE}
    assert req.headers["authorization"].startswith("Bearer ey")  # App JWT, not a token or PAT
    assert t.permissions == ANALYSIS_SCOPE and t.repo_id == 1001
    tp.token(42, 1001, "publish")
    assert json.loads(gh.requests[-1].content)["permissions"] == PUBLISH_SCOPE


def test_scopes_within_app_permissions() -> None:
    for scope in (ANALYSIS_SCOPE, PUBLISH_SCOPE):
        for perm, level in scope.items():
            assert APP_PERMISSIONS[perm] in (level, "write")
    assert "pull_requests" not in ANALYSIS_SCOPE and "checks" not in ANALYSIS_SCOPE  # analysis cannot write
    assert set(APP_PERMISSIONS) == {"actions", "contents", "metadata", "pull_requests", "checks"}


def test_cache_is_per_installation_repo_and_scope() -> None:
    """AT-SEC-05: tokens are never reused across installations (or repos, or scopes)."""
    gh = FakeGitHub()
    gh.add_token_route()
    tp = gh.provider(gh.http())
    a = tp.token(1, 10, "analysis")
    assert tp.token(1, 10, "analysis") is a and gh.minted == 1
    others = {tp.token(2, 10, "analysis").value, tp.token(1, 11, "analysis").value, tp.token(1, 10, "publish").value}
    assert a.value not in others and len(others) == 3 and gh.minted == 4


def test_refresh_before_expiry_and_invalidate() -> None:
    gh = FakeGitHub()
    gh.add_token_route()
    tp = gh.provider(gh.http())
    a = tp.token(1, 10, "analysis")
    gh.now += 3600 - 299  # inside the 5-minute margin
    b = tp.token(1, 10, "analysis")
    assert b.value != a.value and gh.minted == 2
    tp.invalidate(1, 10, "analysis")
    assert tp.token(1, 10, "analysis").value != b.value
    tp.token(1, 11, "publish")
    tp.drop_installation(1)
    n = gh.minted
    tp.token(1, 11, "publish")
    assert gh.minted == n + 1


@pytest.mark.parametrize(
    ("override", "selection", "match"),
    [
        ({"actions": "read", "contents": "write", "metadata": "read"}, "selected", "unrequested"),
        ({"actions": "read", "contents": "read", "metadata": "read", "issues": "write"}, "selected", "unrequested"),
        (None, "all", "selected repositories"),
    ],
)
def test_overbroad_grant_fails_closed(override, selection, match) -> None:  # type: ignore[no-untyped-def]
    gh = FakeGitHub()
    gh.add_token_route(permissions_override=override, selection=selection)
    with pytest.raises(TokenScopeError, match=match):
        gh.provider(gh.http()).token(1, 10, "analysis")


@pytest.mark.parametrize(
    ("status", "exc"),
    [(401, InstallationUnavailable), (403, InstallationUnavailable), (404, InstallationUnavailable), (422, PermissionDenied)],
)
def test_mint_failures(status, exc) -> None:  # type: ignore[no-untyped-def]
    gh = FakeGitHub()
    gh.add_token_route(status=status)
    with pytest.raises(exc):
        gh.provider(gh.http()).token(1, 10, "publish")


def test_tokens_and_jwts_never_logged(caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    gh = FakeGitHub()
    gh.add_token_route()
    tp = gh.provider(gh.http())
    tok = tp.token(1, 10, "analysis").value
    jwt_sent = gh.requests[0].headers["authorization"].removeprefix("Bearer ")
    raw = caplog.text + " ".join(str(getattr(r, "tw", "")) for r in caplog.records)
    assert tok not in raw and jwt_sent not in raw  # never emitted at all
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, f"oops {tok} {jwt_sent}", None, None)
    secret_filter.filter(rec)  # and the scrubber would catch an accidental emission
    assert tok not in JsonFormatter().format(rec) and jwt_sent not in JsonFormatter().format(rec)
    assert tok not in repr(tp.token(1, 10, "analysis"))
