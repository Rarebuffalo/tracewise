"""The website and the waitlist API as one ASGI app (used by web/vercel_app.py, web/dev.py and the tests)."""

from __future__ import annotations

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
    site.frontend("/", directory=str(dist), fallback="404.html", check_dir=True)
    return site
