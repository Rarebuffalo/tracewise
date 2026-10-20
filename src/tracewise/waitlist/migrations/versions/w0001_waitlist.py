"""Waitlist schema: signups, verification tokens, email outbox, rate-limit windows and the public aggregate.

Isolation: everything lives in schema `waitlist`. The runtime role `tracewise_waitlist` (if it exists; created by
`scripts/db/provision_waitlist_role.sql`) gets table rights here and nothing anywhere else. The product roles get
nothing here.

Revision ID: w0001
Revises:
"""

from alembic import op

revision = "w0001"
down_revision = None
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE waitlist.signup (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text NOT NULL CHECK (char_length(email) BETWEEN 3 AND 254),
    email_normalized    text NOT NULL CHECK (email_normalized = lower(btrim(email))),
    status              text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed')),
    github_login        text CHECK (github_login ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}$'),
    ci_failure_freq     text CHECK (ci_failure_freq IN ('daily', 'weekly', 'monthly', 'rarely')),
    updates_consent     boolean NOT NULL DEFAULT false,
    updates_consent_at  timestamptz,
    consent_version     text NOT NULL CHECK (char_length(consent_version) <= 40),
    disposable_domain   boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    confirmed_at        timestamptz,
    last_verify_sent_at timestamptz,
    CONSTRAINT signup_email_normalized_key UNIQUE (email_normalized),
    CONSTRAINT signup_status_matches_confirmed CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL)),
    CONSTRAINT signup_consent_has_time CHECK (updates_consent = (updates_consent_at IS NOT NULL))
);
CREATE INDEX signup_confirmed_idx ON waitlist.signup (confirmed_at) WHERE status = 'confirmed';
CREATE INDEX signup_pending_created_idx ON waitlist.signup (created_at) WHERE status = 'pending';

-- Verification tokens: only the SHA-256 is stored. Several may be live at once (a resend never invalidates the
-- link in an earlier email); confirming marks them all used.
CREATE TABLE waitlist.verify_token (
    token_hash  bytea PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    signup_id   uuid NOT NULL REFERENCES waitlist.signup (id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);
CREATE INDEX verify_token_signup_idx ON waitlist.verify_token (signup_id);

-- Transactional outbox for every email (verification and owner notification). Rows are written in the same
-- transaction as the state change they announce, then sent; failures are retried with backoff.
CREATE TABLE waitlist.email_outbox (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    signup_id           uuid NOT NULL REFERENCES waitlist.signup (id) ON DELETE CASCADE,
    kind                text NOT NULL CHECK (kind IN ('verify', 'owner_notify')),
    status              text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')),
    attempts            integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at     timestamptz NOT NULL DEFAULT now(),
    lease_until         timestamptz,
    provider            text CHECK (provider IN ('resend', 'file')),
    provider_message_id text CHECK (char_length(provider_message_id) <= 200),
    last_error          text CHECK (char_length(last_error) <= 500),
    payload             jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    sent_at             timestamptz,
    CONSTRAINT outbox_sent_has_time CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);
-- At most one owner notification per signup, ever; at most one open verification email per signup.
CREATE UNIQUE INDEX outbox_one_owner_notify ON waitlist.email_outbox (signup_id) WHERE kind = 'owner_notify';
CREATE UNIQUE INDEX outbox_one_open_verify ON waitlist.email_outbox (signup_id)
    WHERE kind = 'verify' AND status IN ('pending', 'sending');
CREATE INDEX outbox_due_idx ON waitlist.email_outbox (next_attempt_at) WHERE status IN ('pending', 'sending');

-- Fixed-window rate-limit counters, keyed by an HMAC of the IP or email (raw values are never stored).
CREATE TABLE waitlist.rate_limit (
    bucket        text NOT NULL CHECK (char_length(bucket) <= 40),
    key_hash      bytea NOT NULL CHECK (octet_length(key_hash) = 16),
    window_start  timestamptz NOT NULL,
    hits          integer NOT NULL CHECK (hits > 0),
    PRIMARY KEY (bucket, key_hash, window_start)
);

-- The public aggregate. The constraints make it impossible to publish a number below 50 or not a multiple of 10.
CREATE TABLE waitlist.public_stats (
    id           smallint PRIMARY KEY CHECK (id = 1),
    shown        boolean NOT NULL,
    count_floor  integer CHECK (count_floor IS NULL OR (count_floor >= 50 AND count_floor % 10 = 0)),
    computed_at  timestamptz NOT NULL,
    CONSTRAINT public_stats_shown_has_count CHECK (shown = (count_floor IS NOT NULL))
);

REVOKE ALL ON ALL TABLES IN SCHEMA waitlist FROM PUBLIC;
REVOKE ALL ON SCHEMA waitlist FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_waitlist') THEN
        GRANT USAGE ON SCHEMA waitlist TO tracewise_waitlist;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON waitlist.signup, waitlist.verify_token, waitlist.email_outbox, waitlist.rate_limit, waitlist.public_stats
            TO tracewise_waitlist;
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE waitlist.public_stats, waitlist.rate_limit, waitlist.email_outbox, waitlist.verify_token, waitlist.signup;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
