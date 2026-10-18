"""Row-level operations (T-104). Each function takes an open connection inside a transaction;
transaction boundaries belong to the caller so multi-table writes are atomic (FS-EVT-2)."""

from __future__ import annotations

from typing import Any, Literal

from psycopg.types.json import Jsonb

from tracewise.db.session import Conn
from tracewise.prepass.sanitize import redact

DeliveryOutcome = Literal["enqueued", "duplicate_run", "ignored", "rejected"]
Surface = Literal["commit_comment", "pr_comment", "check_run"]


def short_error(err: object, limit: int = 500) -> str:
    """Errors are stored redacted and capped; they must never carry tokens or log content."""
    return redact(str(err))[:limit]


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
    """Idempotent on (repo, run, attempt); returns the row id either way."""
    row = conn.execute(
        """INSERT INTO workflow_run (installation_id, repo_id, github_run_id, run_attempt, workflow_id, head_sha,
                                     head_branch, head_repo_id, event, conclusion)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (repo_id, github_run_id, run_attempt) DO UPDATE SET conclusion = workflow_run.conclusion
           RETURNING id""",
        (installation_id, repo_id, run_id, attempt, workflow_id, head_sha, head_branch, head_repo_id, event, conclusion),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def find_workflow_run(conn: Conn, repo_id: int, run_id: int, attempt: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM workflow_run WHERE repo_id = %s AND github_run_id = %s AND run_attempt = %s",
        (repo_id, run_id, attempt),
    ).fetchone()
    return int(row["id"]) if row else None


def repository_scope(conn: Conn, repo_id: int) -> dict[str, Any] | None:
    """Authorisation context for a job: the repository row joined with its installation."""
    return conn.execute(
        """SELECT r.id, r.installation_id, r.full_name, r.enabled, r.removed_at, i.status AS installation_status
           FROM repository r JOIN installation i ON i.id = r.installation_id WHERE r.id = %s""",
        (repo_id,),
    ).fetchone()


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
) -> int:
    row = conn.execute(
        """INSERT INTO analysis (installation_id, run_pk, status, category, confidence_band, diagnosis, provider, model,
                                 tokens_in, tokens_out, latency_ms)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (run_pk) DO UPDATE SET status = EXCLUDED.status, category = EXCLUDED.category,
               confidence_band = EXCLUDED.confidence_band, diagnosis = EXCLUDED.diagnosis, provider = EXCLUDED.provider,
               model = EXCLUDED.model, tokens_in = EXCLUDED.tokens_in, tokens_out = EXCLUDED.tokens_out,
               latency_ms = EXCLUDED.latency_ms, updated_at = now()
           RETURNING id""",
        (
            installation_id,
            run_pk,
            status,
            category,
            confidence_band,
            Jsonb(diagnosis) if diagnosis is not None else None,
            provider,
            model,
            tokens_in,
            tokens_out,
            latency_ms,
        ),
    ).fetchone()
    assert row is not None
    return int(row["id"])


# ------------------------------------------------------------------ publications (FS-PUB-1, FS-PUB-2)


def commit_comment_key(repo_id: int, head_sha: str, workflow_id: int | None) -> str:
    return f"{repo_id}:{head_sha}:{workflow_id or 0}"


def pr_comment_key(repo_id: int, pr_number: int, workflow_id: int | None) -> str:
    return f"{repo_id}:pr{pr_number}:{workflow_id or 0}"


def check_run_key(repo_id: int, run_id: int) -> str:
    return f"{repo_id}:{run_id}"


def reserve_publication(
    conn: Conn, *, installation_id: int, analysis_id: int, surface: Surface, target_key: str
) -> dict[str, Any]:
    """Get or create the publication row for (surface, target), locked for this transaction.

    Callers decide from the returned row: a `published` commit comment must be skipped
    (write-once); a `published` PR comment or Check Run is edited via its `github_id`.
    """
    conn.execute(
        """INSERT INTO publication (installation_id, analysis_id, surface, target_key) VALUES (%s, %s, %s, %s)
           ON CONFLICT (surface, target_key) DO NOTHING""",
        (installation_id, analysis_id, surface, target_key),
    )
    row = conn.execute(
        "SELECT * FROM publication WHERE surface = %s AND target_key = %s FOR UPDATE", (surface, target_key)
    ).fetchone()
    assert row is not None
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
           ON CONFLICT (repo_id, fingerprint) DO UPDATE SET
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
