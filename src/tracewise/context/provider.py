"""Open the code context for one analysis (T-304): Git objects first, Contents API fallback,
otherwise an explicit unavailable result. The workspace lives exactly as long as the `with` block."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

from tracewise.context.contents_api import ContentsApiSource
from tracewise.context.gitfetch import GitFetcher, GitFetchError
from tracewise.context.paths import UnsafePath, validate_sha
from tracewise.context.source import CodeSource, Limits, UnavailableSource
from tracewise.github import errors as gh_err
from tracewise.github.client import RepoClient

log = logging.getLogger(__name__)


@contextlib.contextmanager
def open_code_context(
    rc: RepoClient, head_sha: str, *, fetcher: GitFetcher | None, limits: Limits | None = None
) -> Iterator[CodeSource]:
    """`rc` must be an analysis-scope client bound to the run's repository."""
    try:
        validate_sha(head_sha)
    except UnsafePath:
        yield UnavailableSource(head_sha, "invalid commit SHA")
        return
    git_error: str | None = None
    with contextlib.ExitStack() as stack:
        source: CodeSource | None = None
        if fetcher is not None:
            try:
                git_src = stack.enter_context(fetcher.fetch(rc.full_name, head_sha, rc.git_fetch_token()))
                git_src.entries()  # list inside the workspace lifetime; fail over if listing fails
                source = git_src
            except GitFetchError as e:
                stack.close()  # remove the failed workspace before falling back
                git_error = type(e).__name__
                log.warning("git fetch failed; falling back to the contents API", extra={"tw": {"error": git_error}})
            except gh_err.GitHubPermanent as e:  # token mint refused
                stack.close()
                git_error = type(e).__name__
        if source is None:
            api = ContentsApiSource(rc, head_sha, limits)
            try:
                api.entries()
                source = api
            except (gh_err.GitHubPermanent, gh_err.GitHubRetryable) as e:
                reason = f"git: {git_error or 'not attempted'}; contents API: {type(e).__name__}"
                log.warning("code context unavailable", extra={"tw": {"reason": reason}})
                source = UnavailableSource(head_sha, reason)
        log.info("code context opened", extra={"tw": {"kind": source.kind}})
        # Exceptions raised by the caller propagate from here; the ExitStack removes the workspace.
        yield source
