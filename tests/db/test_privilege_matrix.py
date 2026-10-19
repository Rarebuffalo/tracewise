"""Phase 51 (D-11 input): the documented role/privilege matrix equals the live catalogue after all migrations.

The matrix in docs/DEPLOYMENT-BLUEPRINT.md §6 is parsed and compared table by table, so neither the grants nor the
documentation can drift unnoticed. This records the current design; it does not decide D-11.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DOC = Path(__file__).resolve().parents[2] / "docs" / "DEPLOYMENT-BLUEPRINT.md"
LETTER = {"SELECT": "S", "INSERT": "I", "UPDATE": "U", "DELETE": "D"}


def documented() -> dict[tuple[str, str], str]:
    block = DOC.read_text().split("<!-- privilege-matrix:start -->")[1].split("<!-- privilege-matrix:end -->")[0]
    out: dict[tuple[str, str], str] = {}
    for line in block.splitlines():
        m = re.match(r"\s*\|\s*([a-z_]+)\s*\|\s*([SIUD—]+)\s*\|\s*([SIUD—]+)\s*\|", line)
        if m:
            out[(m.group(1), "tracewise_app")] = m.group(2).replace("—", "")
            out[(m.group(1), "tracewise_system")] = m.group(3).replace("—", "")
    return out


def live(owner: Any) -> dict[tuple[str, str], str]:
    rows = owner.execute(
        """SELECT c.relname, r.rolname, p.priv FROM pg_class c CROSS JOIN pg_roles r
           CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS p(priv)
           WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
             AND r.rolname IN ('tracewise_app', 'tracewise_system') AND has_table_privilege(r.oid, c.oid, p.priv)"""
    ).fetchall()
    tables = [
        t for (t,) in owner.execute("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'")
    ]
    out = {(t, role): "" for t in tables for role in ("tracewise_app", "tracewise_system")}
    for t, role, priv in rows:
        out[(t, role)] += LETTER[priv]
    return {k: "".join(sorted(v, key="SIUD".index)) for k, v in out.items()}


def test_documented_privilege_matrix_matches_the_catalogue(pg, owner) -> None:  # type: ignore[no-untyped-def]
    assert documented() == live(owner)


def test_only_the_system_role_may_execute_the_purge(pg, owner) -> None:  # type: ignore[no-untyped-def]
    got = dict(
        owner.execute(
            "SELECT rolname, has_function_privilege(oid, 'tracewise_purge(integer)', 'EXECUTE') FROM pg_roles"
            " WHERE rolname IN ('tracewise_app', 'tracewise_system')"
        ).fetchall()
    )
    assert got == {"tracewise_app": False, "tracewise_system": True}
