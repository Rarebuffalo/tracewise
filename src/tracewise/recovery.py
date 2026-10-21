"""Recovery (T-702; FS-EVT-5, AT-REL-03): (a) redeliver failed webhook deliveries, (b) sweep recent failed
runs that never reached us (e.g. payloads over 25 MB are never delivered).

Both are bounded, idempotent and resumable:
* (a) lists `GET /app/hook/deliveries?status=failure` (App JWT) up to `max_pages`, keeps deliveries newer than
  the floor (`now - window`, never older than the last completed scan minus an overlap), groups them by GUID
  and asks GitHub to redeliver (`POST …/attempts`) only when: we never recorded that GUID, no attempt for it
  succeeded, the event is one we handle, the installation is not inactive, the per-GUID attempt cap is not
  reached and the last request is older than the cooldown. Every request is recorded in `redelivery_request`.
  The high-water mark advances only after a scan completes. Delivery order is not documented, so nothing
  stops early on time.
* (b) walks enabled, in-scope repositories of active installations round-robin from a durable cursor, lists
  `GET /repos/{o}/{r}/actions/runs?status=failure|timed_out&created>=…` with the repository's analysis token,
  and feeds each run through the normal ingestion path (`ingest_workflow_run`), so delivery/run dedupe and
  T-701 scope checks apply exactly as for webhooks. The cursor advances after each repository finishes.
Neither ever runs analyses itself or publishes; they only (re)create the normal inputs. Rate limits stop the
current pass cleanly (checkpoints keep progress); the next pass resumes.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from tracewise.contracts import WorkflowRunEvent
from tracewise.db.session import Conn, DatabaseUnavailable, transaction
from tracewise.github import errors as gh_err
from tracewise.github.auth import AppCredentials, TokenProvider
from tracewise.github.client import GitHubHTTP, RepoClient
from tracewise.observe import event
from tracewise.web.ingest import ingest_workflow_run

log = logging.getLogger(__name__)

HANDLED_EVENTS = frozenset({"workflow_run", "installation", "installation_repositories"})
_GUID = re.compile(r"^[A-Za-z0-9-]{1,200}$")


@dataclass
class RecoverySummary:
    kind: str
    scanned: int = 0
    candidates: int = 0
    already_received: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    redelivered: int = 0
    enqueued: int = 0
    duplicates: int = 0
    refused: int = 0
    repos_swept: int = 0
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stopped: str | None = None
    failed_repos: int = 0  # repositories skipped this pass after a GitHub fault (revisited next round)
    completed: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["skipped"], d["errors"] = dict(self.skipped), dict(self.errors)
        return d


# One pass of each kind at a time (overlapping cron runs): a second pass would repeat redelivery POSTs inside the
# cooldown and could overwrite the first pass's held high-water mark. Transaction-level try-locks, held by a
# connection that stays open for the pass: released at commit, rollback or process death; never contended.
PASS_LOCKS = {"deliveries": 0x7477_7265_6465_6C76, "sweep": 0x7477_7265_7377_6570}


@contextlib.contextmanager
def _exclusive(pool: ConnectionPool[Conn], kind: str) -> Iterator[bool]:
    with transaction(pool) as conn:
        row = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok", (PASS_LOCKS[kind],)).fetchone()
        yield bool(row and row["ok"])


def redeliver_failed_deliveries(pool: ConnectionPool[Conn], *args: Any, **kw: Any) -> RecoverySummary:
    """See `_redeliver_failed_deliveries`; refuses to overlap another deliveries pass (`stopped: locked`)."""
    with _exclusive(pool, "deliveries") as ok:
        if not ok:
            event(log, "recovery.locked", logging.WARNING, kind="deliveries")
            return _done(_locked("redeliver"), completed=False)
        return _redeliver_failed_deliveries(pool, *args, **kw)


def sweep_failed_runs(pool: ConnectionPool[Conn], *args: Any, **kw: Any) -> RecoverySummary:
    """See `_sweep_failed_runs`; refuses to overlap another sweep (`stopped: locked`)."""
    with _exclusive(pool, "sweep") as ok:
        if not ok:
            event(log, "recovery.locked", logging.WARNING, kind="sweep")
            return _done(_locked("sweep"), completed=False)
        return _sweep_failed_runs(pool, *args, **kw)


def _locked(kind: str) -> RecoverySummary:
    s = RecoverySummary(kind)
    s.stopped = "locked"
    return s


def _stop_reason(e: gh_err.GitHubRetryable) -> str:
    """A rate limit (with a reset time) is not the same signal as a 5xx or a transport failure."""
    return "rate_limited" if e.retry_after_s is not None or "rate limited" in str(e) else "github_unavailable"


def _checkpoint(conn: Conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM recovery_checkpoint WHERE key = %s", (key,)).fetchone()
    return str(row["value"]) if row else None


def _set_checkpoint(conn: Conn, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO recovery_checkpoint (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (key, value),
    )


def _ts(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- (a) redelivery


def _succeeded(code: object) -> bool:
    """A delivery attempt GitHub answered 2xx/3xx. Anything that is not an int (untrusted JSON) is not a success."""
    return isinstance(code, int) and not isinstance(code, bool) and 200 <= code < 400


def _redeliver_failed_deliveries(
    pool: ConnectionPool[Conn],
    http: GitHubHTTP,
    creds: AppCredentials,
    *,
    window: timedelta = timedelta(hours=72),
    overlap: timedelta = timedelta(minutes=10),
    max_pages: int = 10,
    max_requests: int = 50,
    max_attempts: int = 3,
    cooldown: timedelta = timedelta(minutes=15),
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RecoverySummary:
    s = RecoverySummary("redeliver")
    t_now = now()
    with transaction(pool) as conn:
        hw = _ts(_checkpoint(conn, "deliveries:high_water"))
    floor = t_now - window if hw is None else max(t_now - window, hw - overlap)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    newest: datetime | None = None
    jwt_ = creds.app_jwt()
    try:
        for d in http.app_paginate("list_app_hook_deliveries", jwt_, None, {"per_page": 100, "status": "failure"}):
            if s.scanned >= max_pages * 100:
                s.stopped = "page_cap"  # unseen deliveries remain: the high-water mark must not advance
                break
            s.scanned += 1
            if not isinstance(d, dict):
                s.skipped["malformed"] += 1
                continue
            when = _ts(d.get("delivered_at"))
            guid, did = d.get("guid"), d.get("id")
            if when is None or not isinstance(guid, str) or not _GUID.match(guid) or not isinstance(did, int):
                s.skipped["malformed"] += 1
                continue
            newest = when if newest is None or when > newest else newest
            if when >= floor:
                groups[guid].append(d)
    except gh_err.GitHubRetryable as e:
        s.stopped = _stop_reason(e)
        s.errors["list"] += 1
        return _done(s, completed=False)
    except gh_err.GitHubPermanent:  # 4xx, invalid JSON, unexpected shape: report, never raise or advance
        s.stopped = "list_failed"
        s.errors["list"] += 1
        return _done(s, completed=False)
    requested = 0
    hold: datetime | None = None  # oldest latest-attempt time of a delivery skipped only for its cooldown
    for guid, attempts in sorted(groups.items()):
        s.candidates += 1
        latest = max(attempts, key=lambda a: (_ts(a["delivered_at"]), a["id"]))
        if any(_succeeded(a.get("status_code")) for a in attempts):
            s.skipped["succeeded_later"] += 1
            continue
        if latest.get("event") not in HANDLED_EVENTS:
            s.skipped["unhandled_event"] += 1
            continue
        with transaction(pool) as conn:
            if conn.execute("SELECT 1 FROM webhook_delivery WHERE delivery_id = %s", (guid,)).fetchone():
                s.already_received += 1
                continue
            inst = latest.get("installation_id")
            if isinstance(inst, int) and latest.get("event") == "workflow_run":
                row = conn.execute("SELECT status FROM installation WHERE id = %s", (inst,)).fetchone()
                if row and row["status"] != "active":
                    s.skipped["installation_inactive"] += 1
                    continue
            req = conn.execute(
                "SELECT attempts, last_requested_at FROM redelivery_request WHERE guid = %s FOR UPDATE", (guid,)
            ).fetchone()
            if req and req["attempts"] >= max_attempts:
                s.skipped["max_attempts"] += 1
                continue
            if req and req["last_requested_at"] and req["last_requested_at"] > t_now - cooldown:
                s.skipped["cooldown"] += 1
                when = _ts(latest["delivered_at"])  # still below the attempt cap: keep it inside the next window
                hold = when if hold is None or (when is not None and when < hold) else hold
                continue
            if requested >= max_requests:
                s.stopped = s.stopped or "request_cap"  # keep an earlier reason (e.g. page_cap)
                break
            interrupted = False
            try:
                http.app_post("redeliver_app_hook_delivery", jwt_, {"delivery_id": latest["id"]})
                status = "requested"
            except gh_err.GitHubRetryable as e:
                s.stopped = s.stopped or _stop_reason(e)
                s.errors["redeliver"] += 1
                if _stop_reason(e) == "rate_limited":
                    break  # a definite refusal: nothing reached GitHub, so nothing is recorded
                # 5xx or transport failure: the POST may have reached GitHub. Record an uncertain attempt
                # (the cooldown and the attempt cap apply to it), then stop.
                status, interrupted = "uncertain", True
            except gh_err.GitHubPermanent as e:
                status = f"refused:{e.status}"
                s.errors["redeliver"] += 1
            requested += 1
            conn.execute(
                """INSERT INTO redelivery_request (guid, github_delivery_id, installation_id, event, attempts, last_requested_at,
                                                   last_status)
                   VALUES (%s, %s, %s, %s, 1, %s, %s)
                   ON CONFLICT (guid) DO UPDATE SET attempts = redelivery_request.attempts + 1,
                       last_requested_at = EXCLUDED.last_requested_at,
                       github_delivery_id = EXCLUDED.github_delivery_id, last_status = EXCLUDED.last_status""",
                (guid, latest["id"], inst if isinstance(inst, int) else None, str(latest.get("event")), t_now, status),
            )
            event(
                log,
                "recovery.redelivery_requested",
                logging.INFO if status == "requested" else logging.WARNING,
                delivery_id=guid,
                installation_id=inst if isinstance(inst, int) else None,
                gh_event=str(latest.get("event"))[:64],
                status=status,
            )
            if status == "requested":
                s.redelivered += 1
            if interrupted:
                break
    if s.stopped is None and newest is not None:  # only a complete pass may advance the high-water mark
        # ...and never past a delivery that is only waiting for its cooldown: otherwise it falls below the next
        # floor (hw - overlap) and is never requested again. The attempt cap bounds how long the mark is held.
        mark = newest if hold is None else min(newest, hold)
        with transaction(pool) as conn:
            _set_checkpoint(conn, "deliveries:high_water", mark.isoformat())
    return _done(s, completed=s.stopped is None)


# ---------------------------------------------------------------- (b) failed-run sweep


def _repos_after(conn: Conn, cursor: int, limit: int) -> list[dict[str, Any]]:
    sql = """SELECT r.id, r.installation_id, r.full_name FROM repository r JOIN installation i ON i.id = r.installation_id
             WHERE i.status = 'active' AND r.enabled AND r.removed_at IS NULL AND r.id > %s ORDER BY r.id LIMIT %s"""
    return list(conn.execute(sql, (cursor, limit)).fetchall())


def _sweep_failed_runs(
    pool: ConnectionPool[Conn],
    http: GitHubHTTP,
    tokens: TokenProvider,
    *,
    window: timedelta = timedelta(hours=24),
    max_repos: int = 50,
    max_pages: int = 3,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RecoverySummary:
    s = RecoverySummary("sweep")
    since = (now() - window).strftime("%Y-%m-%dT%H:%M:%SZ")
    with transaction(pool) as conn:
        cursor = int(_checkpoint(conn, "sweep:repo_cursor") or 0)
        repos = _repos_after(conn, cursor, max_repos)
        if len(repos) < max_repos and cursor:  # wrap around for round-robin fairness
            seen = {r["id"] for r in repos}
            repos += [r for r in _repos_after(conn, 0, max_repos - len(repos)) if r["id"] not in seen and r["id"] <= cursor]
    for r in repos:
        rc = RepoClient(
            http, tokens, installation_id=r["installation_id"], repo_id=r["id"], full_name=r["full_name"], scope="analysis"
        )
        try:
            for conclusion in ("failure", "timed_out"):
                runs = rc.paginate(
                    "list_workflow_runs",
                    "workflow_runs",
                    query={"status": conclusion, "created": f">={since}", "exclude_pull_requests": "true"},
                )[: max_pages * 100]
                for run in runs:
                    s.scanned += 1
                    _ingest_run(pool, r, run, s)
        except gh_err.GitHubRetryable as e:
            if _stop_reason(e) == "rate_limited":
                s.stopped = "rate_limited"  # stop the whole pass: every further call would be refused too
                s.errors["list_runs"] += 1
                break
            s.errors["GitHubRetryable"] += 1  # this repository only: skip it, keep sweeping the others
            s.failed_repos += 1
            event(
                log,
                "recovery.repo_failed",
                logging.WARNING,
                repo_id=r["id"],
                installation_id=r["installation_id"],
                error_type=type(e).__name__,
            )
            continue
        except (gh_err.InstallationUnavailable, gh_err.PermissionDenied, gh_err.NotFound) as e:
            s.errors[type(e).__name__] += 1  # lifecycle (T-701) or the next pass sorts this out; move on
        except gh_err.GitHubPermanent as e:  # 4xx, invalid JSON, unexpected shape: never block the other repositories
            s.errors["GitHubPermanent"] += 1
            s.failed_repos += 1
            event(
                log,
                "recovery.repo_failed",
                logging.WARNING,
                repo_id=r["id"],
                installation_id=r["installation_id"],
                error_type=type(e).__name__,
            )
            continue
        s.repos_swept += 1
        with transaction(pool) as conn:
            _set_checkpoint(conn, "sweep:repo_cursor", str(r["id"]))
    return _done(s, completed=s.stopped is None and s.failed_repos == 0)


def _ingest_run(pool: ConnectionPool[Conn], r: dict[str, Any], run: dict[str, Any], s: RecoverySummary) -> None:
    if not isinstance(run, dict) or run.get("conclusion") not in ("failure", "timed_out"):
        s.skipped["not_failed"] += 1
        return
    listed_repo = run.get("repository")
    if not isinstance(listed_repo, dict) or listed_repo.get("id") != r["id"]:
        s.skipped["foreign_repo"] += 1  # never re-label a run GitHub attributes to another repository
        return
    repo_ref = {"id": r["id"], "full_name": r["full_name"]}
    try:
        ev = WorkflowRunEvent.model_validate(
            {
                "action": "completed",
                "installation": {"id": r["installation_id"]},
                "repository": repo_ref,
                "workflow_run": {**run, "repository": repo_ref},
            }
        )
    except ValidationError:
        s.skipped["malformed"] += 1
        return
    delivery = f"sweep-{r['id']}-{ev.workflow_run.id}-{ev.workflow_run.run_attempt}"
    out = ingest_workflow_run(pool, delivery, ev).outcome
    event(
        log,
        "recovery.run_ingested",
        delivery_id=delivery,
        installation_id=r["installation_id"],
        repo_id=r["id"],
        run_id=ev.workflow_run.id,
        outcome=out,
    )
    if out == "enqueued":
        s.enqueued += 1
    elif out in ("duplicate_run", "duplicate_delivery"):
        s.duplicates += 1
    else:
        s.refused += 1


def _done(s: RecoverySummary, *, completed: bool) -> RecoverySummary:
    s.completed = completed
    event(
        log,
        "recovery.pass_finished",
        logging.INFO if completed else logging.WARNING,
        **{k: v for k, v in s.as_dict().items() if k != "kind"},
        recovery_pass=s.kind,
    )
    return s


# ---------------------------------------------------------------- entry point (no schedule is configured anywhere)


def build_from_settings() -> tuple[ConnectionPool[Conn], GitHubHTTP, AppCredentials]:
    """Project-scoped App credentials and the system-plane database role (ADR-16, T-705). Fails closed when unconfigured."""
    from tracewise.config import get_settings
    from tracewise.db.session import make_pool

    st = get_settings()
    if not (st.database_url_system and st.github_app_id and st.github_app_private_key_path):
        raise SystemExit("recovery needs DATABASE_URL_SYSTEM, GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH (project App only)")
    return (
        make_pool(st.database_url_system.get_secret_value()),
        GitHubHTTP(),
        AppCredentials.from_pem_file(st.github_app_id, st.github_app_private_key_path),
    )


def main(argv: list[str] | None = None, build: Callable[[], tuple[Any, Any, Any]] = build_from_settings) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="python -m tracewise.recovery", description="One bounded recovery pass (T-702).")
    ap.add_argument("what", choices=["deliveries", "runs", "both"])
    a = ap.parse_args(argv)
    pool, http, creds = build()
    out: list[RecoverySummary] = []
    try:
        if a.what in ("deliveries", "both"):
            out.append(redeliver_failed_deliveries(pool, http, creds))
        if a.what in ("runs", "both"):
            out.append(sweep_failed_runs(pool, http, TokenProvider(creds, http, clock=time.time)))
    except DatabaseUnavailable as e:
        event(log, "recovery.failed", logging.ERROR, error_type=type(e).__name__)
        print(json.dumps({"error": "database_unavailable", "completed": [x.as_dict() for x in out]}, sort_keys=True))
        return 1
    print(json.dumps([x.as_dict() for x in out], sort_keys=True))
    return 0 if all(x.completed for x in out) else 1


if __name__ == "__main__":
    from tracewise.logging import configure_cli

    configure_cli()
    raise SystemExit(main())
