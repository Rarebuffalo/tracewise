"""Operator-attributed requeue (I-6 hardening): the audit actor is the authenticated database login, not a typed name.

`tracewise_requeue(job_id, reason, dry_run)` performs the whole re-run of one dead analysis job in the caller's
transaction: authorisation, every refusal, the per-run advisory lock, the new job row and its `audit_event`. The
job row and the audit row therefore commit together or not at all.

Identity. The actor is `operator:<session_user>`. `session_user` is the role PostgreSQL authenticated for this
connection (password, certificate or IAM: a deployment decision); `SET ROLE` does not change it, and only a superuser
can `SET SESSION AUTHORIZATION`. A typed handle can no longer be recorded.

Authorisation. EXECUTE is granted only to the NOLOGIN group `tracewise_operator` (created by
`scripts/db/provision_roles.sql`; each person gets their own LOGIN role IN ROLE tracewise_operator). The function
refuses, before reading anything, a caller that is not a member, a superuser, or one of the shared service roles
(owner, tenant, system): those are credentials of processes, not of people. A refusal says nothing about the job.

Limit. `tracewise_requeue_max_reruns()` returns it (default 2, provisional). It is a plain SQL function owned by the
schema owner: no session setting can influence it, and only the owner can change it, by replacing the function
(`CREATE OR REPLACE FUNCTION tracewise_requeue_max_reruns() ... SELECT 3`, normally a reviewed migration), which is
visible in the catalogue. The value in force is written into every audit record. Values outside 0..10 are refused.
(A custom setting on the function's SET clause was the first design; a non-superuser owner may not create one.)

SECURITY DEFINER (owner rights, fixed search_path, PUBLIC revoked), like `tracewise_purge` and
`tracewise_job_owned`. Additive: no grant on any table changes. Downgrade drops the function.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UP = """
CREATE FUNCTION tracewise_requeue_max_reruns() RETURNS integer LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog AS $$ SELECT 2 $$;
REVOKE ALL ON FUNCTION tracewise_requeue_max_reruns() FROM PUBLIC;

CREATE FUNCTION tracewise_requeue(p_job_id bigint, p_reason text, p_dry_run boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    who      name := session_user;
    actor    text := 'operator:' || session_user;
    max_r    integer;
    j        job%ROWTYPE;
    base     text;
    done     integer;
    k        integer;
    new_id   bigint;
BEGIN
    -- 1. Who is asking, before anything is read: refusals carry no job information.
    IF NOT pg_has_role(who, 'tracewise_operator', 'MEMBER')
       OR who IN ('tracewise_owner', 'tracewise_app', 'tracewise_system')
       OR (SELECT rolsuper FROM pg_roles WHERE rolname = who) THEN
        RAISE EXCEPTION 'requeue requires a personal login in tracewise_operator' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_reason IS NULL
       OR p_reason NOT IN ('transient_outage', 'fixed_configuration', 'fixed_permission', 'operator_request') THEN
        RAISE EXCEPTION 'unknown requeue reason' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    max_r := tracewise_requeue_max_reruns();
    IF max_r IS NULL OR max_r < 0 OR max_r > 10 THEN
        RAISE EXCEPTION 'tracewise_requeue_max_reruns() must be between 0 and 10' USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- 2. The job, locked; every refusal leaves the database unchanged.
    SELECT * INTO j FROM job WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'not_found', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    IF j.status <> 'dead' THEN
        RETURN jsonb_build_object('outcome', 'not_dead', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    IF j.kind <> 'analyze' THEN
        RETURN jsonb_build_object('outcome', 'unsupported_kind', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    base := split_part(j.dedupe_key, ':rerun:', 1);
    PERFORM pg_advisory_xact_lock(hashtextextended('requeue:' || base, 0));  -- one requeue per run at a time
    IF NOT EXISTS (SELECT 1 FROM installation WHERE id = j.installation_id AND status = 'active') THEN
        RETURN jsonb_build_object('outcome', 'installation_inactive', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM repository r
         WHERE r.id = CASE WHEN jsonb_typeof(j.payload -> 'repo_id') = 'number' THEN (j.payload ->> 'repo_id')::bigint END
           AND r.installation_id = j.installation_id AND r.enabled AND r.removed_at IS NULL
    ) THEN
        RETURN jsonb_build_object('outcome', 'repository_unavailable', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    IF j.run_key IS NOT NULL AND EXISTS (
        SELECT 1 FROM job WHERE run_key = j.run_key AND status IN ('queued', 'retry_wait', 'running')
    ) THEN
        RETURN jsonb_build_object('outcome', 'live_job_exists', 'job_id', p_job_id, 'actor', actor, 'max_reruns', max_r);
    END IF;
    SELECT count(*) INTO done FROM job WHERE starts_with(dedupe_key, base || ':rerun:');
    k := done + 1;
    IF k > max_r THEN
        RETURN jsonb_build_object('outcome', 'rerun_limit', 'job_id', p_job_id, 'rerun', done, 'actor', actor,
                                  'max_reruns', max_r);
    END IF;
    IF p_dry_run THEN
        RETURN jsonb_build_object('outcome', 'would_requeue', 'job_id', p_job_id, 'rerun', k, 'actor', actor,
                                  'max_reruns', max_r);
    END IF;

    -- 3. The new attempt and its audit record, in this one transaction.
    INSERT INTO job (kind, installation_id, run_key, dedupe_key, payload, max_attempts, run_after)
    VALUES ('analyze', j.installation_id, j.run_key, base || ':rerun:' || k, j.payload, j.max_attempts, now())
    RETURNING id INTO new_id;
    INSERT INTO audit_event (installation_id, actor, action, detail)
    VALUES (j.installation_id, actor, 'job.requeued',
            jsonb_build_object('source_job_id', p_job_id, 'new_job_id', new_id, 'reason', p_reason, 'rerun', k,
                               'max_reruns', max_r));
    RETURN jsonb_build_object('outcome', 'requeued', 'job_id', p_job_id, 'new_job_id', new_id, 'rerun', k,
                              'actor', actor, 'max_reruns', max_r);
END $$;
REVOKE ALL ON FUNCTION tracewise_requeue(bigint, text, boolean) FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_operator') THEN
        GRANT EXECUTE ON FUNCTION tracewise_requeue(bigint, text, boolean) TO tracewise_operator;
    END IF;
END $$;
"""

DOWN = """
DROP FUNCTION IF EXISTS tracewise_requeue(bigint, text, boolean);
DROP FUNCTION IF EXISTS tracewise_requeue_max_reruns();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
