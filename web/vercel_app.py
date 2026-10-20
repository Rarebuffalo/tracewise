"""Vercel entrypoint (pyproject.toml → [tool.vercel] entrypoint = "web.vercel_app:app").

One deployment serves both halves on the same origin:
- /api/waitlist/*  → the FastAPI waitlist service (tracewise.waitlist.app), as a Vercel Function;
- everything else  → the static website built by `node web/build.mjs` into web/dist, promoted to Vercel's CDN.

Fails at import if web/dist is missing, so a deployment whose build step did not run cannot go live half-built.
Locally: web/dev.py runs the same app with a disposable database and file-based email.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.site import create_site

app = create_site()
