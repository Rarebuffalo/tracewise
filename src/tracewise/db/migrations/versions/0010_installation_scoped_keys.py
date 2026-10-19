"""Scope run, publication and failure-signature uniqueness to the installation (Phase 50, repository transfer).

A repository can move to another installation (GitHub transfer → `installation_repositories` added under the new
installation). The old keys were global, (repo, run, attempt) and (surface, target_key) and (repo, fingerprint), so
the new tenant's first write for the same PR, commit or run collided with the old tenant's row, which RLS hides from
it. `INSERT … ON CONFLICT` then either did nothing (and the following lookup found no visible row) or tried to
update an invisible row (RLS USING violation). The job retried and went `dead`.

Each key now includes `installation_id`, which every one of these tenant tables already carries and on which RLS
filters. Existing rows keep their installation, and nothing is rewritten. The new keys are strictly looser than the
old ones (a superset of the columns), so the upgrade cannot meet a duplicate. A downgrade can: if two installations
hold the same old key, it refuses with an explanation and never deletes data to make room.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE workflow_run DROP CONSTRAINT workflow_run_repo_id_github_run_id_run_attempt_key;
ALTER TABLE workflow_run ADD CONSTRAINT workflow_run_installation_run_key
    UNIQUE (installation_id, repo_id, github_run_id, run_attempt);

ALTER TABLE publication DROP CONSTRAINT publication_surface_target_key_key;
ALTER TABLE publication ADD CONSTRAINT publication_installation_target_key
    UNIQUE (installation_id, surface, target_key);

ALTER TABLE failure_signature DROP CONSTRAINT failure_signature_pkey;
ALTER TABLE failure_signature ADD CONSTRAINT failure_signature_pkey PRIMARY KEY (installation_id, repo_id, fingerprint);
"""

# Refuse rather than delete: each check names the table whose old global key is no longer unique.
DOWN_GUARD = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM workflow_run GROUP BY repo_id, github_run_id, run_attempt HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'downgrade 0010 refused: workflow_run holds the same (repo, run, attempt) under two installations'
            USING ERRCODE = 'unique_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM publication GROUP BY surface, target_key HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'downgrade 0010 refused: publication holds the same (surface, target) under two installations'
            USING ERRCODE = 'unique_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM failure_signature GROUP BY repo_id, fingerprint HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'downgrade 0010 refused: failure_signature holds the same (repo, fingerprint) under two installations'
            USING ERRCODE = 'unique_violation';
    END IF;
END $$;
"""

DOWN = """
ALTER TABLE failure_signature DROP CONSTRAINT failure_signature_pkey;
ALTER TABLE failure_signature ADD CONSTRAINT failure_signature_pkey PRIMARY KEY (repo_id, fingerprint);

ALTER TABLE publication DROP CONSTRAINT publication_installation_target_key;
ALTER TABLE publication ADD CONSTRAINT publication_surface_target_key_key UNIQUE (surface, target_key);

ALTER TABLE workflow_run DROP CONSTRAINT workflow_run_installation_run_key;
ALTER TABLE workflow_run ADD CONSTRAINT workflow_run_repo_id_github_run_id_run_attempt_key
    UNIQUE (repo_id, github_run_id, run_attempt);
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN_GUARD)
    op.execute(DOWN)
