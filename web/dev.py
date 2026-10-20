"""Local end-to-end mode: a disposable PostgreSQL, the waitlist migrations, file-based email, and the real app.

    node web/build.mjs && uv run python web/dev.py [--port 8000]

Nothing leaves this machine: emails are written as JSON files to .waitlist-mail/ (open one to get the confirmation
link), the database lives in a private temp directory and is deleted on exit, and only 127.0.0.1 is bound.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import psycopg  # noqa: E402
import uvicorn  # noqa: E402
from tests.pg import OWNER, ephemeral  # noqa: E402

from tracewise.waitlist.migrate import upgrade  # noqa: E402

ROLE = "tracewise_waitlist"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--owner-email", default="owner@localhost.test", help="where owner notifications are 'sent' (a file)")
    a = ap.parse_args()
    if not (ROOT / "web" / "dist" / "index.html").exists():
        print("web/dist is missing: run `node web/build.mjs` first", file=sys.stderr)
        return 2
    cluster = ephemeral()
    try:
        with psycopg.connect(cluster.url(OWNER), autocommit=True) as c:
            c.execute(f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        upgrade(cluster.url(OWNER))
        mail = Path(os.environ.get("WAITLIST_EMAIL_FILE_DIR") or ROOT / ".waitlist-mail").resolve()
        os.environ.update(
            {
                "WAITLIST_ENV": "local",
                "WAITLIST_DATABASE_URL": cluster.url(ROLE),
                "WAITLIST_PUBLIC_SITE_URL": f"http://127.0.0.1:{a.port}",
                "WAITLIST_EMAIL_MODE": "file",
                "WAITLIST_EMAIL_FILE_DIR": str(mail),
                "WAITLIST_OWNER_NOTIFY_EMAIL": a.owner_email,
            }
        )
        print(f"waitlist dev: http://127.0.0.1:{a.port}  (emails → {mail}/)", flush=True)
        from web.vercel_app import app

        uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")
    finally:
        cluster.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
