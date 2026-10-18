"""Harden the SECURITY DEFINER purge function's name resolution (Phase 11 audit, finding SA-5).

0008 set `search_path = pg_catalog, public`. When `pg_temp` is not listed, PostgreSQL searches the caller's
temporary schema FIRST for tables. A caller allowed to execute the function (tracewise_system) could create
temporary `installation`/`job` tables and steer the owner-privileged purge onto an active tenant's real rows.
This pins `pg_temp` last, so unqualified names always resolve to the real tables.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UP = "ALTER FUNCTION tracewise_purge(integer) SET search_path = pg_catalog, public, pg_temp;"
DOWN = "ALTER FUNCTION tracewise_purge(integer) SET search_path = pg_catalog, public;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
