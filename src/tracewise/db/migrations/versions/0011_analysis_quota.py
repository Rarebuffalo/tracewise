"""Analysis quota (T-703, FS-QTA-1): an analysis row may record that a run was over the installation's monthly quota.

The status `quota_exceeded` marks a run that was NOT investigated because the quota was used up; it lets the
publisher reuse its idempotent Check Run path for the one "quota reached" notice per repository per day, and lets
the gate see whether today's notice already exists. Quota-exceeded rows never count towards the quota.

An index on (installation_id, created_at) serves the monthly count. The downgrade refuses while any
`quota_exceeded` row exists rather than deleting data.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE analysis DROP CONSTRAINT analysis_status_check;
ALTER TABLE analysis ADD CONSTRAINT analysis_status_check CHECK (status IN (
    'diagnosed', 'inconclusive', 'logs_unavailable', 'permission_denied', 'could_not_complete', 'quota_exceeded'));
CREATE INDEX analysis_installation_created ON analysis (installation_id, created_at);
"""

DOWN = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM analysis WHERE status = 'quota_exceeded') THEN
        RAISE EXCEPTION 'downgrade 0011 refused: analysis rows with status quota_exceeded exist'
            USING ERRCODE = 'check_violation';
    END IF;
END $$;
DROP INDEX analysis_installation_created;
ALTER TABLE analysis DROP CONSTRAINT analysis_status_check;
ALTER TABLE analysis ADD CONSTRAINT analysis_status_check CHECK (status IN (
    'diagnosed', 'inconclusive', 'logs_unavailable', 'permission_denied', 'could_not_complete'));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
