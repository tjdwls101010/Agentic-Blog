"""Typed package errors and the canonical command exit-code mapping."""

from __future__ import annotations

from .redact import redact_diagnostic


class AgenticBlogError(Exception):
    """Base class for every error raised by this package."""

    def __init__(self, message: object = "") -> None:
        self._raw_diagnostic = str(message)
        super().__init__(redact_diagnostic(self._raw_diagnostic))

    def diagnostic_message(self, *, redact: bool = True, max_length: int = 240) -> str:
        """Return the bounded default diagnostic or the explicit opt-out value."""
        return (
            redact_diagnostic(self._raw_diagnostic, max_length=max_length)
            if redact
            else self._raw_diagnostic
        )


class InvalidIdentifierError(AgenticBlogError, ValueError):
    """A blog, post, or directory identifier could not be normalized."""


class RateLimitedError(AgenticBlogError):
    """Naver rejected a request with HTTP 429.

    No other block signature is classified as rate limiting until it is measured.
    """

    def __init__(
        self, message: str = "Naver rate limited this request.", *, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EnvelopeParseError(AgenticBlogError):
    """A JSON response no longer has the expected envelope structure."""


class BodyParseError(AgenticBlogError):
    """A post or in-blog-search HTML response no longer has the expected structure."""


class NotFoundError(AgenticBlogError):
    """The requested blog, post, or topic does not exist."""


class TargetUnavailableError(AgenticBlogError):
    """A target exists but cannot be read anonymously."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or f"Target is unavailable to anonymous readers: {reason}.")


_EXIT_CODE_SPEC = (
    (0, "success", ()),
    (
        1,
        "usage error, invalid identifier, or unexpected failure",
        (AgenticBlogError,),
    ),
    (3, "blocked or throttled by Naver", (RateLimitedError,)),
    (4, "Naver response structure changed", (EnvelopeParseError, BodyParseError)),
    (
        5,
        "target does not exist or is unavailable anonymously",
        (NotFoundError, TargetUnavailableError),
    ),
)

EXIT_CODES = {code: description for code, description, _ in _EXIT_CODE_SPEC}


def exit_code_for(error: BaseException) -> int:
    """Return the command exit code for an exception; exit 2 remains unassigned."""
    for code, _, error_types in reversed(_EXIT_CODE_SPEC):
        if error_types and isinstance(error, error_types):
            return code
    return next(code for code, _, error_types in _EXIT_CODE_SPEC if AgenticBlogError in error_types)
