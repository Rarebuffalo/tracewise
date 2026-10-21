"""Row-level operations (T-104). Each function takes an open connection inside a transaction;
transaction boundaries belong to the caller so multi-table writes are atomic (FS-EVT-2)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Literal

from psycopg.types.json import Jsonb

from tracewise.db.session import Conn
from tracewise.prepass.sanitize import redact

DeliveryOutcome = Literal[
    "enqueued",
    "duplicate_run",
    "ignored",
    "rejected",
    "processed",
    "repo_not_in_scope",
    "repo_disabled",
    "installation_inactive",
]
PURGE_GRACE_DAYS = 7  # FS-INS-3
Surface = Literal["commit_comment", "pr_comment", "check_run"]


def short_error(err: object, limit: int = 500) -> str:
    """Errors are stored redacted and capped; they must never carry tokens or log content.

    Stored text depends only on things input cannot control (P-5, completed in Phase 43):
    * database errors: class, SQLSTATE and schema identifiers (table, column, constraint). The primary message is
      NOT kept: PostgreSQL quotes input in some of them ('invalid input syntax for type integer: "..."'), and
      `DETAIL` carries failing-row values;
    * validation errors: count, model name and pydantic's fixed error codes. Locations are NOT kept: extra keys and
      dict keys come from the input;
    * Tracewise's own exceptions: their message, which the code controls;
    * plain strings: kept (callers pass their own reason codes);
    * anything else: the class name only (an arbitrary exception's text is unbounded content)."""
    return redact(_content_free(err))[:limit]


def _content_free(err: object) -> str:
    import psycopg
    from pydantic import ValidationError

    if isinstance(err, str):  # a reason code chosen by the caller (e.g. "cancelled_uninstalled"), not exception text
        return err
    if isinstance(err, psycopg.Error):
        d = err.diag
        ids = [
            f"{k}={v}"
            for k, v in (("table", d.table_name), ("column", d.column_name), ("constraint", d.constraint_name))
            if v and _IDENT.fullmatch(v)
        ]
        return f"{type(err).__name__} [sqlstate {err.sqlstate or '?'}]" + (f" {' '.join(ids)}" if ids else "")
    if isinstance(err, ValidationError):
        kinds = sorted({str(e.get("type", "?")) for e in err.errors(include_input=False)})[:10]
        return f"{err.error_count()} validation error(s) for {err.title}: {', '.join(kinds)}"
    if type(err).__module__.startswith("tracewise."):
        return str(err)
    return type(err).__name__


_IDENT = re.compile(r"[a-z_][a-z0-9_]{0,62}")


# ------------------------------------------------------------------ deliveries


def insert_delivery(
    conn: Conn, delivery_id: str, event: str, action: str | None, installation_id: int | None, outcome: DeliveryOutcome
) -> bool:
    """True if newly recorded; False if this delivery ID was already seen (FS-EVT-4)."""
    row = conn.execute(
        """INSERT INTO webhook_delivery (delivery_id, event, action, installation_id, outcome)
           VALUES (%s, %s, %s, %s, %s) ON CONFLICT (delivery_id) DO NOTHING RETURNING delivery_id""",
        (delivery_id, event, action, installation_id, outcome),
    ).fetchone()
    return row is not None


def set_delivery_outcome(conn: Conn, delivery_id: str, outcome: DeliveryOutcome, job_id: int | None) -> None:
    conn.execute("UPDATE webhook_delivery SET outcome = %s, job_id = %s WHERE delivery_id = %s", (outcome, job_id, delivery_id))


def get_delivery(conn: Conn, delivery_id: str) -> dict[str, Any] | None:
    return conn.execute("SELECT * FROM webhook_delivery WHERE delivery_id = %s", (delivery_id,)).fetchone()


# ------------------------------------------------------------------ tenants


def upsert_installation(conn: Conn, installation_id: int, account_login: str | None = None) -> None:
    conn.execute(
        """INSERT INTO installation (id, account_login) VALUES (%s, %s)
           ON CONFLICT (id) DO UPDATE SET account_login = COALESCE(EXCLUDED.account_login, installation.account_login)""",
        (installation_id, account_login),
    )


def upsert_repository(conn: Conn, repo_id: int, installation_id: int, full_name: str) -> None:
    conn.execute(
        """INSERT INTO repository (id, installation_id, full_name) VALUES (%s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET full_name = EXCLUDED.full_name, installation_id = EXCLUDED.installation_id""",
        (repo_id, installation_id, full_name),
    )


# ------------------------------------------------------------------ lifecycle (T-701; FS-INS-3, FS-INS-4)
#
# `deleted` is terminal: GitHub never reuses an installation id, so a late `created`/`unsuspend`
# delivery for a deleted installation must not resurrect it. Every write is guarded so replays are no-ops.


def installation_status(conn: Conn, installation_id: int) -> str | None:
    row = conn.execute("SELECT status FROM installation WHERE id = %s", (installation_id,)).fetchone()
    return str(row["status"]) if row else None


def set_installation_status(
    conn: Conn, installation_id: int, status: Literal["active", "suspended"], account_login: str | None = None
) -> bool:
    """Create or update a non-deleted installation. Returns False when it is deleted (no resurrection)."""
    row = conn.execute(
        """INSERT INTO installation (id, account_login, status) VALUES (%s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status,
               account_login = COALESCE(EXCLUDED.account_login, installation.account_login)
           WHERE installation.status <> 'deleted'
           RETURNING id""",
        (installation_id, account_login, status),
    ).fetchone()
    return row is not None


def mark_installation_deleted(conn: Conn, installation_id: int, grace_days: int = PURGE_GRACE_DAYS) -> bool:
    """FS-INS-3: deleted + purge scheduled. Idempotent: the first deletion time and purge date are kept."""
    row = conn.execute(
        """INSERT INTO installation (id, status, deleted_at, purge_after)
           VALUES (%s, 'deleted', now(), now() + make_interval(days => %s))
           ON CONFLICT (id) DO UPDATE SET status = 'deleted',
               deleted_at = COALESCE(installation.deleted_at, now()),
               purge_after = COALESCE(installation.purge_after, now() + make_interval(days => %s))
           RETURNING id""",
        (installation_id, grace_days, grace_days),
    ).fetchone()
    return row is not None


def repository_added(conn: Conn, repo_id: int, installation_id: int, full_name: str) -> None:
    """FS-INS-4: (re)grant access. Clears `removed_at`; the Tracewise-side `enabled` toggle is left alone."""
    conn.execute(
        """INSERT INTO repository (id, installation_id, full_name) VALUES (%s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET installation_id = EXCLUDED.installation_id, full_name = EXCLUDED.full_name,
               removed_at = NULL""",
        (repo_id, installation_id, full_name),
    )


def repository_removed(conn: Conn, repo_id: int, installation_id: int) -> bool:
    """FS-INS-4: access withdrawn. Only a repository owned by this installation is touched."""
    cur = conn.execute(
        """UPDATE repository SET removed_at = COALESCE(removed_at, now())
           WHERE id = %s AND installation_id = %s""",
        (repo_id, installation_id),
    )
    return cur.rowcount == 1


def ingest_scope(conn: Conn, installation_id: int, repo_id: int) -> str | None:
    """Why a failure event must not be analysed, or None if it may be. Unknown rows are allowed (created later)."""
    status = installation_status(conn, installation_id)
    if status in ("deleted", "suspended"):
        return "installation_inactive"
    row = conn.execute("SELECT installation_id, enabled, removed_at FROM repository WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        return None
    if row["removed_at"] is not None or row["installation_id"] != installation_id:
        return "repo_not_in_scope"
    if not row["enabled"]:
        return "repo_disabled"
    return None


def repository_enabled(conn: Conn, repo_id: int) -> bool:
    row = conn.execute("SELECT enabled AND removed_at IS NULL AS ok FROM repository WHERE id = %s", (repo_id,)).fetchone()
    return bool(row and row["ok"])


# ------------------------------------------------------------------ runs and analyses


def insert_workflow_run(
    conn: Conn,
    *,
    installation_id: int,
    repo_id: int,
    run_id: int,
    attempt: int,
    workflow_id: int | None,
    head_sha: str,
    head_branch: str | None,
    head_repo_id: int | None,
    event: str,
    conclusion: str,
) -> int:
    """Idempotent on (installation, repo, run, attempt) (0010: per installation, so a transferred repository's new
    installation gets its own row); returns the row id either way."""
    row = conn.execute(
        """INSERT INTO workflow_run (installation_id, repo_id, github_run_id, run_attempt, workflow_id, head_sha,
                                     head_branch, head_repo_id, event, conclusion)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (installation_id, repo_id, github_run_id, run_attempt) DO UPDATE SET conclusion = workflow_run.conclusion
           RETURNING id""",
        (installation_id, repo_id, run_id, attempt, workflow_id, head_sha, head_branch, head_repo_id, event, conclusion),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def find_workflow_run(conn: Conn, installation_id: int, repo_id: int, run_id: int, attempt: int) -> int | None:
    """The installation's own row. Explicit even under RLS, so a system-plane caller can never pick up another
    installation's row for the same run after a repository transfer."""
    row = conn.execute(
        "SELECT id FROM workflow_run WHERE installation_id = %s AND repo_id = %s AND github_run_id = %s AND run_attempt = %s",
        (installation_id, repo_id, run_id, attempt),
    ).fetchone()
    return int(row["id"]) if row else None


_QUOTA_COUNTED = ("diagnosed", "inconclusive", "could_not_complete")


def count_monthly_analyses(conn: Conn, installation_id: int) -> int:
    """T-703: analyses this UTC calendar month that ran the investigation (a diagnosis was recorded). Notices,
    logs-unavailable, permission-denied and quota-exceeded rows do not count."""
    row = conn.execute(
        """SELECT count(*) AS n FROM analysis
           WHERE installation_id = %s AND status = ANY(%s) AND diagnosis IS NOT NULL
             AND created_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
        (installation_id, list(_QUOTA_COUNTED)),
    ).fetchone()
    return int(row["n"]) if row else 0


def counted_analysis_exists(conn: Conn, run_pk: int) -> bool:
    """T-703: this run attempt already has an analysis that counts towards the quota (so it is a retry, not a new
    analysis): the quota gate must let it finish instead of re-labelling it."""
    row = conn.execute(
        "SELECT 1 FROM analysis WHERE run_pk = %s AND status = ANY(%s) AND diagnosis IS NOT NULL",
        (run_pk, list(_QUOTA_COUNTED)),
    ).fetchone()
    return row is not None


def quota_notice_today(conn: Conn, installation_id: int, repo_id: int, *, excluding_run_pk: int) -> bool:
    """T-703: whether another run of this repository already recorded today's (UTC) quota notice."""
    row = conn.execute(
        """SELECT 1 FROM analysis a JOIN workflow_run w ON w.id = a.run_pk
           WHERE a.installation_id = %s AND w.repo_id = %s AND a.status = 'quota_exceeded' AND a.run_pk <> %s
             AND a.created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' LIMIT 1""",
        (installation_id, repo_id, excluding_run_pk),
    ).fetchone()
    return row is not None


def analysis_recorded(conn: Conn, installation_id: int, repo_id: int, run_id: int, attempt: int) -> bool:
    """Whether any job attempt persisted an analysis for this run attempt. `_persist` runs before ANY publication
    surface is reserved, so False proves that nothing was (or may have been) written to GitHub for it."""
    row = conn.execute(
        """SELECT 1 FROM analysis a JOIN workflow_run w ON w.id = a.run_pk
           WHERE w.installation_id = %s AND w.repo_id = %s AND w.github_run_id = %s AND w.run_attempt = %s""",
        (installation_id, repo_id, run_id, attempt),
    ).fetchone()
    return row is not None


def repository_scope(conn: Conn, repo_id: int) -> dict[str, Any] | None:
    """Authorisation context for a job: the repository row joined with its installation."""
    return conn.execute(
        """SELECT r.id, r.installation_id, r.full_name, r.enabled, r.removed_at, i.status AS installation_status
           FROM repository r JOIN installation i ON i.id = r.installation_id WHERE r.id = %s""",
        (repo_id,),
    ).fetchone()


SNIPPET_MAX_BYTES = 2000  # P-3 (approved option A): the persisted source snippet, in UTF-8 bytes
SNIPPET_TRUNCATED = "[truncated for storage]"


def stored_snippet(snippet: str) -> str:
    """The copy of `problem_snippet` that may be persisted: redacted first, then ≤SNIPPET_MAX_BYTES UTF-8 bytes,
    whole lines where possible, never splitting a character, marked when cut (P-3). Reports are rendered from the
    in-memory diagnosis and are unaffected."""
    text = redact(snippet)
    if len(text.encode("utf-8")) <= SNIPPET_MAX_BYTES:
        return text
    budget = SNIPPET_MAX_BYTES - len(SNIPPET_TRUNCATED.encode("utf-8")) - 1
    kept, used = [], 0
    for line in text.splitlines(keepends=True):
        size = len(line.encode("utf-8"))
        if used + size > budget:
            break
        kept.append(line)
        used += size
    head = "".join(kept) or text.encode("utf-8")[:budget].decode("utf-8", errors="ignore") + "\n"
    if not head.endswith("\n"):
        head += "\n"
    return head + SNIPPET_TRUNCATED


def _storable(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """The persistence boundary for the diagnosis document: every writer goes through upsert_analysis."""
    snippet = diagnosis.get("problem_snippet")
    if isinstance(snippet, str):
        return {**diagnosis, "problem_snippet": stored_snippet(snippet)}
    return diagnosis


def upsert_analysis(
    conn: Conn,
    *,
    installation_id: int,
    run_pk: int,
    status: str,
    category: str | None,
    confidence_band: str | None,
    diagnosis: dict[str, Any] | None,
    provider: str | None = None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms: int | None = None,
    cost_usd: Decimal | None = None,
) -> int:
    row = conn.execute(
        """INSERT INTO analysis (installation_id, run_pk, status, category, confidence_band, diagnosis, provider, model,
                                 tokens_in, tokens_out, latency_ms, cost_usd)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (run_pk) DO UPDATE SET status = EXCLUDED.status, category = EXCLUDED.category,
               confidence_band = EXCLUDED.confidence_band, diagnosis = EXCLUDED.diagnosis, provider = EXCLUDED.provider,
               model = EXCLUDED.model, tokens_in = EXCLUDED.tokens_in, tokens_out = EXCLUDED.tokens_out,
               latency_ms = EXCLUDED.latency_ms, cost_usd = EXCLUDED.cost_usd, updated_at = now()
           RETURNING id""",
        (
            installation_id,
            run_pk,
            status,
            category,
            confidence_band,
            Jsonb(_storable(diagnosis)) if diagnosis is not None else None,
            provider,
            model,
            tokens_in,
            tokens_out,
            latency_ms,
            cost_usd,
        ),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def record_analysis_ops(conn: Conn, analysis_id: int, stage_ms: dict[str, int], publish_result: dict[str, str]) -> None:
    """T-706 (AT-OPS-01): stage timings and publish result. Identifiers and numbers only; idempotent overwrite."""
    conn.execute(
        "UPDATE analysis SET stage_ms = %s, publish_result = %s, finished_at = now(), updated_at = now() WHERE id = %s",
        (Jsonb(stage_ms), Jsonb(publish_result), analysis_id),
    )


# ------------------------------------------------------------------ publications (FS-PUB-1, FS-PUB-2)


def commit_comment_key(repo_id: int, head_sha: str, workflow_id: int | None) -> str:
    return f"{repo_id}:{head_sha}:{workflow_id or 0}"


def pr_comment_key(repo_id: int, pr_number: int, workflow_id: int | None) -> str:
    return f"{repo_id}:pr{pr_number}:{workflow_id or 0}"


def check_run_key(repo_id: int, run_id: int) -> str:
    return f"{repo_id}:{run_id}"


class PublicationNotVisible(Exception):
    """The reservation exists but this transaction cannot see it (it should be impossible with per-installation
    keys). A permanent condition for the job, never a retry loop and never an AssertionError."""


def reserve_publication(
    conn: Conn, *, installation_id: int, analysis_id: int, surface: Surface, target_key: str
) -> dict[str, Any]:
    """Get or create the publication row for (surface, target), locked for this transaction.

    Callers decide from the returned row: a `published` commit comment must be skipped
    (write-once); a `published` PR comment or Check Run is edited via its `github_id`.
    """
    conn.execute(
        """INSERT INTO publication (installation_id, analysis_id, surface, target_key) VALUES (%s, %s, %s, %s)
           ON CONFLICT (installation_id, surface, target_key) DO NOTHING""",
        (installation_id, analysis_id, surface, target_key),
    )
    row = conn.execute(
        "SELECT * FROM publication WHERE installation_id = %s AND surface = %s AND target_key = %s FOR UPDATE",
        (installation_id, surface, target_key),
    ).fetchone()
    if row is None:
        raise PublicationNotVisible(surface)
    return row


def mark_published(
    conn: Conn,
    publication_id: int,
    analysis_id: int,
    github_id: int,
    *,
    source_run_id: int | None = None,
    source_attempt: int | None = None,
    content_digest: str | None = None,
) -> None:
    conn.execute(
        """UPDATE publication SET state = 'published', github_id = %s, analysis_id = %s, last_error = NULL,
               missing_permission = NULL, source_run_id = COALESCE(%s, source_run_id),
               source_attempt = COALESCE(%s, source_attempt), content_digest = COALESCE(%s, content_digest),
               updated_at = now()
           WHERE id = %s""",
        (github_id, analysis_id, source_run_id, source_attempt, content_digest, publication_id),
    )


def mark_unpublished_permission(conn: Conn, publication_id: int, permission: str | None) -> None:
    """FS-PUB-5 / FS-ERR-3: the surface could not be written for lack of a permission. Never overwrites a published row."""
    conn.execute(
        """UPDATE publication SET state = 'unpublished_permission', missing_permission = %s, updated_at = now()
           WHERE id = %s AND state <> 'published'""",
        ((permission or "unknown")[:100], publication_id),
    )


def mark_publication_failed(conn: Conn, publication_id: int, error: object) -> None:
    conn.execute(
        "UPDATE publication SET state = 'failed', last_error = %s, updated_at = now() WHERE id = %s AND state <> 'published'",
        (short_error(error), publication_id),
    )


# ------------------------------------------------------------------ signatures, usage, audit


def record_signature(
    conn: Conn, *, repo_id: int, installation_id: int, fingerprint: str, normalized_message: str, run_pk: int
) -> int:
    """Insert or bump a failure fingerprint; returns occurrences after this run."""
    row = conn.execute(
        """INSERT INTO failure_signature
               (repo_id, fingerprint, installation_id, normalized_message, first_seen_run, last_seen_run)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (installation_id, repo_id, fingerprint) DO UPDATE SET
               occurrences = failure_signature.occurrences
                   + CASE WHEN failure_signature.last_seen_run = EXCLUDED.last_seen_run THEN 0 ELSE 1 END,
               last_seen_run = EXCLUDED.last_seen_run, last_seen_at = now()
           RETURNING occurrences""",
        (repo_id, fingerprint, installation_id, redact(normalized_message)[:300], run_pk, run_pk),
    ).fetchone()
    assert row is not None
    return int(row["occurrences"])


def add_usage(conn: Conn, installation_id: int, kind: str, quantity: float, analysis_id: int | None = None) -> None:
    conn.execute(
        "INSERT INTO usage_event (installation_id, analysis_id, kind, quantity) VALUES (%s, %s, %s, %s)",
        (installation_id, analysis_id, kind, quantity),
    )


def audit(conn: Conn, actor: str, action: str, installation_id: int | None = None, **detail: str | int | bool | None) -> None:
    """Content-free audit trail: identifiers and flags only."""
    conn.execute(
        "INSERT INTO audit_event (installation_id, actor, action, detail) VALUES (%s, %s, %s, %s)",
        (installation_id, actor, action, Jsonb(detail)),
    )
