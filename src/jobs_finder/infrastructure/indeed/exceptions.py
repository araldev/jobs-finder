"""Indeed-specific exceptions.

Spec: REQ-I-010.

All three subclasses share the same `details: dict[str, Any] | None` shape
so presentation handlers can log them uniformly. The shape is a
1:1 mirror of the LinkedIn exceptions module so the presentation
layer can treat both sources symmetrically.
"""

from __future__ import annotations

from typing import Any

from jobs_finder.domain.exceptions import JobSearchError


def _format(message: str, details: dict[str, Any] | None) -> str:
    if details is not None:
        return f"{message} | details={details}"
    return message


class IndeedBlockedError(JobSearchError):
    """Raised when Indeed returns a Cloudflare challenge, 429, 503, or network error.

    The presentation layer maps this to HTTP 502 with a masked detail.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class IndeedParseError(JobSearchError):
    """Raised when the Indeed HTML fragment cannot be parsed into a field.

    Examples: missing `data-jk`, malformed `jk` value, unparseable
    relative-time string, or a card missing a required selector.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class IndeedTimeoutError(JobSearchError):
    """Raised when the results selector does not appear within `timeout_ms`."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)
