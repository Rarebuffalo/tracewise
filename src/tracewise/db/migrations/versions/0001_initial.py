"""Initial schema (ARCHITECTURE section 3, T-104).

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE installation (
    id              bigint PRIMARY KEY,
    account_login   text,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    monthly_quota   integer NOT NULL DEFAULT 500 CHECK (monthly_quota >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,
    purge_after     timestamptz
);

CREATE TABLE repository (
    id              bigint PRIMARY KEY,
    installation_id bigint NOT NULL REFERENCES installation (id),
    full_name       text NOT NULL,
    default_branch  text,
    enabled         boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    removed_at      timestamptz
);
CREATE INDEX repository_installation ON repository (installation_id);

-- Retained 14 days (T-704). Content-free: identifiers and outcome only.
CREATE TABLE webhook_delivery (
    delivery_id     text PRIMARY KEY CHECK (length(delivery_id) BETWEEN 1 AND 200),
    event           text NOT NULL,
    action          text,
    installation_id bigint,
    received_at     timestamptz NOT NULL DEFAULT now(),
    outcome         text NOT NULL CHECK (outcome IN ('enqueued', 'duplicate_run', 'ignored', 'rejected')),
    job_id          bigint
);
CREATE INDEX webhook_delivery_received ON webhook_delivery (received_at);

CREATE TABLE workflow_run (
    id              bigserial PRIMARY KEY,
    installation_id bigint NOT NULL,
    repo_id         bigint NOT NULL,
    github_run_id   bigint NOT NULL,
    run_attempt     integer NOT NULL CHECK (run_attempt >= 1),
    workflow_id     bigint,
    head_sha        char(40) NOT NULL CHECK (head_sha ~ '^[0-9a-f]{40}$'),
    head_branch     text,
    head_repo_id    bigint,
    event           text NOT NULL,
    conclusion      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repo_id, github_run_id, run_attempt)
);

-- Job states (explicit): queued -> running -> succeeded
--                                  running -> retry_wait -> running ...
--                                  running -> dead (permanent error, attempts or deadline exhausted)
--                        queued/retry_wait -> cancelled
CREATE TABLE job (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL,
    installation_id bigint NOT NULL,
    run_key         text,
    dedupe_key      text NOT NULL UNIQUE,
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'retry_wait', 'succeeded', 'dead', 'cancelled')),
    attempts        integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts    integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    run_after       timestamptz NOT NULL DEFAULT now(),
    deadline_at     timestamptz,
    locked_by       text,
    locked_until    timestamptz,
    last_error      text CHECK (length(last_error) <= 500),
    result          jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    CHECK ((status = 'running') = (locked_by IS NOT NULL AND locked_until IS NOT NULL)),
    CHECK ((status IN ('succeeded', 'dead', 'cancelled')) = (finished_at IS NOT NULL))
);
CREATE INDEX job_ready ON job (run_after, id) WHERE status IN ('queued', 'retry_wait');
CREATE INDEX job_running_installation ON job (installation_id) WHERE status = 'running';
CREATE INDEX job_running_run ON job (run_key) WHERE status = 'running';

CREATE TABLE analysis (
    id              bigserial PRIMARY KEY,
    installation_id bigint NOT NULL,
    run_pk          bigint NOT NULL UNIQUE REFERENCES workflow_run (id),
    status          text NOT NULL CHECK (status IN ('diagnosed', 'inconclusive', 'logs_unavailable',
                                                    'permission_denied', 'could_not_complete')),
    category        text,
    confidence_band text CHECK (confidence_band IN ('high', 'medium', 'low')),
    diagnosis       jsonb,
    provider        text,
    model           text,
    tokens_in       integer,
    tokens_out      integer,
    cost_usd        numeric(12, 6),
    latency_ms      integer,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE publication (
    id              bigserial PRIMARY KEY,
    installation_id bigint NOT NULL,
    analysis_id     bigint NOT NULL REFERENCES analysis (id),
    surface         text NOT NULL CHECK (surface IN ('commit_comment', 'pr_comment', 'check_run')),
    target_key      text NOT NULL,
    github_id       bigint,
    state           text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'published', 'failed', 'skipped')),
    last_error      text CHECK (length(last_error) <= 500),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (surface, target_key)
);

-- FS-PUB-1: a commit comment is write-once. Once published it can never be re-pointed or re-published.
CREATE FUNCTION publication_commit_comment_write_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.surface = 'commit_comment' AND OLD.state = 'published' THEN
        RAISE EXCEPTION 'commit comment publication % is write-once', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER publication_write_once BEFORE UPDATE ON publication
    FOR EACH ROW EXECUTE FUNCTION publication_commit_comment_write_once();

CREATE TABLE failure_signature (
    repo_id             bigint NOT NULL,
    fingerprint         char(16) NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{16}$'),
    installation_id     bigint NOT NULL,
    normalized_message  varchar(300) NOT NULL,
    first_seen_run      bigint NOT NULL,
    last_seen_run       bigint NOT NULL,
    occurrences         integer NOT NULL DEFAULT 1,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (repo_id, fingerprint)
);

CREATE TABLE usage_event (
    id              bigserial PRIMARY KEY,
    installation_id bigint NOT NULL,
    analysis_id     bigint REFERENCES analysis (id),
    kind            text NOT NULL,
    quantity        numeric(14, 4) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_event_installation_month ON usage_event (installation_id, created_at);

CREATE TABLE audit_event (
    id              bigserial PRIMARY KEY,
    installation_id bigint,
    actor           text NOT NULL,
    action          text NOT NULL,
    detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Least privilege: the runtime role gets DML only, never DDL (ADR-16 / IMPLEMENTATION-PLAN section 4).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tracewise_app') THEN
        GRANT USAGE ON SCHEMA public TO tracewise_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO tracewise_app;
        GRANT DELETE ON webhook_delivery, job, usage_event, failure_signature TO tracewise_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tracewise_app;
        REVOKE UPDATE, DELETE ON audit_event FROM tracewise_app;
    END IF;
END $$;
"""

DOWN = """
DROP TABLE IF EXISTS audit_event, usage_event, failure_signature, publication, analysis, job,
    workflow_run, webhook_delivery, repository, installation CASCADE;
DROP FUNCTION IF EXISTS publication_commit_comment_write_once();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
