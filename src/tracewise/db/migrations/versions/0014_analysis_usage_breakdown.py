"""Usage breakdown on `analysis` (D-12 part 2, option A of the decision note): nullable, additive.

* `cached_input_tokens`: cached input, part of `tokens_in`; NULL = the provider did not report it (never 0).
* `reasoning_output_tokens`: reasoning ("thinking") output, part of `tokens_out`; NULL = not reported.
* `usage_source`: `no_call` (no provider request: the totals are genuinely 0), `provider` (every step reported its
  usage), `partial` (a step failed: its usage, if any was spent, is unknown, so the totals are a lower bound).
  NULL = a row written before this revision, or a notice without any investigation: no measurement record.

Only provider-reported counts are stored; no raw provider payload. The columns inherit the analysis row's
retention step (180 days, `tracewise_purge`), its RLS policy and its table grants (no column grants). Adding
nullable columns rewrites nothing. Downgrade drops them.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE analysis
    ADD COLUMN cached_input_tokens integer,
    ADD COLUMN reasoning_output_tokens integer,
    ADD COLUMN usage_source text CHECK (usage_source IN ('no_call', 'provider', 'partial')),
    ADD CONSTRAINT analysis_usage_subsets CHECK (
        (cached_input_tokens IS NULL OR (tokens_in IS NOT NULL AND cached_input_tokens BETWEEN 0 AND tokens_in))
        AND (reasoning_output_tokens IS NULL
             OR (tokens_out IS NOT NULL AND reasoning_output_tokens BETWEEN 0 AND tokens_out))
        AND (usage_source IS DISTINCT FROM 'no_call'
             OR (cached_input_tokens IS NULL AND reasoning_output_tokens IS NULL)));
"""

DOWN = """
ALTER TABLE analysis
    DROP CONSTRAINT IF EXISTS analysis_usage_subsets,
    DROP COLUMN IF EXISTS usage_source,
    DROP COLUMN IF EXISTS reasoning_output_tokens,
    DROP COLUMN IF EXISTS cached_input_tokens;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
