"""Installation lifecycle outcomes (T-701; FS-INS-3, FS-INS-4, AT-INS-04).

Extends `webhook_delivery.outcome` so lifecycle processing and scope refusals are recorded explicitly:
`processed` (a lifecycle event was applied), `repo_not_in_scope` (repository removed from the
installation), `repo_disabled` (disabled in Tracewise), `installation_inactive` (suspended/deleted).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE webhook_delivery DROP CONSTRAINT webhook_delivery_outcome_check;
ALTER TABLE webhook_delivery ADD CONSTRAINT webhook_delivery_outcome_check CHECK (outcome IN (
    'enqueued', 'duplicate_run', 'ignored', 'rejected', 'processed', 'repo_not_in_scope', 'repo_disabled',
    'installation_inactive'));
CREATE INDEX job_pending_installation ON job (installation_id) WHERE status IN ('queued', 'retry_wait');
"""

DOWN = """
DROP INDEX IF EXISTS job_pending_installation;
UPDATE webhook_delivery SET outcome = 'ignored'
    WHERE outcome NOT IN ('enqueued', 'duplicate_run', 'ignored', 'rejected');
ALTER TABLE webhook_delivery DROP CONSTRAINT webhook_delivery_outcome_check;
ALTER TABLE webhook_delivery ADD CONSTRAINT webhook_delivery_outcome_check
    CHECK (outcome IN ('enqueued', 'duplicate_run', 'ignored', 'rejected'));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
