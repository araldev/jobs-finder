"""LLM-specific exception types for the chat filter (T-007 of `ai-chat-filter`).

Spec: REQ-LLM-001 (error mapping) and design §2 (2 distinct classes).

Two LLM-specific exception classes are defined here, both subclassing
`JobSearchError` so the existing presentation-layer exception
handler catches them. The handler maps the parent `JobSearchError`
to 502, so `LLMUnavailableError` lands at 502 with the standard
error body shape (`{"detail": "LLM provider unavailable: <msg>",
"request_id": "..."}`). `LLMResponseParseError` is raised when the
defensive parser cannot extract a valid JSON — the route maps it
to 422 via a route-local `HTTPException` (NOT the global handler,
per design §5).

The 2 classes are intentionally DISTINCT (NOT one class with a
`code` field) because:
  1. The HTTP mapping is different (502 vs 422).
  2. The route handles them in different code paths.
  3. Q2 spec resolution: the simpler two-class design was preferred
     over the single-class-with-code alternative.

Both classes accept an optional `cause: Exception | None = None`
keyword-only arg. When provided, `__str__` interpolates the cause's
repr so operators can trace the chain of failures (e.g. the
underlying httpx layer error that triggered the `LLMUnavailableError`)
from a single log line. The `cause` is NOT stored as a Python
exception chain (i.e. we do NOT use `raise ... from cause`) because
the route catches the LLM class and the original cause's message
is preserved in the rendered string instead. This keeps the
exception classes flat and predictable.
"""

from __future__ import annotations

from jobs_finder.domain.exceptions import JobSearchError


class LLMUnavailableError(JobSearchError):
    """The LLM provider is unavailable.

    Raised on 5xx, timeout, 429, and MiniMax error codes 1002/1013
    (after retry exhaustion) and 1004/1008/1001 (no retry). The
    presentation layer maps this to HTTP 502 via the existing
    `jobsearch_error_handler` (the parent class is `JobSearchError`).

    Args:
        message: Human-readable error description. Surfaced in the
            HTTP 502 response body via `str(err)` interpolation.
        cause: Optional underlying exception (httpx layer, JSON
            decode, etc.). Its `repr()` is appended to `str(err)` so
            operators can see the full failure chain in a single
            log line. NOT stored as a Python exception chain
            (no `raise ... from cause`) because the rendered string
            already preserves the info and the route catches this
            class by its concrete type, not by chaining.
    """

    __slots__ = ("_cause", "_message")

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self._message = message
        self._cause = cause

    def __str__(self) -> str:
        if self._cause is None:
            return self._message
        return f"{self._message} (cause: {self._cause!r})"


class LLMResponseParseError(JobSearchError):
    """The LLM response could not be parsed into a valid selection.

    Raised by the defensive parser (T-008) when both the
    `json.loads` tier AND the regex-extraction tier fail. The chat
    route catches this LOCALLY to map to HTTP 422 (NOT via the
    global `JobSearchError` handler) because the defensive parser
    is designed to never raise — this class is reserved for the
    rare "model returned something unparseable" edge case.

    Args:
        message: Human-readable error description (e.g. "no JSON
            object in response", "tier 1 + tier 2 both failed").
            Surfaced in the HTTP 422 response body.
        cause: Optional underlying exception (`json.JSONDecodeError`,
            `re.error`, etc.). Its `repr()` is appended to
            `str(err)` for log diagnostics.
    """

    __slots__ = ("_cause", "_message")

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self._message = message
        self._cause = cause

    def __str__(self) -> str:
        if self._cause is None:
            return self._message
        return f"{self._message} (cause: {self._cause!r})"
