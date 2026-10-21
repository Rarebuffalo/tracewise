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


def test_only_the_purge_is_security_definer_and_only_the_system_role_runs_it(owner: Any) -> None:
    definers = rows(owner, "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace AND prosecdef")
    assert definers == [("tracewise_purge",)]
    executable = rows(
        owner,
        """SELECT p.proname, r.rolname FROM pg_proc p CROSS JOIN pg_roles r
            WHERE p.pronamespace = 'public'::regnamespace AND r.rolname IN ('tracewise_app', 'tracewise_system') AND p.prosecdef
              AND has_function_privilege(r.oid, p.oid, 'EXECUTE')""",
    )
    assert executable == [("tracewise_purge", "tracewise_system")]


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
