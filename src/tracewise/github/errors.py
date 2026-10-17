"""GitHub error taxonomy, mapped onto the job queue's retry semantics (FS-ERR-2, FS-ERR-3, FS-LOG-3)."""

from __future__ import annotations

from tracewise.jobs.queue import PermanentError, RetryableError


class GitHubRetryable(RetryableError):
    """5xx, network failure or rate limit that outlasts the inline budget; the job is re-queued
    no earlier than `retry_after_s`."""


class GitHubPermanent(PermanentError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NotFound(GitHubPermanent):
    """404. May also mean "no access" for private resources (GitHub docs)."""


class Gone(GitHubPermanent):
    """410 (e.g. logs past retention)."""


class PermissionDenied(GitHubPermanent):
    """403 that is not a rate limit: the installation lacks a permission (FS-ERR-3). No retry loop."""

    def __init__(self, message: str, permission: str | None, status: int = 403) -> None:
        super().__init__(message, status)
        self.permission = permission


class InstallationUnavailable(GitHubPermanent):
    """Token mint refused (401/404/403 on the installation): uninstalled or suspended (FS-INS-3)."""


class TokenScopeError(GitHubPermanent):
    """GitHub granted more (or other) access than requested; fail closed."""


class UnsafeRedirect(GitHubPermanent):
    """A log redirect pointed outside the allowed hosts or was not https."""


class ResponseTooLarge(GitHubPermanent):
    pass
