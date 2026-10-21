"""Worker process entry point (T-1002 local foundation).

    python -m tracewise.worker [--worker-id ID] [--once]

Startup validates configuration and refuses to run unless:
* `DATABASE_URL` is the RLS-restricted tenant role and `DATABASE_URL_SYSTEM` the BYPASSRLS system role,
* the schema is at this build's migration head (the process never migrates),
* the GitHub App credentials and the model provider are configured (the fake provider only with TW_ENV=test).

Shutdown: the first SIGTERM/SIGINT stops claiming; the current job runs to completion, then pools close and the
process exits 0. A second signal uses the default action (immediate exit); the claimed job's lease then expires and
another worker reclaims it (T-105 semantics). Exit codes: 0 clean stop, 1 runtime failure, 2 configuration refused.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType

from tracewise.config import Settings, get_settings, invalid_fields
from tracewise.db.session import DatabaseUnavailable, SchemaMismatch, WrongDatabaseRole
from tracewise.jobs.worker import Worker
from tracewise.observe import event

log = logging.getLogger(__name__)

EXIT_OK, EXIT_RUNTIME, EXIT_CONFIG = 0, 1, 2


class ConfigError(Exception):
    """Startup refused; names settings, never values."""


@dataclass
class Runtime:
    worker: Worker
    close: Callable[[], None]


def build_from_settings(st: Settings, worker_id: str) -> Runtime:
    from tracewise.context.gitfetch import GitFetcher, GitFetchError
    from tracewise.db.migrate import head_revision
    from tracewise.db.session import make_pool, require_schema_at, require_system_plane
    from tracewise.github.auth import AppCredentials, TokenProvider
    from tracewise.github.client import GitHubHTTP
    from tracewise.investigate.loop import InvestigationLimits
    from tracewise.investigate.providers import ProviderConfigError, provider_factory
    from tracewise.jobs.handlers.analyze import AnalyzeDeps, make_analyze_handler

    missing = [
        n
        for n, v in (
            ("DATABASE_URL", st.database_url),
            ("DATABASE_URL_SYSTEM", st.database_url_system),
            ("GITHUB_APP_ID", st.github_app_id),
            ("GITHUB_APP_PRIVATE_KEY_PATH", st.github_app_private_key_path),
        )
        if not v
    ]
    if missing:
        raise ConfigError("missing: " + ", ".join(missing))
    assert st.database_url and st.database_url_system and st.github_app_id and st.github_app_private_key_path
    if st.database_url.get_secret_value() == st.database_url_system.get_secret_value():
        raise ConfigError("DATABASE_URL and DATABASE_URL_SYSTEM must be different roles")
    try:
        providers = provider_factory(st)
    except ProviderConfigError as e:
        raise ConfigError(str(e)) from None
    try:
        creds = AppCredentials.from_pem_file(st.github_app_id, st.github_app_private_key_path)
    except (OSError, ValueError, TypeError):
        raise ConfigError("GITHUB_APP_PRIVATE_KEY_PATH does not name a readable RSA private key") from None

    system = make_pool(st.database_url_system.get_secret_value())
    tenant = make_pool(st.database_url.get_secret_value())

    def close() -> None:
        tenant.close()
        system.close()
        http.close()

    http = GitHubHTTP()
    try:
        require_system_plane(system)
        require_schema_at(system, head_revision())
        try:
            swept = GitFetcher().sweep_workspaces()  # AT-SEC-06: workspaces left by a killed process
        except GitFetchError:
            swept = 0
        deps = AnalyzeDeps(
            tenant,
            http,
            TokenProvider(creds, http, clock=time.time),
            st.github_app_id,
            provider_factory=providers,
            fetcher_factory=lambda: GitFetcher(),
            limits=InvestigationLimits.from_settings(st),
            report_max_chars=st.report_max_chars,
            log_max_bytes=st.log_max_bytes_per_job,
            price_input_per_mtok=st.llm_price_input_per_mtok,
            price_output_per_mtok=st.llm_price_output_per_mtok,
            analysis_quota=st.analysis_quota_monthly,
        )
        handler = make_analyze_handler(deps)  # require_tenant_plane runs here
    except BaseException:
        close()
        raise
    event(log, "worker.workspaces_swept", count=swept)
    return Runtime(Worker(system, {"analyze": handler}, worker_id), close)


def main(argv: list[str] | None = None, build: Callable[[Settings, str], Runtime] = build_from_settings) -> int:
    ap = argparse.ArgumentParser(prog="python -m tracewise.worker")
    ap.add_argument("--worker-id", default=f"{socket.gethostname()[:40]}-{os.getpid()}")
    ap.add_argument("--once", action="store_true", help="process at most one job, then exit")
    ap.add_argument("--idle-sleep", type=float, default=1.0)
    a = ap.parse_args(argv)
    stop = threading.Event()
    holder: list[Runtime] = []

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        # Installed before startup (Phase 41): a stop requested while connecting or validating is graceful too.
        event(log, "worker.stopping", signal=signal.Signals(signum).name)
        stop.set()
        if holder:
            holder[0].worker.stop()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)  # a second signal: default action (immediate exit)
        signal.signal(signal.SIGINT, signal.default_int_handler)

    old = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT)}
    event(log, "worker.starting", worker=a.worker_id)
    try:
        return _run(a, build, stop, holder)
    finally:
        for s, h in old.items():
            signal.signal(s, h)


def _run(a: argparse.Namespace, build: Callable[[Settings, str], Runtime], stop: threading.Event, holder: list[Runtime]) -> int:
    try:
        st = get_settings()
    except Exception as e:  # pydantic: names only, never values
        print(f"worker refused to start: invalid configuration ({invalid_fields(e)})", file=sys.stderr)
        return EXIT_CONFIG
    try:
        rt = build(st, a.worker_id)
    except (ConfigError, WrongDatabaseRole, SchemaMismatch) as e:
        event(log, "worker.refused", logging.ERROR, error_type=type(e).__name__)
        print(f"worker refused to start: {e}", file=sys.stderr)
        return EXIT_CONFIG
    except DatabaseUnavailable as e:
        event(log, "worker.refused", logging.ERROR, error_type=type(e).__name__)
        print("worker refused to start: database unavailable", file=sys.stderr)
        return EXIT_RUNTIME
    holder.append(rt)
    if stop.is_set():  # stopped during startup: release resources, claim nothing
        rt.close()
        event(log, "worker.stopped", exit_code=EXIT_OK, during_startup=True)
        return EXIT_OK
    event(log, "worker.started", worker=a.worker_id, once=a.once)
    code = EXIT_OK
    try:
        if a.once:
            rt.worker.run_once()
        else:
            rt.worker.run_forever(idle_sleep_s=a.idle_sleep)
    except DatabaseUnavailable:
        code = EXIT_RUNTIME
        event(log, "worker.failed", logging.ERROR, error_type="DatabaseUnavailable")
    except Exception as e:  # a bug or an unexpected database error: stop, never spin
        code = EXIT_RUNTIME
        event(log, "worker.failed", logging.ERROR, error_type=type(e).__name__)
    finally:
        rt.close()
        event(log, "worker.stopped", exit_code=code)
    return code


if __name__ == "__main__":  # pragma: no cover
    from tracewise.logging import configure_cli

    configure_cli()
    sys.exit(main())
