"""InfoJobs-specific exceptions.

Spec: REQ-J-001..J-006 (partial — exceptions are a building block, not
a user-facing requirement on their own; the consuming scraper code
lands in T-006).

All three subclasses share the same `details: dict[str, Any] | None`
shape so presentation handlers can log them uniformly. The shape is
a 1:1 mirror of the LinkedIn and Indeed exception modules so the
presentation layer can treat all three sources symmetrically.
"""

from __future__ import annotations

from typing import Any

from jobs_finder.domain.exceptions import JobSearchError


def _format(message: str, details: dict[str, Any] | None) -> str:
    if details is not None:
        return f"{message} | details={details}"
    return message


class InfoJobsBlockedError(JobSearchError):
    """Raised when InfoJobs returns a Distil / Geetest challenge, 403, 503, or network error.

    The InfoJobs anti-bot surface (Distil Networks + Geetest) is stricter
    than Indeed's Cloudflare: the very first request from a clean
    browser can be challenged. The presentation layer maps this to
    HTTP 502 with a masked detail.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class InfoJobsParseError(JobSearchError):
    """Raised when the InfoJobs HTML fragment cannot be parsed into a field.

    Examples: missing `data-offer-id` style attribute, malformed offer
    id value, unparseable relative-time string, or a card missing a
    required selector.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)


class InfoJobsTimeoutError(JobSearchError):
    """Raised when the results selector does not appear within `timeout_ms`."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        return _format(msg, self.details)
