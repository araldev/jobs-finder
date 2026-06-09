"""LinkedIn-specific exceptions.

Spec: REQ-016.

All three subclasses share the same `details: dict[str, Any] | None` shape
so presentation handlers can log them uniformly.

NOTE: `LinkedInParseError` was added in T-005 so the parsers could raise it.
`LinkedInBlockedError` and `LinkedInTimeoutError` are added in T-006 because
the scraper imports them; T-007 will add unit tests covering the hierarchy
without touching the source files.
"""

from __future__ import annotations

from typing import Any

from jobs_finder.domain.exceptions import JobSearchError


def _format(message: str, details: dict[str, Any] | None) -> str:
    if details is not None:
        return f"{message} | details={details}"
    return message


class LinkedInParseError(JobSearchError):
    """Raised when the LinkedIn HTML fragment cannot be parsed into a field."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class LinkedInBlockedError(JobSearchError):
    """Raised when LinkedIn returns an auth-wall / verification / challenge page.

    The presentation layer maps this to HTTP 502 with a masked detail.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class LinkedInTimeoutError(JobSearchError):
    """Raised when the results selector does not appear within `timeout_ms`."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)
