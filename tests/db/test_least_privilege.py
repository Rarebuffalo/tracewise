"""D-11 supporting evidence: least privilege beyond the S/I/U/D matrix (test_privilege_matrix.py). Every migrated
object is checked for privileges a runtime role must never hold, so a future migration cannot widen them silently.
Records the current design; it does not decide D-11."""

from __future__ import annotations

from typing import Any

RUNTIME = ("tracewise_app", "tracewise_system")


def rows(owner: Any, sql: str) -> list[tuple[Any, ...]]:
    return list(owner.execute(sql).fetchall())


def test_no_truncate_references_or_trigger_on_any_relation(owner: Any) -> None:
    assert (
        rows(
            owner,
            """SELECT c.relname, r.rolname, p FROM pg_class c CROSS JOIN pg_roles r
            CROSS JOIN unnest(ARRAY['TRUNCATE', 'REFERENCES', 'TRIGGER']) AS p
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND r.rolname IN ('tracewise_app', 'tracewise_system') AND has_table_privilege(r.oid, c.oid, p)""",
        )
        == []
    )


def test_public_holds_no_privilege_on_any_relation_or_sequence(owner: Any) -> None:
    assert (
        rows(
            owner,
            """SELECT c.relname, a.privilege_type FROM pg_class c, aclexplode(c.relacl) a
           WHERE c.relnamespace = 'public'::regnamespace AND a.grantee = 0""",
        )
        == []
    )


def test_sequences_allow_nextval_but_never_setval(owner: Any) -> None:
    assert (
        rows(
            owner,
            """SELECT c.relname, r.rolname FROM pg_class c CROSS JOIN pg_roles r
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
              AND r.rolname IN ('tracewise_app', 'tracewise_system')
              AND has_sequence_privilege(r.oid, c.oid, 'UPDATE')""",
        )
        == []
    )


def test_no_column_level_grants_hide_beside_the_table_grants(owner: Any) -> None:
    assert (
        rows(
            owner,
            """SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
           WHERE c.relnamespace = 'public'::regnamespace AND a.attacl IS NOT NULL""",
        )
        == []
    )


def test_only_the_purge_the_job_fence_and_the_requeue_are_security_definers_with_their_runners(owner: Any) -> None:
    """The requeue (0013) runs for no runtime role: only the `tracewise_operator` group (test below). The purge runs
    only for the system role. The job fence (migration 0012, D-1/D-2) is runnable by both runtime
    roles: the tenant plane must check ownership in its own write transactions, without job-table rights."""
    definers = rows(
        owner, "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace AND prosecdef ORDER BY proname"
    )
    assert definers == [("tracewise_job_owned",), ("tracewise_purge",), ("tracewise_requeue",)]
    executable = rows(
        owner,
        """SELECT p.proname, r.rolname FROM pg_proc p CROSS JOIN pg_roles r
            WHERE p.pronamespace = 'public'::regnamespace AND r.rolname IN ('tracewise_app', 'tracewise_system') AND p.prosecdef
              AND has_function_privilege(r.oid, p.oid, 'EXECUTE')""",
    )
    assert sorted(executable) == [
        ("tracewise_job_owned", "tracewise_app"),
        ("tracewise_job_owned", "tracewise_system"),
        ("tracewise_purge", "tracewise_system"),
    ]


def test_runtime_roles_cannot_create_or_inherit_anything(owner: Any) -> None:
    for role in RUNTIME:
        schema_create, db_create = owner.execute(
            "SELECT has_schema_privilege(%s, 'public', 'CREATE'), has_database_privilege(%s, current_database(), 'CREATE')",
            (role, role),
        ).fetchone()
        assert (schema_create, db_create) == (False, False), role
        attrs = owner.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication FROM pg_roles WHERE rolname = %s", (role,)
        ).fetchone()
        assert attrs == (False, False, False, False), role
    assert (
        rows(
            owner,
            """SELECT g.rolname, m.rolname FROM pg_auth_members a JOIN pg_roles g ON g.oid = a.roleid
           JOIN pg_roles m ON m.oid = a.member WHERE m.rolname IN ('tracewise_app', 'tracewise_system')""",
        )
        == []
    )


def test_no_default_privileges_grant_future_objects_to_runtime_roles_or_public(owner: Any) -> None:
    assert (
        rows(
            owner,
            """SELECT d.defaclobjtype, a.grantee::regrole::text FROM pg_default_acl d, aclexplode(d.defaclacl) a
           WHERE a.grantee = 0
              OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('tracewise_app', 'tracewise_system'))""",
        )
        == []
    )


def test_only_the_system_role_bypasses_rls(owner: Any) -> None:
    got = dict(rows(owner, "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('tracewise_app', 'tracewise_system')"))
    assert got == {"tracewise_app": False, "tracewise_system": True}


def test_only_the_operator_group_may_execute_the_requeue(owner: Any) -> None:
    got = dict(
        owner.execute(
            "SELECT rolname, has_function_privilege(oid, 'tracewise_requeue(bigint, text, boolean)', 'EXECUTE')"
            " FROM pg_roles WHERE rolname IN ('tracewise_app', 'tracewise_system', 'tracewise_operator', 'ops_mallory')"
        ).fetchall()
    )
    assert got == {"tracewise_app": False, "tracewise_system": False, "tracewise_operator": True, "ops_mallory": False}
    acl = owner.execute("SELECT proacl::text FROM pg_proc WHERE proname = 'tracewise_requeue_max_reruns'").fetchone()
    assert acl is not None and not (acl[0] or "").startswith("{=") and ",=" not in (acl[0] or "")  # PUBLIC revoked


def test_runtime_roles_hold_only_what_their_code_uses(owner: Any) -> None:
    """D-11 option C (0015): no runtime role may DELETE from any Tracewise table, and the tenant role uses only the
    sequences of the three tables it inserts into."""
    deleters = rows(
        owner,
        """SELECT c.relname, r.rolname FROM pg_class c CROSS JOIN pg_roles r
           WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
             AND r.rolname IN ('tracewise_app', 'tracewise_system') AND has_table_privilege(r.oid, c.oid, 'DELETE')""",
    )
    assert deleters == []
    seqs = rows(
        owner,
        """SELECT relname FROM (SELECT c.relname, c.oid FROM pg_class c
                                 WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S' OFFSET 0) s
            WHERE has_sequence_privilege('tracewise_app', s.oid, 'USAGE') ORDER BY 1""",
    )
    assert seqs == [("analysis_id_seq",), ("publication_id_seq",), ("workflow_run_id_seq",)]
