"""LinkedIn-specific exceptions.

Spec: REQ-016.

NOTE: This file is split across two apply commits by design. T-005 lands
`LinkedInParseError` so the parsers can raise it. T-007 adds the remaining
two: `LinkedInBlockedError` and `LinkedInTimeoutError`. Both subclasses
share the same `details: dict[str, Any] | None` shape so presentation
handlers can log them uniformly.
"""

from __future__ import annotations

from typing import Any

from jobs_finder.domain.exceptions import JobSearchError


class LinkedInParseError(JobSearchError):
    """Raised when the LinkedIn HTML fragment cannot be parsed into a field.

    Carries an optional `details` dict (e.g. a snippet of the offending HTML)
    for diagnostics. The default `__str__` includes the message and, when
    present, the `details` payload.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] | None = details

    def __str__(self) -> str:
        msg = self.args[0] if self.args else self.__class__.__name__
        if self.details is not None:
            return f"{msg} | details={self.details}"
        return msg
