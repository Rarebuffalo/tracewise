"""Row-level security (T-705; FS-SEC-6, AT-SEC-03, ADR-05).

Tenant = installation. Every tenant-owned table gets RLS with one policy for all non-owner, non-BYPASSRLS
roles: rows are visible and writable only when their installation equals the transaction-local tenant
context `tracewise.installation_id` (set with `set_config(..., true)`). No context (or an empty one) →
`tracewise_tenant()` is NULL → nothing matches: fail closed. A non-numeric context raises an error.

Roles (provisioned outside migrations; tests create them):
* `tracewise_app`    tenant plane (analysis, publication). No BYPASSRLS, not the owner → always restricted.
* `tracewise_system` system plane (webhook ingress, lifecycle, queue claiming, recovery sweeps), which handles
  GitHub-authenticated identifiers across installations. Must be created WITH BYPASSRLS. Gets DML grants here.
* the migration owner is not restricted (no FORCE), as migrations need full access.
The recovery tables are system-plane only: the tenant role loses access to them.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UP = """
CREATE FUNCTION tracewise_tenant() RETURNS bigint LANGUAGE sql STABLE PARALLEL SAFE AS
$$ SELECT NULLIF(current_setting('tracewise.installation_id', true), '')::bigint $$;

ALTER TABLE installation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON installation USING (id = tracewise_tenant()) WITH CHECK (id = tracewise_tenant());

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['repository', 'workflow_run', 'job', 'analysis', 'publication', 'failure_signature',
                             'usage_event', 'audit_event', 'webhook_delivery'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (installation_id = tracewise_tenant()) '
                       'WITH CHECK (installation_id = tracewise_tenant())', t);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_system') THEN
        GRANT USAGE ON SCHEMA public TO tracewise_system;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO tracewise_system;
        GRANT DELETE ON webhook_delivery, job, usage_event, failure_signature TO tracewise_system;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tracewise_system;
        REVOKE UPDATE, DELETE ON audit_event FROM tracewise_system;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        REVOKE ALL ON recovery_checkpoint, redelivery_request FROM tracewise_app;
    END IF;
END $$;
"""

DOWN = """
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['installation', 'repository', 'workflow_run', 'job', 'analysis', 'publication',
                             'failure_signature', 'usage_event', 'audit_event', 'webhook_delivery'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t);
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        GRANT SELECT, INSERT, UPDATE ON recovery_checkpoint, redelivery_request TO tracewise_app;
    END IF;
END $$;
DROP FUNCTION IF EXISTS tracewise_tenant();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
