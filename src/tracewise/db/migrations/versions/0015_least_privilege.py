"""D-11 option C: least privilege for the runtime roles, derived from the SQL each process actually runs.

Tenant plane (`tracewise_app`, RLS): the analyze handler and publisher only. It reads `installation` and `repository`
(scope and re-checks) and reads/writes `workflow_run`, `analysis` and `publication`. Job ownership is asked through
`tracewise_job_owned` (SECURITY DEFINER, 0012), never through job-table rights. Everything else is revoked:
  * `job`, `webhook_delivery`, `usage_event`, `failure_signature`: all (a tenant-plane bug could squat another
    tenant's predictable dedupe key, fake a running job, or erase its own intake and job history);
  * `audit_event`: all (a tenant could forge its own audit rows; the system plane and definer functions write it);
  * `installation`, `repository`: INSERT and UPDATE (a tenant could un-delete itself or move its purge date);
  * `alembic_version`: SELECT (the schema check runs on the system plane only: worker and preflight);
  * sequences other than those of `workflow_run`, `analysis` and `publication`.
System plane (`tracewise_system`): DELETE on `job`, `webhook_delivery`, `usage_event`, `failure_signature` is revoked.
No runtime code deletes from a Tracewise table; the retention purge deletes as the definer (0008).

Unchanged: RLS policies, the definer functions and their EXECUTE grants (purge, job fence, requeue), every system-role
SELECT/INSERT/UPDATE. Downgrade restores exactly the grants of 0001 and 0005. Roles that do not exist are skipped.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UP = """
DO $$
DECLARE s record;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        REVOKE ALL ON job, webhook_delivery, usage_event, failure_signature, audit_event, alembic_version
            FROM tracewise_app;
        REVOKE INSERT, UPDATE ON installation, repository FROM tracewise_app;
        FOR s IN SELECT c.relname FROM pg_class c
                  WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
                    AND c.relname NOT IN ('workflow_run_id_seq', 'analysis_id_seq', 'publication_id_seq')
        LOOP
            EXECUTE format('REVOKE ALL ON SEQUENCE %I FROM tracewise_app', s.relname);
        END LOOP;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_system') THEN
        REVOKE DELETE ON job, webhook_delivery, usage_event, failure_signature FROM tracewise_system;
    END IF;
END $$;
"""

DOWN = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        GRANT SELECT, INSERT, UPDATE ON job, webhook_delivery, usage_event, failure_signature, installation, repository
            TO tracewise_app;
        GRANT DELETE ON job, webhook_delivery, usage_event, failure_signature TO tracewise_app;
        GRANT SELECT, INSERT ON audit_event TO tracewise_app;
        GRANT SELECT ON alembic_version TO tracewise_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tracewise_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_system') THEN
        GRANT DELETE ON job, webhook_delivery, usage_event, failure_signature TO tracewise_system;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
