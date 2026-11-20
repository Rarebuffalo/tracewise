"""Job attempt fencing (D-1, D-2): one database-decided owner per job attempt.

A job's ownership generation is its `attempts` counter: every claim, including a reclaim after the reaper took an
expired lease back, increments it in the same UPDATE that sets `locked_by`. An attempt is therefore identified by
(`id`, `locked_by`, `attempts`), and a reclaimed job always has a newer generation.

Queue transitions (complete, fail, heartbeat, cancel) check that triple in their own conditional UPDATE. Writes made
elsewhere (the analysis record, publication state, the ops record) run on the tenant plane, whose role should not
need job-table rights (D-11). They call `tracewise_job_owned(job, installation, worker, attempt, lock)` inside their
own transaction, before writing:

* `lock = true` takes `FOR SHARE` on the job row until that transaction ends. The reaper and a reclaim both UPDATE
  the row, so they wait: ownership cannot change between the check and the caller's commit.
* `lock = false` is a plain check, used immediately before an external (GitHub) request, so no row lock is held
  across a network call (which would also stall the owner's own heartbeat).

SECURITY DEFINER (owned by the migration owner, fixed search_path, PUBLIC revoked) so that the tenant role can ask
only this one question about one job of its own installation: the function also requires the transaction's tenant
setting, when set, to match. It reveals nothing but a boolean. Additive: no grant is removed; existing rows need no
backfill (`attempts` already exists and is NOT NULL). Downgrade drops the function; code at this revision then fails
at startup (`require_schema_at`), not silently unfenced.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UP = """
CREATE FUNCTION tracewise_job_owned(p_job_id bigint, p_installation_id bigint, p_worker text, p_attempt integer,
                                    p_lock boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    tenant text := NULLIF(current_setting('tracewise.installation_id', true), '');
BEGIN
    IF tenant IS NOT NULL AND tenant <> p_installation_id::text THEN
        RETURN false;  -- a tenant transaction may only ask about its own installation's jobs
    END IF;
    IF p_lock THEN
        PERFORM 1 FROM job
         WHERE id = p_job_id AND installation_id = p_installation_id AND status = 'running'
           AND locked_by = p_worker AND attempts = p_attempt
         FOR SHARE;
    ELSE
        PERFORM 1 FROM job
         WHERE id = p_job_id AND installation_id = p_installation_id AND status = 'running'
           AND locked_by = p_worker AND attempts = p_attempt;
    END IF;
    RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION tracewise_job_owned(bigint, bigint, text, integer, boolean) FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_system') THEN
        GRANT EXECUTE ON FUNCTION tracewise_job_owned(bigint, bigint, text, integer, boolean) TO tracewise_system;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        GRANT EXECUTE ON FUNCTION tracewise_job_owned(bigint, bigint, text, integer, boolean) TO tracewise_app;
    END IF;
END $$;
"""

DOWN = """
DROP FUNCTION IF EXISTS tracewise_job_owned(bigint, bigint, text, integer, boolean);
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
