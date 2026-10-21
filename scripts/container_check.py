"""Local stack check for the runtime image (T-1002). Offline: every container runs with `--network none`.

    make image-check          (builds `tracewise:local`, then runs this script)

Starts a disposable PostgreSQL (tests/pg.py) with a non-superuser owner and database (the production role model),
mounts its Unix socket into the containers, and runs the processes from the image in order: migrate status →
superuser refusal (exit 2) → migrate upgrade → preflight --database → web (liveness and readiness) → worker --once →
a wrong worker configuration (exit 2) → ops report. A throwaway RSA key is generated in a private temporary directory
and deleted afterwards; the webhook secret is random per run. Prints one line per step and exits non-zero on the
first unexpected result. Nothing reaches GitHub or a model provider.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from tests.pg import APP, OWNER, SYSTEM, ephemeral  # noqa: E402  (OWNER: the bootstrap superuser, setup only)

IMAGE = os.environ.get("TRACEWISE_IMAGE", "tracewise:local")
STAGE_OWNER, STAGE_DB = "tracewise_stage_owner", "tracewise_stage"
PROBE = (
    "import urllib.request, urllib.error\n"
    "for p in ('/healthz', '/readyz'):\n"
    "    try:\n"
    "        print(p, urllib.request.urlopen('http://127.0.0.1:8000' + p, timeout=3).status)\n"
    "    except urllib.error.HTTPError as x:\n"
    "        print(p, x.code)\n"
)


def main() -> int:
    pg = ephemeral()
    keydir = Path(tempfile.mkdtemp(prefix="tw-key-"))
    keydir.chmod(0o700)
    key = keydir / "app.pem"
    key.write_bytes(
        rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    key.chmod(0o600)

    # The production role model (scripts/db/provision_roles.sql): a NON-superuser owner and its own database.
    # tests/pg's bootstrap owner is a superuser, which the migration CLI rightly refuses.
    import psycopg

    with psycopg.connect(pg.url(OWNER, "postgres"), autocommit=True) as c:
        c.execute(f"CREATE ROLE {STAGE_OWNER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        c.execute(f"CREATE DATABASE {STAGE_DB} OWNER {STAGE_OWNER}")

    def url(user: str) -> str:
        return f"postgresql://{user}@/{STAGE_DB}?host={urllib.parse.quote('/pgsock', safe='')}&port={pg.port}"

    env = {
        "TW_ENV": "test",
        "LLM_PROVIDER": "fake",
        "DATABASE_URL": url(APP),
        "DATABASE_URL_SYSTEM": url(SYSTEM),
        "DATABASE_URL_MIGRATIONS": url(STAGE_OWNER),
        "GITHUB_APP_ID": "1",
        "GITHUB_APP_PRIVATE_KEY_PATH": "/run/secrets/app.pem",
        "GITHUB_WEBHOOK_SECRET": "local-check-" + secrets.token_hex(12),
    }
    worker_env = ("DATABASE_URL", "DATABASE_URL_SYSTEM", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH", "LLM_PROVIDER", "TW_ENV")
    base = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}"]
    base += ["-v", f"{pg.sock}:/pgsock", "-v", f"{keydir}:/run/secrets:ro"]

    def e(names: tuple[str, ...] | list[str], **over: str) -> list[str]:
        out: list[str] = []
        for n in names:
            out += ["-e", f"{n}={over.get(n, env[n])}"]
        return out

    def step(label: str, args: list[str], expect: int) -> str:
        p = subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)  # noqa: S603
        last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
        ok = p.returncode == expect
        print(f"{'ok ' if ok else 'BAD'} {label}: exit {p.returncode} (expected {expect}) {last[:160]}")
        if not ok:
            raise SystemExit(1)
        return p.stdout

    try:
        migrate = [IMAGE, "python", "-m", "tracewise.db.migrate"]
        step("migrate status on an empty database", [*base, *e(["DATABASE_URL_MIGRATIONS"]), *migrate, "status"], 4)
        superuser = e(["DATABASE_URL_MIGRATIONS"], DATABASE_URL_MIGRATIONS=url(OWNER))
        step("migrate refuses a superuser owner URL", [*base, *superuser, *migrate, "upgrade"], 2)
        step("migrate upgrade", [*base, *e(["DATABASE_URL_MIGRATIONS"]), *migrate, "upgrade"], 0)
        out = step(
            "preflight --database",
            [*base, *e(list(env)), IMAGE, "python", "-m", "tracewise.preflight", "--process", "all", "--database"],
            0,
        )
        warns = [json.loads(line)["check"] for line in out.splitlines() if '"result": "warn"' in line]
        print(f"    warnings: {warns}")
        web = [IMAGE, "uvicorn", "--factory", "tracewise.web.asgi:create_runtime_app", "--host", "127.0.0.1", "--port", "8000"]
        cid = subprocess.run(  # noqa: S603
            [*base[:2], "-d", *base[2:], *e(["DATABASE_URL_SYSTEM", "GITHUB_WEBHOOK_SECRET", "TW_ENV"]), *web],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        try:
            got = ""
            for _ in range(30):
                r = subprocess.run(["docker", "exec", cid, "python", "-c", PROBE], capture_output=True, text=True, check=False)  # noqa: S603, S607
                got = r.stdout.strip().replace("\n", "; ")
                if r.returncode == 0 and "/readyz 200" in got:
                    break
                time.sleep(1)
            ok = "/healthz 200" in got and "/readyz 200" in got
            print(f"{'ok ' if ok else 'BAD'} web: {got}")
            if not ok:
                return 1
        finally:
            subprocess.run(["docker", "stop", "-t", "10", cid], capture_output=True, check=False)  # noqa: S603, S607
        step("worker --once on an empty queue", [*base, *e(worker_env), IMAGE, "python", "-m", "tracewise.worker", "--once"], 0)
        step(
            "worker refuses the system URL as the tenant URL",
            [*base, *e(worker_env, DATABASE_URL=env["DATABASE_URL_SYSTEM"]), IMAGE, "python", "-m", "tracewise.worker", "--once"],
            2,
        )
        step("ops report", [*base, *e(["DATABASE_URL_SYSTEM"]), IMAGE, "python", "-m", "tracewise.ops", "report"], 0)
        print("container check passed")
        return 0
    finally:
        pg.stop()
        shutil.rmtree(keydir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
