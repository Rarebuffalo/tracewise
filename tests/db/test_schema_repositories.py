"""T-104: schema, migrations, least privilege, repositories, publication write-once (FS-PUB-1/2)."""

from __future__ import annotations

import psycopg
import pytest

from tests.pg import OWNER
from tracewise.db import repositories as repo
from tracewise.db.migrate import downgrade, upgrade
from tracewise.db.session import transaction

SHA = "c" * 40


def _run(conn, run_id: int = 100, attempt: int = 1) -> int:  # type: ignore[no-untyped-def]
    repo.upsert_installation(conn, 9, "acme")
    repo.upsert_repository(conn, 1, 9, "acme/app")
    return repo.insert_workflow_run(
        conn,
        installation_id=9,
        repo_id=1,
        run_id=run_id,
        attempt=attempt,
        workflow_id=55,
        head_sha=SHA,
        head_branch="main",
        head_repo_id=1,
        event="push",
        conclusion="failure",
    )


def test_migrations_down_and_up(pg, owner) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER))
    assert owner.execute("SELECT to_regclass('public.job')").fetchone() == (None,)
    upgrade(pg.url(OWNER))
    assert owner.execute("SELECT to_regclass('public.job')::text").fetchone() == ("job",)


def test_runtime_role_is_least_privilege(pool) -> None:  # type: ignore[no-untyped-def]
    for stmt in (
        "DROP TABLE job",
        "ALTER TABLE job ADD COLUMN x int",
        "DELETE FROM audit_event",
        "UPDATE audit_event SET actor='x'",
        "DELETE FROM installation",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
            c.execute(stmt)


def test_delivery_dedupe(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        assert repo.insert_delivery(c, "d-1", "workflow_run", "completed", 9, "ignored")
        assert not repo.insert_delivery(c, "d-1", "workflow_run", "completed", 9, "ignored")
        repo.set_delivery_outcome(c, "d-1", "enqueued", 5)
        row = repo.get_delivery(c, "d-1")
    assert row is not None and (row["outcome"], row["job_id"]) == ("enqueued", 5)


def test_workflow_run_idempotent(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        a = _run(c)
        b = _run(c)
        d = _run(c, attempt=2)
    assert a == b != d


def test_schema_rejects_bad_rows(pool) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(psycopg.errors.CheckViolation), transaction(pool) as c:
        c.execute("INSERT INTO job (kind, installation_id, dedupe_key, payload, status) VALUES ('k', 1, 'x', '{}', 'running')")
    with pytest.raises(psycopg.errors.CheckViolation), transaction(pool) as c:
        c.execute("INSERT INTO job (kind, installation_id, dedupe_key, payload, status) VALUES ('k', 1, 'y', '{}', 'bogus')")
    with pytest.raises(psycopg.errors.CheckViolation), transaction(pool) as c:
        repo.upsert_installation(c, 9)
        repo.upsert_repository(c, 1, 9, "acme/app")
        repo.insert_workflow_run(
            c,
            installation_id=9,
            repo_id=1,
            run_id=1,
            attempt=1,
            workflow_id=None,
            head_sha="XYZ" * 13 + "a",
            head_branch=None,
            head_repo_id=None,
            event="push",
            conclusion="failure",
        )


def test_commit_comment_is_write_once(pool) -> None:  # type: ignore[no-untyped-def]
    key = repo.commit_comment_key(1, SHA, 55)
    with transaction(pool) as c:
        run_pk = _run(c)
        a1 = repo.upsert_analysis(
            c,
            installation_id=9,
            run_pk=run_pk,
            status="diagnosed",
            category="code_regression",
            confidence_band="high",
            diagnosis={"schema_version": "2"},
        )
        pub = repo.reserve_publication(c, installation_id=9, analysis_id=a1, surface="commit_comment", target_key=key)
        assert pub["state"] == "pending"
        repo.mark_published(c, pub["id"], a1, 777)
    with transaction(pool) as c:
        again = repo.reserve_publication(c, installation_id=9, analysis_id=a1, surface="commit_comment", target_key=key)
        assert (again["id"], again["state"], again["github_id"]) == (pub["id"], "published", 777)
    with pytest.raises(psycopg.errors.CheckViolation, match="write-once"), transaction(pool) as c:
        repo.mark_published(c, pub["id"], a1, 778)
    with transaction(pool) as c:  # a failure note cannot overwrite a published row either
        repo.mark_publication_failed(c, pub["id"], "boom")
        row = c.execute("SELECT state, github_id FROM publication WHERE id = %s", (pub["id"],)).fetchone()
    assert row == {"state": "published", "github_id": 777}


def test_pr_comment_and_check_run_are_upserted(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        a1 = repo.upsert_analysis(
            c, installation_id=9, run_pk=_run(c, 100), status="diagnosed", category=None, confidence_band=None, diagnosis=None
        )
        a2 = repo.upsert_analysis(
            c, installation_id=9, run_pk=_run(c, 101), status="inconclusive", category=None, confidence_band=None, diagnosis=None
        )
        for surface, key in (("pr_comment", repo.pr_comment_key(1, 42, 55)), ("check_run", repo.check_run_key(1, 100))):
            p = repo.reserve_publication(c, installation_id=9, analysis_id=a1, surface=surface, target_key=key)
            repo.mark_published(c, p["id"], a1, 5)
            p2 = repo.reserve_publication(c, installation_id=9, analysis_id=a2, surface=surface, target_key=key)
            assert p2["id"] == p["id"] and p2["github_id"] == 5  # caller edits github_id 5
            repo.mark_published(c, p["id"], a2, 5)
        n = c.execute("SELECT count(*) AS n FROM publication WHERE analysis_id = %s", (a2,)).fetchone()
    assert n == {"n": 2}


def test_signature_counts_distinct_runs_and_redacts(pool) -> None:  # type: ignore[no-untyped-def]
    tok = "ghp_" + "Z" * 36
    with transaction(pool) as c:
        r1, r2 = _run(c, 100), _run(c, 101)
        kw = {"repo_id": 1, "installation_id": 9, "fingerprint": "0123456789abcdef", "normalized_message": f"auth {tok} failed"}
        assert repo.record_signature(c, run_pk=r1, **kw) == 1
        assert repo.record_signature(c, run_pk=r1, **kw) == 1  # same run reprocessed: no double count
        assert repo.record_signature(c, run_pk=r2, **kw) == 2
        msg = c.execute("SELECT normalized_message FROM failure_signature").fetchone()
    assert msg is not None and tok not in msg["normalized_message"]


def test_usage_and_audit_are_content_free(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        repo.add_usage(c, 9, "analysis", 1)
        repo.audit(c, "system", "installation.created", 9, repos=3)
        row = c.execute("SELECT actor, action, detail FROM audit_event").fetchone()
    assert row == {"actor": "system", "action": "installation.created", "detail": {"repos": 3}}


def test_short_error_redacts_and_caps() -> None:
    e = RuntimeError("401 for token ghs_" + "A" * 36 + " " + "x" * 1000)
    s = repo.short_error(e)
    assert "ghs_" not in s and len(s) == 500


def test_migration_0002_roundtrip_and_new_state(pg, owner) -> None:  # type: ignore[no-untyped-def]
    downgrade(pg.url(OWNER), "0001")
    cols = {r[0] for r in owner.execute("SELECT column_name FROM information_schema.columns WHERE table_name='publication'")}
    assert "source_attempt" not in cols
    upgrade(pg.url(OWNER))
    cols = {r[0] for r in owner.execute("SELECT column_name FROM information_schema.columns WHERE table_name='publication'")}
    assert {"source_run_id", "source_attempt", "content_digest", "missing_permission"} <= cols


def test_unpublished_permission_never_overwrites_published(pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:
        a = repo.upsert_analysis(
            c, installation_id=9, run_pk=_run(c), status="diagnosed", category=None, confidence_band=None, diagnosis=None
        )
        p = repo.reserve_publication(c, installation_id=9, analysis_id=a, surface="pr_comment", target_key="k")
        repo.mark_unpublished_permission(c, p["id"], "pull_requests=write")
        row = c.execute("SELECT state, missing_permission FROM publication WHERE id=%s", (p["id"],)).fetchone()
        assert row == {"state": "unpublished_permission", "missing_permission": "pull_requests=write"}
        repo.mark_published(c, p["id"], a, 9, source_run_id=55, source_attempt=1, content_digest="a" * 64)
        repo.mark_unpublished_permission(c, p["id"], "x")
        row = c.execute("SELECT state, missing_permission, source_attempt FROM publication WHERE id=%s", (p["id"],)).fetchone()
    assert row == {"state": "published", "missing_permission": None, "source_attempt": 1}
    with pytest.raises(psycopg.errors.CheckViolation), transaction(pool) as c:
        c.execute("UPDATE publication SET content_digest = 'nothex' WHERE id = %s", (p["id"],))


def test_migration_0003_roundtrip_and_lifecycle_outcomes(pg, owner) -> None:  # type: ignore[no-untyped-def]
    owner.execute("INSERT INTO webhook_delivery (delivery_id, event, outcome) VALUES ('x', 'workflow_run', 'repo_not_in_scope')")
    downgrade(pg.url(OWNER), "0002")
    assert owner.execute("SELECT outcome FROM webhook_delivery WHERE delivery_id='x'").fetchone() == ("ignored",)
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute("INSERT INTO webhook_delivery (delivery_id, event, outcome) VALUES ('y', 'e', 'processed')")
    upgrade(pg.url(OWNER))
    owner.execute("INSERT INTO webhook_delivery (delivery_id, event, outcome) VALUES ('z', 'e', 'installation_inactive')")


def test_migration_0004_roundtrip_and_runtime_grants(pg, owner, pool) -> None:  # type: ignore[no-untyped-def]
    with transaction(pool) as c:  # the runtime role may use the recovery tables
        c.execute("INSERT INTO recovery_checkpoint (key, value) VALUES ('k', 'v')")
        c.execute("INSERT INTO redelivery_request (guid, github_delivery_id, event) VALUES ('g', 1, 'workflow_run')")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction(pool) as c:
        c.execute("DELETE FROM recovery_checkpoint")
    downgrade(pg.url(OWNER), "0003")
    assert owner.execute("SELECT to_regclass('public.recovery_checkpoint')").fetchone() == (None,)
    upgrade(pg.url(OWNER))
    assert owner.execute("SELECT to_regclass('public.redelivery_request')::text").fetchone() == ("redelivery_request",)


def test_short_error_never_copies_row_or_input_content(pg, owner) -> None:  # type: ignore[no-untyped-def]
    """Phase 36 (P-5): psycopg errors carry `DETAIL: Failing row contains (...)` and pydantic errors echo
    `input_value=...`. short_error() feeds job.last_error and publication.last_error (kept up to 365 days), so it
    must keep the error class and primary message only (its own contract: never log content; FS-SEC-3)."""
    import pydantic

    try:
        owner.execute(
            "INSERT INTO publication (installation_id, analysis_id, surface, target_key, content_digest) "
            "VALUES (1, 1, 'check_run', 'ROW_CONTENT_MARKER_7', 'zz')"
        )
    except psycopg.Error as e:
        db_err = e
    s = repo.short_error(db_err)
    assert "ROW_CONTENT_MARKER_7" not in s and "Failing row" not in s and s  # still says what failed

    class M(pydantic.BaseModel):
        n: int

    try:
        M.model_validate({"n": "INPUT_CONTENT_MARKER_8"})
    except pydantic.ValidationError as e:
        v_err = e
    s2 = repo.short_error(v_err)
    assert "INPUT_CONTENT_MARKER_8" not in s2 and "validation error" in s2 and "n" in s2
