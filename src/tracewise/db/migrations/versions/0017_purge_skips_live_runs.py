"""Retention purge: never touch the data of a run that has a live job (D-12 verification, fifth batch).

`tracewise_purge` (0008, search path 0009) cleared excerpts after 90 days, deleted analyses and their publications
after 180 days, and deleted unreferenced runs after 365 days. It did so even when a queued, waiting or running job
existed for the same run, for example an operator requeue of an old run (0013). The publication rows a running
attempt reconciles against could disappear mid-attempt. Reconcile-before-create still prevented a duplicate, but a
running attempt must not lose its data. Each of those three steps now skips runs with a live job (matched on
`job.run_key = '<repo_id>:<run_id>'`, as written by ingest); they are picked up by a later run once the job ends.

Everything else is unchanged: the periods, batch bounds, advisory try-lock, tenant purge, owner, SECURITY DEFINER
and the system role's EXECUTE grant. CREATE OR REPLACE keeps the owner and grants. A partial index keeps the
live-job lookup bounded. Downgrade restores the 0008/0009 body exactly.

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UP = r"""
CREATE INDEX job_live_run ON job (run_key) WHERE status IN ('queued', 'retry_wait', 'running');
CREATE OR REPLACE FUNCTION tracewise_purge(batch_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
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
    -- (0017) Never the analysis of a run with a live job: a running or queued attempt may still read or rewrite it.
    UPDATE analysis SET diagnosis = NULL, content_purged_at = now()
     WHERE id IN (SELECT a.id FROM analysis a JOIN workflow_run w ON w.id = a.run_pk
                   WHERE a.diagnosis IS NOT NULL AND a.updated_at < now() - interval '90 days'
                     AND NOT EXISTS (SELECT 1 FROM job j WHERE j.run_key = w.repo_id || ':' || w.github_run_id
                                AND j.status IN ('queued', 'running', 'retry_wait'))
                   ORDER BY a.id LIMIT n);
    GET DIAGNOSTICS c = ROW_COUNT; r := r || jsonb_build_object('analysis_content', c); more := more OR c = n;

    -- 2. Analyses: 180 days, with their publications; usage keeps its own retention (detached).
    SELECT array_agg(id) INTO ids FROM (SELECT a.id FROM analysis a JOIN workflow_run w ON w.id = a.run_pk
                                         WHERE a.updated_at < now() - interval '180 days'
                                           AND NOT EXISTS (SELECT 1 FROM job j
                                                            WHERE j.run_key = w.repo_id || ':' || w.github_run_id
                                                              AND j.status IN ('queued', 'running', 'retry_wait'))
                                         ORDER BY a.id LIMIT n) s;
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
           AND NOT EXISTS (SELECT 1 FROM analysis a WHERE a.run_pk = w.id)
           AND NOT EXISTS (SELECT 1 FROM job j WHERE j.run_key = w.repo_id || ':' || w.github_run_id
                                AND j.status IN ('queued', 'running', 'retry_wait')) LIMIT n);
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
"""

DOWN = r"""
CREATE OR REPLACE FUNCTION tracewise_purge(batch_limit integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
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
DROP INDEX IF EXISTS job_live_run;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
