"""AT-SEC-05 (logging half): tokens never logged. Installation-scope half is T-301."""

import io
import json
import logging

from pydantic import SecretStr

from tracewise import logging as twlog
from tracewise.config import Settings


def _capture() -> tuple[logging.Logger, io.StringIO]:
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(twlog.JsonFormatter())
    h.addFilter(twlog.secret_filter)
    lg = logging.getLogger("tw.test")
    lg.handlers[:] = [h]
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    return lg, buf


def test_registered_and_shaped_tokens_are_scrubbed() -> None:
    lg, buf = _capture()
    inst = "ghs_" + "Q" * 36
    opaque = "opaque-installation-token-value"
    twlog.secret_filter.register(opaque)
    token = twlog.correlation_id.set("corr-1")
    try:
        lg.info("minted %s and %s", inst, opaque, extra={"tw": {"auth": f"token {opaque}"}})
        try:
            raise RuntimeError(f"bad creds {opaque}")
        except RuntimeError:
            lg.exception("failed")
        lg.info("db at postgresql://app:hunter2pass@localhost/db")
    finally:
        twlog.correlation_id.reset(token)
        twlog.secret_filter.unregister(opaque)
    out = buf.getvalue()
    assert inst not in out and opaque not in out and "hunter2pass" not in out
    first = json.loads(out.splitlines()[0])
    assert first["correlation_id"] == "corr-1"
    assert "[REDACTED]" in first["msg"] and "[REDACTED]" in first["auth"]


def test_settings_hide_secrets_and_default_offline() -> None:
    s = Settings(openai_api_key=SecretStr("sk-test-not-real-0000000000000000"))
    assert s.llm_provider == "fake"
    assert "sk-test" not in repr(s) and "sk-test" not in str(s.model_dump())
    assert "sk-test-not-real-0000000000000000" in s.secret_values()


def test_openai_requires_key() -> None:
    import pytest

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(llm_provider="openai")


def test_url_query_strings_are_redacted_and_request_url_loggers_quieted() -> None:
    """T-706 audit: httpx logs full request URLs at INFO, including signed log-redirect URLs."""
    from tracewise.logging import QUIET_LOGGERS, SecretFilter, configure

    f = SecretFilter()
    signed = "GET https://productionresultssa1.blob.core.windows.net/logs/1.txt?sv=2020&sig=AbC%2Fdef&se=2026 done"
    s3 = 'see "https://bucket.s3.amazonaws.com/k.png?X-Amz-Credential=AKIAEXAMPLE&X-Amz-Signature=ff00"'
    assert f.scrub(signed) == "GET https://productionresultssa1.blob.core.windows.net/logs/1.txt?[REDACTED] done"
    assert "AKIAEXAMPLE" not in f.scrub(s3) and "ff00" not in f.scrub(s3)
    assert f.scrub("https://api.github.com/repos/a/b/check-runs") == "https://api.github.com/repos/a/b/check-runs"
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure()
        assert all(logging.getLogger(n).getEffectiveLevel() >= logging.WARNING for n in QUIET_LOGGERS)
    finally:
        root.handlers[:], _ = saved[0], root.setLevel(saved[1])


def test_nested_fields_are_scrubbed_at_any_depth() -> None:
    """Phase 11 audit (SA-6): observe.sanitize allows flat dicts and lists; the filter must scrub inside them too."""
    from tracewise.logging import SecretFilter

    f = SecretFilter()
    f.register("nested-secret-value")
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None)
    rec.tw = {  # type: ignore[attr-defined]
        "flags": ["ok", "ghs_" + "b" * 36],
        "stage": {"x": "https://h.example/p?sig=abc", "nested-secret-value": 1},
        "deep": [[[[[[[["too deep"]]]]]]]],
        "n": 3,
    }
    f.filter(rec)
    out = repr(rec.tw)  # type: ignore[attr-defined]
    assert "ghs_bbbb" not in out and "sig=abc" not in out and "nested-secret-value" not in out
    assert rec.tw["n"] == 3 and rec.tw["stage"]["x"] == "https://h.example/p?[REDACTED]"  # type: ignore[attr-defined]
    assert "[TRUNCATED]" in out


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "raw",
    [
        "loc=https%3A%2F%2Fblob.core.windows.net%2Fl%3Fsig%3DSECRETSIG1",
        "Authorization: Bearer SECRETOPAQUE3abcdef",
        "authorization: token SECRETOPAQUE4abcdef",
        "headers={'Authorization': 'Bearer SECRETOPAQUE5abcdef'}",
        "Cookie: session=SECRETCOOKIE5; other=1",
        "Set-Cookie: tw=SECRETCOOKIE8",
        "X-Amz-Signature=SECRETSIG9abcdef&X-Amz-Credential=SECRETCRED",
        "blob.core.windows.net/l.txt?sv=1&sig=SECRETSIG10",
        "redirect to //h/p?token=SECRETTOK11",
        "bearer SECRETOPAQUE12abcdef in text",
    ],
    ids=[
        "encoded-url",
        "auth-bearer",
        "auth-token",
        "repr-dict",
        "cookie",
        "set-cookie",
        "amz-params",
        "schemeless-sas",
        "token-param",
        "bare-bearer",
    ],  # ids never echo the synthetic secrets
)
def test_phase14_redaction_bypass_shapes(raw: str) -> None:
    """Phase 14 audit (SA-8): encoded URLs, auth/cookie headers and bare signature parameters."""
    from tracewise.logging import SecretFilter

    assert "SECRET" not in SecretFilter().scrub(raw), raw


def test_redaction_keeps_benign_metric_text() -> None:
    from tracewise.logging import SecretFilter

    text = "tokens_in=120 tokens_out=30 outcome=diagnosed https://api.github.com/repos/a/b/check-runs"
    assert SecretFilter().scrub(text) == text
