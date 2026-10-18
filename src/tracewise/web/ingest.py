"""Webhook ingestion transaction (T-106; FS-EVT-1, FS-EVT-2, FS-EVT-4).

The delivery row, the run row and the job row are written in ONE transaction:
either all exist or none do, so a failed request can be safely redelivered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psycopg_pool import ConnectionPool

from tracewise.contracts import AnalysisJob, WorkflowRunEvent
from tracewise.db import repositories as repo
from tracewise.db.session import Conn, transaction
from tracewise.jobs import queue

Outcome = Literal[
    "enqueued",
    "duplicate_delivery",
    "duplicate_run",
    "ignored",
    "rejected",
    "repo_not_in_scope",
    "repo_disabled",
    "installation_inactive",
]
ANALYZE = "analyze"


@dataclass(frozen=True)
class IngestResult:
    outcome: Outcome
    job_id: int | None = None


def ingest_workflow_run(
    pool: ConnectionPool[Conn], delivery_id: str, event: WorkflowRunEvent, timeout_s: float = 3.0
) -> IngestResult:
    action = event.action
    inst = event.installation.id
    with transaction(pool, timeout_s) as conn:
        if not repo.insert_delivery(conn, delivery_id, "workflow_run", action, inst, "ignored"):
            return IngestResult("duplicate_delivery")
        if not event.should_analyse():
            return IngestResult("ignored")  # e.g. in_progress, success, startup_failure (gated)
        refusal = repo.ingest_scope(conn, inst, event.repository.id)  # T-701: AT-INS-04, FS-INS-3
        if refusal is not None:
            repo.set_delivery_outcome(conn, delivery_id, refusal, None)  # type: ignore[arg-type]
            return IngestResult(refusal)  # type: ignore[arg-type]
        run = event.workflow_run
        repo.upsert_installation(conn, inst)
        repo.upsert_repository(conn, event.repository.id, inst, event.repository.full_name)
        repo.insert_workflow_run(
            conn,
            installation_id=inst,
            repo_id=event.repository.id,
            run_id=run.id,
            attempt=run.run_attempt,
            workflow_id=run.workflow_id,
            head_sha=run.head_sha,
            head_branch=run.head_branch,
            head_repo_id=run.head_repository.id if run.head_repository else None,
            event=run.event,
            conclusion=run.conclusion or "",
        )
        payload = AnalysisJob.from_event(event, delivery_id).model_dump(mode="json")
        job_id = queue.enqueue(
            conn,
            kind=ANALYZE,
            installation_id=inst,
            dedupe_key=event.dedupe_key,
            payload=payload,
            run_key=f"{event.repository.id}:{run.id}",
        )
        if job_id is None:
            repo.set_delivery_outcome(conn, delivery_id, "duplicate_run", None)
            return IngestResult("duplicate_run")
        repo.set_delivery_outcome(conn, delivery_id, "enqueued", job_id)
        return IngestResult("enqueued", job_id)


def record_other(
    pool: ConnectionPool[Conn],
    delivery_id: str,
    event: str,
    action: str | None,
    installation_id: int | None,
    outcome: Literal["ignored", "rejected"],
    timeout_s: float = 3.0,
) -> bool:
    """Record a non-analysed or rejected (signed but malformed) delivery. False if already seen."""
    with transaction(pool, timeout_s) as conn:
        return repo.insert_delivery(conn, delivery_id, event, action, installation_id, outcome)
