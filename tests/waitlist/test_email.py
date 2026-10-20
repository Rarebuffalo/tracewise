"""Email providers and templates, without any network (Resend is exercised through httpx.MockTransport)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import httpx
import pytest

from tracewise.waitlist import service, templates
from tracewise.waitlist.email import DisabledSender, FileSender, Message, ResendSender, make_sender, sanitize_error

MSG = Message("ada@example.com", "Subject", "text body", "<p>html</p>", "verify-abc-1", {"List-Unsubscribe": "<https://x/u>"})


def resend(handler: httpx.MockTransport) -> ResendSender:
    return ResendSender(
        "re_test_key", "Tracewise <hello@updates.example.com>", "reply@example.com", client=httpx.Client(transport=handler)
    )


def test_resend_request_shape_and_success() -> None:
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"id": "4ef9a417-02e9-4d39-ad75-9611e0fcc33c"})

    r = resend(httpx.MockTransport(handle)).send(MSG)
    assert r.ok and r.provider == "resend" and r.message_id == "4ef9a417-02e9-4d39-ad75-9611e0fcc33c"
    req = seen[0]
    assert str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == "Bearer re_test_key"
    assert req.headers["idempotency-key"] == "verify-abc-1"
    body = json.loads(req.content)
    assert body["to"] == ["ada@example.com"] and body["reply_to"] == "reply@example.com"
    assert body["headers"] == {"List-Unsubscribe": "<https://x/u>"}


@pytest.mark.parametrize(("code", "retryable"), [(429, True), (500, True), (503, True), (409, True), (403, False), (422, False)])
def test_resend_errors_are_classified_and_sanitised(code: int, retryable: bool) -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"name": "validation_error", "message": "cannot send to ada@example.com"})

    r = resend(httpx.MockTransport(handle)).send(MSG)
    assert not r.ok and r.retryable is retryable
    assert r.error is not None and "ada@example.com" not in r.error and str(code) in r.error
    assert "re_test_key" not in r.error


def test_resend_network_failure_is_retryable() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    r = resend(httpx.MockTransport(handle)).send(MSG)
    assert not r.ok and r.retryable and r.error == "network error: ConnectTimeout"


def test_disabled_sender_never_claims_success() -> None:
    r = DisabledSender().send(MSG)
    assert not r.ok and r.provider is None and r.message_id is None


def test_file_sender_writes_private_files(tmp_path: Path) -> None:
    r = FileSender(tmp_path / "mail").send(MSG)
    assert r.ok and r.provider == "file"
    files = list((tmp_path / "mail").iterdir())
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "mail").stat().st_mode) == 0o700
    assert json.loads(files[0].read_text())["to"] == "ada@example.com"


def test_make_sender_falls_back_to_disabled(tmp_path: Path) -> None:
    assert isinstance(make_sender("resend", file_dir=tmp_path, api_key=None, sender=None, reply_to=None), DisabledSender)
    assert isinstance(make_sender("disabled", file_dir=tmp_path, api_key="k", sender="s", reply_to=None), DisabledSender)
    assert isinstance(make_sender("file", file_dir=tmp_path, api_key=None, sender=None, reply_to=None), FileSender)


def test_sanitize_error_removes_addresses_and_truncates() -> None:
    out = sanitize_error("rejected <owner@corp.example> and bob@x.io " + "x" * 500)
    assert "@" not in out.replace("[address]", "") and len(out) <= 300


def test_verification_template_escapes_and_includes_links() -> None:
    subject, text, html = templates.verification(
        'https://site.example/confirm/#token=a"b<c', "https://site.example/unsubscribe/#token=u.v", "1 Main St <Suite>", 48
    )
    assert "Confirm" in subject
    assert 'a"b<c' not in html and "a&quot;b&lt;c" in html
    assert "1 Main St &lt;Suite&gt;" in html and "1 Main St <Suite>" in text
    assert "48 hours" in text and "unsubscribe/#token=u.v" in text


def test_owner_template_escapes_user_supplied_values() -> None:
    _, text, html = templates.owner_notification(
        {"email": "<script>@x.io", "github_login": None, "updates_consent": False, "ci_failure_freq": None}
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "GitHub username: —" in text and "Product-updates consent: no" in text and "CI fails: not answered yet" in text


def test_consent_version_is_shown_on_privacy_page() -> None:
    page = (Path(__file__).resolve().parents[2] / "web" / "src" / "privacy.html").read_text()
    assert "{{CONSENT_VERSION}}" in page and service.CONSENT_VERSION


@pytest.mark.parametrize(
    ("code", "body", "ok"),
    [(200, {"success": True}, True), (200, {"success": False}, False), (500, {"success": True}, False), (200, None, False)],
)
def test_turnstile_verification(code: int, body: object, ok: bool) -> None:
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(code, json=body) if body is not None else httpx.Response(code, text="not json")

    assert (
        service.verify_turnstile("ts-secret", "tok", "203.0.113.9", client=httpx.Client(transport=httpx.MockTransport(handle)))
        is ok
    )
    assert str(seen[0].url) == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    assert b"remoteip=203.0.113.9" in seen[0].content


def test_turnstile_network_failure_fails_closed() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert service.verify_turnstile("s", "t", None, client=httpx.Client(transport=httpx.MockTransport(handle))) is False
