"""The website and the waitlist API as one ASGI app (used by web/vercel_app.py, web/dev.py and the tests)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:  # the package uses a src/ layout; make it importable without installing
    sys.path.insert(0, str(ROOT / "src"))

from tracewise.waitlist.app import create_app  # noqa: E402

DIST = ROOT / "web" / "dist"


def create_site(dist: Path = DIST, **kwargs: Any) -> FastAPI:
    """The waitlist API plus the built site. API routes always win; unknown paths get the site's 404 page."""
    site = create_app(**kwargs)
    # Locally and in tests a missing build is an error. On Vercel the build step already fails without web/dist,
    # and the static files may be served from the CDN rather than bundled with the function, so the function must
    # not refuse to start just because the directory is absent from its bundle (unverified platform behaviour).
    site.frontend("/", directory=str(dist), fallback="404.html", check_dir=os.environ.get("VERCEL") != "1")
    return site
