"""Fetch exactly one commit's objects into a private bare repository and read them (T-304; FS-CTX-1, FS-CTX-4, ADR-14).

Security properties (each has a test in tests/context/test_gitfetch.py):

* **No checkout, no execution.** A bare repo is initialised with an empty template; nothing is ever
  checked out, so no hooks, filters, smudge (LFS), attributes, submodules or symlinks touch the disk.
  `core.hooksPath=/dev/null` is set anyway. Files are read with `git cat-file` from the object store.
* **Fixed host.** The remote URL is built from a validated owner/repo on `https://github.com` only.
  (Tests may use `http://127.0.0.1:<port>` via `allow_insecure_loopback=True`, which production never sets.)
  `protocol.allow=never` except that scheme; `http.followRedirects=false`; no credential helper.
* **Token handling.** The installation token is sent as an `Authorization: Basic` header injected via
  `GIT_CONFIG_COUNT/KEY/VALUE` environment variables scoped to that exact URL prefix. It never appears in
  argv, the remote URL, the repo config, logs or error text. Residual risk: the environment of the git
  child processes is readable by the **same OS user** via /proc/<pid>/environ while the fetch runs.
* **Minimal environment.** The child env is built from scratch: no inherited GIT_TRACE*, GIT_CURL_VERBOSE,
  proxies, HOME or system/global config; prompts disabled.
* **Bounded.** `--depth=1`, `--filter=blob:limit=<max_file_bytes>`, a wall-clock timeout and a cap on the
  workspace size during transfer; on breach the whole process group is SIGKILLed. Reads run with
  `GIT_NO_LAZY_FETCH=1` and without credentials, so a filtered (oversized) blob is reported as missing and
  never fetched later.
* **Cleanup.** The workspace is removed in `finally` (success, error, timeout, cancellation). Directories
  are named `tw-ws-<pid>-<random>`; `sweep_workspaces()` at startup removes those of dead processes or
  older than `max_age_s` (FS-CTX-4, AT-SEC-06).
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from tracewise.context.paths import validate_owner_repo, validate_sha
from tracewise.context.source import CodeSource, EntryKind, Limits, TreeEntry
from tracewise.prepass.sanitize import redact

log = logging.getLogger(__name__)

GITHUB = "https://github.com"
WS_PREFIX = "tw-ws-"
_WS_NAME = re.compile(r"^tw-ws-(\d+)-[A-Za-z0-9_]+$")


class GitFetchError(Exception):
    """Fetch failed; callers fall back to the Contents API. Messages are scrubbed."""


class GitAuthError(GitFetchError):
    pass


class CommitNotFound(GitFetchError):
    pass


class GitTimeout(GitFetchError):
    pass


class GitTransferTooLarge(GitFetchError):
    pass


@dataclass(frozen=True)
class FetchLimits:
    fetch_timeout_s: float = 60.0
    read_timeout_s: float = 10.0
    max_transfer_bytes: int = 256 * 1024 * 1024
    poll_s: float = 0.05


def default_workspace_root() -> Path:
    return Path(tempfile.gettempdir()) / "tracewise-ws"


def _dir_bytes(root: Path) -> int:
    total = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(Path(e.path))
                    elif e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
        except FileNotFoundError:
            continue
    return total


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)


class GitFetcher:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        limits: Limits | None = None,
        fetch_limits: FetchLimits | None = None,
        base_url: str = GITHUB,
        allow_insecure_loopback: bool = False,
    ) -> None:
        git = shutil.which("git")
        if git is None:
            raise GitFetchError("git binary not available")
        self.git = git
        self.root = workspace_root or default_workspace_root()
        self.limits = limits or Limits()
        self.flimits = fetch_limits or FetchLimits()
        u = urlsplit(base_url)
        loopback = u.scheme == "http" and u.hostname == "127.0.0.1" and allow_insecure_loopback
        if not (base_url == GITHUB or loopback) or u.path not in ("", "/") or u.username or u.query:
            raise ValueError("git base URL must be https://github.com")
        self.base_url = base_url.rstrip("/")
        self._scheme = u.scheme

    # ------------------------------------------------------------ public

    @contextlib.contextmanager
    def fetch(self, full_name: str, head_sha: str, token: str) -> Iterator[GitObjectSource]:
        owner, repo = validate_owner_repo(full_name)
        validate_sha(head_sha)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        ws = Path(tempfile.mkdtemp(prefix=f"{WS_PREFIX}{os.getpid()}-", dir=self.root))
        try:
            ws.chmod(0o700)
            gitdir = ws / "repo.git"
            self._run(["init", "--bare", "-q", "--template=", str(gitdir)], ws, auth=None, timeout=self.flimits.read_timeout_s)
            url = f"{self.base_url}/{owner}/{repo}.git"
            self._run([*self._cfg(gitdir), "remote", "add", "origin", url], ws, auth=None, timeout=self.flimits.read_timeout_s)
            self._run(
                [
                    *self._cfg(gitdir),
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "--no-write-fetch-head",
                    f"--filter=blob:limit={self.limits.max_file_bytes}",
                    "origin",
                    f"+{head_sha}:refs/tw/head",
                ],
                ws,
                auth=(url, token),
                timeout=self.flimits.fetch_timeout_s,
                watch=ws,
            )
            got = self._run(
                [*self._cfg(gitdir), "rev-parse", "--verify", "refs/tw/head^{commit}"],
                ws,
                auth=None,
                timeout=self.flimits.read_timeout_s,
            ).strip()
            if got != head_sha:
                raise GitFetchError("fetched commit does not match the requested SHA")
            yield GitObjectSource(self, gitdir, ws, head_sha, self.limits)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def sweep_workspaces(self, max_age_s: float = 1800.0) -> int:
        """Remove workspaces left by crashed processes or older than `max_age_s` (startup + periodic)."""
        if not self.root.is_dir():
            return 0
        removed = 0
        now = time.time()
        for d in self.root.iterdir():
            m = _WS_NAME.match(d.name)
            if not m or not d.is_dir() or d.is_symlink():
                continue
            pid = int(m.group(1))
            alive = True
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True
            age = now - d.stat().st_mtime
            if not alive or age > max_age_s or (pid == os.getpid() and age > max_age_s):
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed

    # ------------------------------------------------------------ internals

    def _cfg(self, gitdir: Path) -> list[str]:
        c = {
            "core.hooksPath": "/dev/null",
            "core.fsmonitor": "false",
            "core.askPass": "",
            "credential.helper": "",
            "protocol.allow": "never",
            f"protocol.{self._scheme}.allow": "always",
            "http.followRedirects": "false",
            "fetch.recurseSubmodules": "false",
            "submodule.recurse": "false",
            "gc.auto": "0",
            "maintenance.auto": "false",
            "http.lowSpeedLimit": "1024",
            "http.lowSpeedTime": "20",
            "advice.detachedHead": "false",
        }
        args = ["--git-dir", str(gitdir)]
        for k, v in c.items():
            args += ["-c", f"{k}={v}"]
        return args

    def _env(self, ws: Path, auth: tuple[str, str] | None) -> dict[str, str]:
        env = {
            "PATH": os.pathsep.join(dict.fromkeys([str(Path(self.git).parent), "/usr/bin", "/bin"])),
            "HOME": str(ws),
            "XDG_CONFIG_HOME": str(ws),
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
        if auth is not None:
            url, token = auth
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            env.pop("GIT_NO_LAZY_FETCH")
            env.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": f"http.{url}.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
                }
            )
        return env

    def _run(
        self,
        args: list[str],
        ws: Path,
        *,
        auth: tuple[str, str] | None,
        timeout: float,
        watch: Path | None = None,
        stdin: bytes | None = None,
    ) -> str:
        return self._run_bytes(args, ws, auth=auth, timeout=timeout, watch=watch, stdin=stdin).decode("utf-8", "replace")

    def _run_bytes(
        self,
        args: list[str],
        ws: Path,
        *,
        auth: tuple[str, str] | None,
        timeout: float,
        watch: Path | None = None,
        stdin: bytes | None = None,
        max_out: int | None = None,
    ) -> bytes:
        out_path, err_path = ws / ".out", ws / ".err"
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.Popen(  # noqa: S603 - fixed binary, validated args, no shell
                [self.git, *args],
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=self._env(ws, auth),
                cwd=ws,
                start_new_session=True,
                close_fds=True,
            )
            try:
                if stdin is not None and proc.stdin is not None:
                    proc.stdin.write(stdin)
                    proc.stdin.close()
                deadline = time.monotonic() + timeout
                while proc.poll() is None:
                    if time.monotonic() > deadline:
                        _kill_group(proc)
                        raise GitTimeout(f"git {args_name(args)} timed out after {timeout:.0f}s")
                    if watch is not None and _dir_bytes(watch) > self.flimits.max_transfer_bytes:
                        _kill_group(proc)
                        raise GitTransferTooLarge("git transfer exceeded the size cap")
                    if max_out is not None and out_path.stat().st_size > max_out:
                        _kill_group(proc)
                        raise GitTransferTooLarge("git output exceeded the size cap")
                    time.sleep(self.flimits.poll_s)
            except BaseException:
                _kill_group(proc)  # cancellation (e.g. KeyboardInterrupt) must not leave git running
                raise
        # Final check: a transfer can finish between two polls; the cap must still hold.
        if watch is not None and _dir_bytes(watch) > self.flimits.max_transfer_bytes:
            raise GitTransferTooLarge("git transfer exceeded the size cap")
        stdout = out_path.read_bytes()
        stderr = err_path.read_bytes()[-4096:].decode("utf-8", "replace")
        out_path.unlink(missing_ok=True)
        err_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise self._classify(args, stderr, auth)
        return stdout

    def _classify(self, args: list[str], stderr: str, auth: tuple[str, str] | None) -> GitFetchError:
        text = stderr
        if auth is not None:
            text = text.replace(auth[1], "[REDACTED]")
        text = redact(text)[-300:].strip()
        low = text.lower()
        name = args_name(args)
        if "authentication failed" in low or "401" in low or "could not read username" in low or "403" in low:
            return GitAuthError(f"git {name}: authentication failed")
        if "not our ref" in low or "couldn't find remote ref" in low or "unadvertised object" in low or "not found" in low:
            return CommitNotFound(f"git {name}: commit not available from the remote")
        return GitFetchError(f"git {name} failed: {text}")


def args_name(args: list[str]) -> str:
    for a in args:
        if a in ("init", "remote", "fetch", "rev-parse", "ls-tree", "cat-file"):
            return a
    return "command"


class GitObjectSource(CodeSource):
    kind = "git"

    def __init__(self, fetcher: GitFetcher, gitdir: Path, ws: Path, head_sha: str, limits: Limits) -> None:
        super().__init__(head_sha, limits)
        self._f, self._gitdir, self._ws = fetcher, gitdir, ws

    def _git(self, args: list[str], stdin: bytes | None = None, max_out: int | None = None) -> bytes:
        return self._f._run_bytes(
            self._f._cfg(self._gitdir) + args,
            self._ws,
            auth=None,
            timeout=self._f.flimits.read_timeout_s,
            stdin=stdin,
            max_out=max_out,
        )

    def _list_tree(self) -> tuple[dict[str, TreeEntry], bool]:
        cap = self.limits.max_entries
        raw = self._git(["ls-tree", "-r", "-z", "--full-tree", "refs/tw/head"], max_out=cap * 1200)
        rows = [r for r in raw.split(b"\x00") if r]
        truncated = len(rows) > cap
        rows = rows[:cap]
        parsed: list[tuple[str, str, str]] = []
        for r in rows:
            meta, _, path_b = r.partition(b"\t")
            mode, _typ, oid = meta.decode().split(" ")
            try:
                path = path_b.decode("utf-8")
            except UnicodeDecodeError:
                continue  # non-UTF-8 names cannot be addressed safely; skipped
            parsed.append((mode, oid, path))
        sizes = self._sizes([oid for mode, oid, _ in parsed if mode != "160000"])
        out: dict[str, TreeEntry] = {}
        for mode, oid, path in parsed:
            kind: EntryKind = "submodule" if mode == "160000" else "symlink" if mode == "120000" else "file"
            out[path] = TreeEntry(path, kind, oid, None if kind == "submodule" else sizes.get(oid))
        return out, truncated

    def _sizes(self, oids: list[str]) -> dict[str, int]:
        if not oids:
            return {}
        raw = self._git(
            ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
            stdin=("\n".join(oids) + "\n").encode(),
            max_out=len(oids) * 80 + 1024,
        )
        sizes: dict[str, int] = {}
        for line in raw.decode().splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[1] == "blob":
                sizes[parts[0]] = int(parts[2])  # "<oid> missing" (filtered blob) → absent → size unknown
        return sizes

    def _read_blob(self, entry: TreeEntry) -> bytes | None:
        try:
            return self._git(["cat-file", "blob", entry.oid], max_out=self.limits.max_file_bytes + 1)
        except GitFetchError:
            return None
