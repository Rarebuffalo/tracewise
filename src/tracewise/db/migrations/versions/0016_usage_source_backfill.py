"""Backfill `analysis.usage_source = 'no_call'` for rows written before 0014, where the code proves no model was asked.

A legacy row has `usage_source IS NULL` and token totals of 0. Zero does not prove "no call" (a provider can report 0,
or a failed first step spends unknown tokens), so only these facts, each guaranteed by the code that wrote the row,
mark a row as `no_call`:

* `provider = 'none'`: `finalize` received no investigation result at all (the evidence was not `ok`, or the
  attempt deadline left no time to start). `investigate()` was never entered;
* `status IN ('logs_unavailable', 'permission_denied')`: decided before any investigation;
* `diagnosis->>'inconclusive_reason' = 'no_error_line'`: the loop returns before its first provider step. This needs
  the diagnosis document, which the purge clears after 90 days; rows without it stay unknown.

Every other legacy row keeps `usage_source` NULL ("no measurement record"). That includes the "could not complete"
notices, whose provider steps, if any, were not recorded. The totals are not touched. One bounded UPDATE of a
metadata column; the subset constraint of 0014 holds, because no subsets are set. Downgrade leaves the values: they
are true either way, and 0014's downgrade drops the column.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UP = """
UPDATE analysis SET usage_source = 'no_call'
 WHERE usage_source IS NULL
   AND cached_input_tokens IS NULL AND reasoning_output_tokens IS NULL
   AND coalesce(tokens_in, 0) = 0 AND coalesce(tokens_out, 0) = 0
   AND (provider = 'none'
        OR status IN ('logs_unavailable', 'permission_denied')
        OR diagnosis->>'inconclusive_reason' = 'no_error_line');
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    pass  # see the docstring: the backfilled values stay true
