"""The deployed shape: the built website and the waitlist API served by one app (web/vercel_app.py)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.waitlist.conftest import ROOT, RecordingSender
from tracewise.waitlist.db import Conn
from tracewise.waitlist.settings import WaitlistSettings

if shutil.which("node") is None:  # pragma: no cover
    pytest.skip("node is required to build the website", allow_module_level=True)


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PUBLIC_", "VERCEL"))}
    env.update(
        {"WEB_OUT_DIR": str(out), "PUBLIC_OPERATOR_NAME": "Example Operator", "PUBLIC_CONTACT_EMAIL": "privacy@example.com"}
    )
    subprocess.run(["node", str(ROOT / "web" / "build.mjs")], check=True, env=env, capture_output=True)  # noqa: S603, S607
    return out


@pytest.fixture
def site(dist: Path, settings: WaitlistSettings, pool: ConnectionPool[Conn], sender: RecordingSender) -> Iterator[TestClient]:
    from web.site import create_site

    with TestClient(
        create_site(dist, settings=settings, pool=pool, sender=sender), base_url="https://tracewise-test.example"
    ) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/confirm/", "/unsubscribe/", "/privacy/"])
def test_pages_are_served(site: TestClient, path: str) -> None:
    r = site.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "Content-Security-Policy" in html and "{{" not in html
    assert "Design preview" not in html and "preview-banner" not in html


def test_unknown_path_gets_404_page(site: TestClient) -> None:
    r = site.get("/no/such/page")
    assert r.status_code == 404 and "No trail leads here" in r.text


def test_api_routes_win_over_static_files(site: TestClient) -> None:
    assert site.get("/api/waitlist/health").json()["ok"] is True
    r = site.get("/api/waitlist/nope")
    assert r.status_code == 404 and r.json() == {"error": "not_found"}


def test_assets_referenced_by_pages_exist(site: TestClient) -> None:
    html = site.get("/").text
    refs = set(re.findall(r'(?:src|href)="(/[^"#]+)"', html))
    assert any(r.startswith("/js/home.mjs?v=") for r in refs) and any(r.startswith("/css/site.css?v=") for r in refs)
    for ref in refs:
        if ref.endswith("/") or ref.startswith("/api/"):
            continue
        assert site.get(ref).status_code == 200, ref


def test_privacy_page_uses_configured_operator(site: TestClient) -> None:
    html = site.get("/privacy/").text
    assert "Example Operator" in html and "mailto:privacy@example.com" in html and "not set" not in html


def test_home_page_wires_real_forms(site: TestClient) -> None:
    html = site.get("/").text
    assert html.count("data-signup") == 2
    assert 'name="website"' in html  # honeypot
    assert 'type="checkbox" name="updates"' in html and "checked" not in html.split('name="updates"')[1][:20]
    assert "noindex" in html  # not a Vercel production build: not indexed
