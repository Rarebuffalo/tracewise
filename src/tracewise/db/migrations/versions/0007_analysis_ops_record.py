"""Per-analysis operational record (T-706; FS-OPS-1, AT-OPS-01).

`analysis` already holds tokens_in/tokens_out, cost_usd, latency_ms (model time) and status (outcome).
This adds the stage timings and the publish result, both small JSON objects of identifiers and numbers
only (no content): `stage_ms` {stage: ms} and `publish_result` {surface: state}.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE analysis
    ADD COLUMN stage_ms jsonb
        CHECK (stage_ms IS NULL OR (jsonb_typeof(stage_ms) = 'object' AND pg_column_size(stage_ms) <= 2048)),
    ADD COLUMN publish_result jsonb
        CHECK (publish_result IS NULL OR (jsonb_typeof(publish_result) = 'object' AND pg_column_size(publish_result) <= 2048)),
    ADD COLUMN finished_at timestamptz;
CREATE INDEX analysis_created ON analysis (created_at);
"""

DOWN = """
DROP INDEX IF EXISTS analysis_created;
ALTER TABLE analysis DROP COLUMN IF EXISTS stage_ms, DROP COLUMN IF EXISTS publish_result, DROP COLUMN IF EXISTS finished_at;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
