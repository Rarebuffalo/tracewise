"""Publication state for idempotent, reconciling publishers (T-502/T-503).

Adds what the publishers need and the 0001 schema cannot represent:
* `unpublished_permission` state + `missing_permission` (FS-PUB-5, FS-ERR-3);
* `source_run_id` / `source_attempt`: which run attempt last wrote the surface, so an older attempt
  finishing late can never overwrite a newer result;
* `content_digest`: skip a no-op re-publish of identical content.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE publication
    ADD COLUMN source_run_id bigint,
    ADD COLUMN source_attempt integer CHECK (source_attempt >= 1),
    ADD COLUMN content_digest char(64) CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    ADD COLUMN missing_permission text CHECK (length(missing_permission) <= 100);
ALTER TABLE publication DROP CONSTRAINT publication_state_check;
ALTER TABLE publication ADD CONSTRAINT publication_state_check
    CHECK (state IN ('pending', 'published', 'failed', 'skipped', 'unpublished_permission'));
"""

DOWN = """
UPDATE publication SET state = 'failed', last_error = 'unpublished_permission' WHERE state = 'unpublished_permission';
ALTER TABLE publication DROP CONSTRAINT publication_state_check;
ALTER TABLE publication ADD CONSTRAINT publication_state_check
    CHECK (state IN ('pending', 'published', 'failed', 'skipped'));
ALTER TABLE publication DROP COLUMN missing_permission, DROP COLUMN content_digest,
    DROP COLUMN source_attempt, DROP COLUMN source_run_id;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
