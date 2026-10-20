"""Operator CLI for the waitlist (internal metrics and data requests). Uses WAITLIST_DATABASE_URL.

python -m tracewise.waitlist.admin stats                     exact internal counts (never published)
python -m tracewise.waitlist.admin export [--all] [--json]   confirmed signups (or all with --all) to stdout
python -m tracewise.waitlist.admin delete EMAIL              hard-delete one person's signup (data request)
python -m tracewise.waitlist.admin outbox [--status S]       email deliveries (default: not yet sent)
python -m tracewise.waitlist.admin retry [ID ...|--failed]   re-queue failed deliveries, then process due ones
python -m tracewise.waitlist.admin process                   deliver due emails now
python -m tracewise.waitlist.admin purge                     apply retention (unconfirmed after 7 days, …)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from typing import Any

from tracewise.waitlist import service
from tracewise.waitlist.db import get_pool, transaction
from tracewise.waitlist.email import make_sender
from tracewise.waitlist.security import normalize_email
from tracewise.waitlist.settings import WaitlistSettings

EXPORT_COLUMNS = (
    "email",
    "status",
    "created_at",
    "confirmed_at",
    "github_login",
    "updates_consent",
    "updates_consent_at",
    "consent_version",
    "ci_failure_freq",
    "disposable_domain",
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.waitlist.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    ex = sub.add_parser("export")
    ex.add_argument("--all", action="store_true", help="include unconfirmed signups")
    ex.add_argument("--json", action="store_true")
    de = sub.add_parser("delete")
    de.add_argument("email")
    ob = sub.add_parser("outbox")
    ob.add_argument("--status", choices=["pending", "sending", "sent", "failed", "cancelled", "open"], default="open")
    rt = sub.add_parser("retry")
    rt.add_argument("ids", nargs="*")
    rt.add_argument("--failed", action="store_true", help="re-queue every failed delivery")
    sub.add_parser("process")
    sub.add_parser("purge")
    a = ap.parse_args(argv)

    s = WaitlistSettings()
    if s.waitlist_database_url is None:
        print("WAITLIST_DATABASE_URL is not set", file=sys.stderr)
        return 2
    pool = get_pool(s.waitlist_database_url.get_secret_value())

    if a.cmd == "stats":
        with transaction(pool) as c:
            row = c.execute(
                """SELECT count(*) AS total,
                          count(*) FILTER (WHERE status = 'confirmed') AS confirmed,
                          count(*) FILTER (WHERE status = 'pending') AS pending,
                          count(*) FILTER (WHERE status = 'confirmed' AND updates_consent) AS confirmed_with_updates_consent,
                          count(*) FILTER (WHERE status = 'confirmed' AND github_login IS NOT NULL) AS confirmed_with_github,
                          count(*) FILTER (WHERE disposable_domain) AS disposable_flagged
                   FROM waitlist.signup"""
            ).fetchone()
            freq = c.execute(
                "SELECT coalesce(ci_failure_freq, 'unanswered') AS f, count(*) AS n FROM waitlist.signup "
                "WHERE status = 'confirmed' GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall()
            deliveries = c.execute(
                "SELECT kind, status, count(*) AS n FROM waitlist.email_outbox GROUP BY 1, 2 ORDER BY 1, 2"
            ).fetchall()
        print(
            json.dumps(
                {
                    "signups": dict(row or {}),
                    "ci_failure_freq": {r["f"]: r["n"] for r in freq},
                    "outbox": [dict(r) for r in deliveries],
                    "public": service.public_count(pool, use_memo=False),
                },
                indent=1,
                default=str,
            )
        )
        return 0

    if a.cmd == "export":
        with transaction(pool, statement_timeout_ms=30000) as c:
            rows = c.execute(
                """SELECT email, status, created_at, confirmed_at, github_login, updates_consent, updates_consent_at,
                          consent_version, ci_failure_freq, disposable_domain
                   FROM waitlist.signup WHERE %(all)s OR status = 'confirmed' ORDER BY created_at""",
                {"all": a.all},
            ).fetchall()
        if a.json:
            print(json.dumps([dict(r) for r in rows], indent=1, default=str))
        else:
            w = csv.DictWriter(sys.stdout, fieldnames=list(EXPORT_COLUMNS))
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in EXPORT_COLUMNS})
        return 0

    if a.cmd == "delete":
        email = normalize_email(a.email)
        if email is None:
            print("not a valid email address", file=sys.stderr)
            return 2
        with transaction(pool) as c:
            n = c.execute("DELETE FROM waitlist.signup WHERE email_normalized = %s", (email,)).rowcount
        print("deleted" if n else "not found")
        return 0

    if a.cmd == "outbox":
        with transaction(pool) as c:
            rows = c.execute(
                """SELECT id, kind, status, attempts, next_attempt_at, last_error, provider, provider_message_id,
                          created_at, sent_at
                   FROM waitlist.email_outbox
                   WHERE (%(st)s = 'open' AND status IN ('pending', 'sending', 'failed')) OR status = %(st)s
                   ORDER BY created_at DESC LIMIT 200""",
                {"st": a.status},
            ).fetchall()
        for r in rows:
            print(json.dumps(dict(r), default=str))
        if not s.waitlist_email_mode or s.waitlist_email_mode == "disabled":
            print("note: WAITLIST_EMAIL_MODE=disabled, so nothing is being sent", file=sys.stderr)
        return 0

    if a.cmd in ("retry", "process"):
        if a.cmd == "retry":
            ids: list[Any] = [uuid.UUID(i) for i in a.ids]
            with transaction(pool) as c:
                if a.failed:
                    n = c.execute(
                        "UPDATE waitlist.email_outbox SET status = 'pending', attempts = 0, next_attempt_at = now(), "
                        "updated_at = now() WHERE status = 'failed'"
                    ).rowcount
                else:
                    n = c.execute(
                        "UPDATE waitlist.email_outbox SET status = 'pending', attempts = 0, next_attempt_at = now(), "
                        "updated_at = now() WHERE id = ANY(%s) AND status IN ('failed', 'pending')",
                        (ids,),
                    ).rowcount
            print(f"re-queued {n}")
        sender = make_sender(
            s.waitlist_email_mode,
            file_dir=s.waitlist_email_file_dir,
            api_key=s.resend_api_key.get_secret_value() if s.resend_api_key else None,
            sender=s.waitlist_email_from,
            reply_to=s.waitlist_email_reply_to,
        )
        print(json.dumps(service.process_outbox(pool, s, sender, limit=100, budget_s=120.0)))
        return 0

    if a.cmd == "purge":
        print(json.dumps(service.purge(pool)))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
