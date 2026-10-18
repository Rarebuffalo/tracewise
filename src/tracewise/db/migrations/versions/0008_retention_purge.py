"""Retention and tenant purge (T-704; FS-SEC-3, FS-INS-3, AT-SEC-12, AT-INS-03).

`tracewise_purge(batch_limit)` applies the documented retention policy and returns per-step counts. It is the
only way the runtime can delete tenant content. The system role keeps no DELETE privilege on analyses,
publications or audit events. Instead it may EXECUTE this one fixed-policy function (SECURITY DEFINER, owned by
the migration owner). It takes no dates: the cut-offs use the database clock, so a caller cannot widen what
is deleted. Every step is bounded by `batch_limit` (clamped to 1..10000). One call is one transaction. A
transaction-level advisory try-lock makes concurrent calls return `locked` instead of contending.

Policy (SPEC FS-SEC-3 is the ceiling; ARCHITECTURE §3 gives the per-table periods; DECISIONS D-12):

* `analysis.diagnosis` (holds the redacted excerpts): set to NULL 90 days after the analysis was last
  written; `content_purged_at` is set.
* `analysis` rows: deleted 180 days after the last write, with their publications. Usage rows are detached
  (`analysis_id` set to NULL).
* `webhook_delivery`: deleted 14 days after receipt.
* `failure_signature`: deleted 365 days after it was last seen.
* `workflow_run`: deleted after 365 days, once no analysis references it.
* `job`: terminal jobs only, 365 days after they finished. Queued, running and retry_wait jobs are never touched.
* `usage_event`, `audit_event`, `redelivery_request`: deleted 365 days after creation or last request.
* Tenant purge: for a `deleted` installation whose `purge_after` has passed and that has no queued, running or
  retry_wait job, every tenant row for that installation is deleted, bounded per call. Audit events are kept for
  their own 365 days. When nothing is left, `purged_at` is set, `account_login` is cleared and a
  `tenant_purged` audit event is written. The installation row stays as a tombstone, so a late lifecycle event
  can never resurrect it (D-10).

Rows without a usable expiry are never deleted by guesswork. Examples: a `deleted` installation with
`purge_after` NULL, a non-terminal job, a redelivery request never sent. Such installations are counted in
`tenants_without_purge_after`.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE installation ADD COLUMN purged_at timestamptz;
ALTER TABLE analysis ADD COLUMN content_purged_at timestamptz;
CREATE INDEX analysis_updated ON analysis (updated_at);
CREATE INDEX job_finished ON job (finished_at) WHERE finished_at IS NOT NULL;
CREATE INDEX failure_signature_last_seen ON failure_signature (last_seen_at);
CREATE INDEX workflow_run_created ON workflow_run (created_at);
CREATE INDEX audit_event_created ON audit_event (created_at);
CREATE INDEX usage_event_created ON usage_event (created_at);
CREATE INDEX publication_analysis ON publication (analysis_id);
CREATE INDEX installation_purge_due ON installation (purge_after) WHERE status = 'deleted' AND purged_at IS NULL;

CREATE FUNCTION tracewise_purge(batch_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    n integer := LEAST(GREATEST(COALESCE(batch_limit, 1), 1), 10000);
    c integer;
    total integer;
    r jsonb := '{}'::jsonb;
    more boolean := false;
    ids bigint[];
    inst bigint;
BEGIN
    IF NOT pg_try_advisory_xact_lock(7472616365) THEN  -- 'trace' — one purger at a time
        RETURN jsonb_build_object('locked', true, 'more', true);
    END IF;

    -- 1. Excerpts: 90 days (the diagnosis document holds them).
    UPDATE analysis SET diagnosis = NULL, content_purged_at = now()
     WHERE id IN (SELECT id FROM analysis WHERE diagnosis IS NOT NULL AND updated_at < now() - interval '90 days'
                  ORDER BY id LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('analysis_content', c); more := more OR c = n;

    -- 2. Analyses: 180 days, with their publications; usage keeps its own retention (detached).
    SELECT array_agg(id) INTO ids FROM (SELECT id FROM analysis WHERE updated_at < now() - interval '180 days'
                                        ORDER BY id LIMIT n) s;
    ids := COALESCE(ids, '{}');
    DELETE FROM publication WHERE analysis_id = ANY (ids);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('publication', c);
    UPDATE usage_event SET analysis_id = NULL WHERE analysis_id = ANY (ids);
    DELETE FROM analysis WHERE id = ANY (ids);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('analysis', c); more := more OR c = n;

    -- 3. Deliveries: 14 days.
    DELETE FROM webhook_delivery WHERE delivery_id IN (
        SELECT delivery_id FROM webhook_delivery WHERE received_at < now() - interval '14 days' LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('webhook_delivery', c); more := more OR c = n;

    -- 4. Fingerprints: 365 days since last seen.
    DELETE FROM failure_signature WHERE (repo_id, fingerprint) IN (
        SELECT repo_id, fingerprint FROM failure_signature WHERE last_seen_at < now() - interval '365 days' LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('failure_signature', c); more := more OR c = n;

    -- 5. Runs: 365 days, once unreferenced.
    DELETE FROM workflow_run WHERE id IN (
        SELECT w.id FROM workflow_run w WHERE w.created_at < now() - interval '365 days'
           AND NOT EXISTS (SELECT 1 FROM analysis a WHERE a.run_pk = w.id) LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('workflow_run', c); more := more OR c = n;

    -- 6. Jobs: terminal only, 365 days after finishing.
    DELETE FROM job WHERE id IN (
        SELECT id FROM job WHERE status IN ('succeeded', 'dead', 'cancelled') AND finished_at < now() - interval '365 days'
        LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('job', c); more := more OR c = n;

    -- 7. Usage, audit, redelivery bookkeeping: 365 days.
    DELETE FROM usage_event WHERE id IN (SELECT id FROM usage_event WHERE created_at < now() - interval '365 days' LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('usage_event', c); more := more OR c = n;
    DELETE FROM audit_event WHERE id IN (SELECT id FROM audit_event WHERE created_at < now() - interval '365 days' LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('audit_event', c); more := more OR c = n;
    DELETE FROM redelivery_request WHERE guid IN (
        SELECT guid FROM redelivery_request WHERE last_requested_at < now() - interval '365 days' LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('redelivery_request', c); more := more OR c = n;

    -- 8. Tenant purge: one due installation per call, bounded per table, FK order.
    SELECT count(*) INTO c FROM installation WHERE status = 'deleted' AND purge_after IS NULL AND purged_at IS NULL;
    r := r || jsonb_build_object('tenants_without_purge_after', c);
    SELECT count(*) INTO c FROM installation i WHERE i.status = 'deleted' AND i.purge_after <= now() AND i.purged_at IS NULL
       AND EXISTS (SELECT 1 FROM job j WHERE j.installation_id = i.id AND j.status IN ('queued', 'running', 'retry_wait'));
    r := r || jsonb_build_object('tenants_waiting_for_jobs', c);
    SELECT i.id INTO inst FROM installation i
     WHERE i.status = 'deleted' AND i.purge_after <= now() AND i.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM job j WHERE j.installation_id = i.id AND j.status IN ('queued', 'running', 'retry_wait'))
     ORDER BY i.purge_after, i.id LIMIT 1 FOR UPDATE;
    IF inst IS NOT NULL THEN
        total := 0;
        DELETE FROM publication WHERE id IN (SELECT id FROM publication WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM usage_event WHERE id IN (SELECT id FROM usage_event WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM analysis WHERE id IN (
            SELECT a.id FROM analysis a WHERE a.installation_id = inst
               AND NOT EXISTS (SELECT 1 FROM publication p WHERE p.analysis_id = a.id)
               AND NOT EXISTS (SELECT 1 FROM usage_event u WHERE u.analysis_id = a.id) LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM workflow_run WHERE id IN (
            SELECT w.id FROM workflow_run w WHERE w.installation_id = inst
               AND NOT EXISTS (SELECT 1 FROM analysis a WHERE a.run_pk = w.id) LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM failure_signature WHERE (repo_id, fingerprint) IN (
            SELECT repo_id, fingerprint FROM failure_signature WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM job WHERE id IN (SELECT id FROM job WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM webhook_delivery WHERE delivery_id IN (
            SELECT delivery_id FROM webhook_delivery WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM redelivery_request WHERE guid IN (SELECT guid FROM redelivery_request WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        DELETE FROM repository WHERE id IN (SELECT id FROM repository WHERE installation_id = inst LIMIT n);
        GET DIAGNOSTICS c = ROW_COUNT; total := total + c;
        r := r || jsonb_build_object('tenant', inst, 'tenant_rows', total);
        IF total = 0 THEN
            UPDATE installation SET purged_at = now(), account_login = NULL WHERE id = inst;
            INSERT INTO audit_event (installation_id, actor, action, detail)
                 VALUES (inst, 'system', 'tenant_purged',
                         jsonb_build_object('purge_after', (SELECT purge_after FROM installation WHERE id = inst)));
            r := r || jsonb_build_object('tenant_purged', inst);
        END IF;
        more := true;  -- another due installation, or more rows of this one, may remain
    END IF;
    RETURN r || jsonb_build_object('more', more, 'batch_limit', n);
END $$;
REVOKE ALL ON FUNCTION tracewise_purge(integer) FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_system') THEN
        GRANT EXECUTE ON FUNCTION tracewise_purge(integer) TO tracewise_system;
    END IF;
END $$;
"""

DOWN = """
DROP FUNCTION IF EXISTS tracewise_purge(integer);
DROP INDEX IF EXISTS installation_purge_due;
DROP INDEX IF EXISTS publication_analysis;
DROP INDEX IF EXISTS usage_event_created;
DROP INDEX IF EXISTS audit_event_created;
DROP INDEX IF EXISTS workflow_run_created;
DROP INDEX IF EXISTS failure_signature_last_seen;
DROP INDEX IF EXISTS job_finished;
DROP INDEX IF EXISTS analysis_updated;
ALTER TABLE analysis DROP COLUMN IF EXISTS content_purged_at;
ALTER TABLE installation DROP COLUMN IF EXISTS purged_at;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
