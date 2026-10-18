"""Recovery state (T-702; FS-EVT-5, AT-REL-03).

* `recovery_checkpoint`: durable cursors/high-water marks for the redelivery scan and the failed-run sweep.
  A value only advances after the step it covers completed, so an interrupted run resumes without skipping.
* `redelivery_request`: one row per GitHub delivery GUID we asked GitHub to redeliver, with a capped attempt
  count, so repeated scans never spam the redelivery endpoint.
Both are system tables (no tenant content).

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE recovery_checkpoint (
    key         text PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 100),
    value       text NOT NULL CHECK (length(value) <= 200),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE redelivery_request (
    guid                text PRIMARY KEY CHECK (length(guid) BETWEEN 1 AND 200),
    github_delivery_id  bigint NOT NULL,
    installation_id     bigint,
    event               text NOT NULL,
    attempts            integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_requested_at   timestamptz,
    last_status         text CHECK (length(last_status) <= 100)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        GRANT SELECT, INSERT, UPDATE ON recovery_checkpoint, redelivery_request TO tracewise_app;
    END IF;
END $$;
"""

DOWN = "DROP TABLE IF EXISTS redelivery_request, recovery_checkpoint;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
