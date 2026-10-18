"""Runtime roles may not write the migration version (security audit 2026-10-19).

0001 granted INSERT/UPDATE on ALL TABLES to the runtime role, which included `alembic_version`, and 0005
copied that to `tracewise_system`. A runtime role could therefore change the recorded schema revision, so a
later `alembic upgrade` would skip or re-apply migrations (for example, the RLS migration). Only the
migration owner needs to write it. SELECT is kept (harmless; useful for a read-only version check).

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UP = """
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['tracewise_app', 'tracewise_system'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""

DOWN = """
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['tracewise_app', 'tracewise_system'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('GRANT INSERT, UPDATE ON alembic_version TO %I', r);
        END IF;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
