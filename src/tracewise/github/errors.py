"""GitHub error taxonomy, mapped onto the job queue's retry semantics (FS-ERR-2, FS-ERR-3, FS-LOG-3)."""

from __future__ import annotations

from tracewise.jobs.queue import PermanentError, RetryableError


class GitHubRetryable(RetryableError):
    """5xx, network failure or rate limit that outlasts the inline budget; the job is re-queued
    no earlier than `retry_after_s`."""


class DeadlineExhausted(GitHubRetryable):
    """O-2: the attempt's remaining time is too short to start (or repeat) a request. `sent` is False when no request
    of this call reached GitHub, so nothing can have been applied; True when an earlier try of the same call was sent
    (its outcome is unknown, exactly as for a timeout)."""

    def __init__(self, message: str, *, sent: bool = False) -> None:
        super().__init__(message)
        self.sent = sent


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
    """Token mint refused on the installation (404, or a 403 that is not a rate limit): uninstalled or suspended
    (FS-INS-3). Also a fresh installation token that is still rejected (401 after a successful re-mint)."""


class AppAuthenticationFailed(GitHubPermanent):
    """GitHub rejected the App JWT itself (401 on an App-JWT call such as the token mint): a wrong, deleted or
    mismatched private key, a wrong App ID, or clock skew. An operator fault, never an uninstall, so it is
    deliberately not an `InstallationUnavailable`: the job ends `dead` and counts as a failure (no publication is
    possible without a token)."""


class TokenScopeError(GitHubPermanent):
    """GitHub granted more (or other) access than requested; fail closed."""


class UnsafeRedirect(GitHubPermanent):
    """A log redirect pointed outside the allowed hosts or was not https."""


class ResponseTooLarge(GitHubPermanent):
    pass
