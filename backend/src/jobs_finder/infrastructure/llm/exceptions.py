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


class LLMStreamError(LLMUnavailableError):
    """The LLM streaming response could not be parsed (non-200, malformed SSE, etc.).

    Spec: `chat-streaming` change T-001 + design §1 (Stream layer
    mapping). Subclasses `LLMUnavailableError` so the route's
    `isinstance` chain catches the parent first (the 502 fallback)
    and then discriminates the specific subclass to map to the
    `llm_stream` machine code (REQ-ERROR-MAPPING-001).

    Raised by `MiniMaxLLMClient.stream_complete` when:
      - The HTTP status is non-200 (5xx, 429, 401/403, ...).
      - A `data: <json>` line is not valid JSON (malformed SSE).
      - A line lacks the `data: ` prefix when expected (protocol drift).

    The 2 design-level reasons for the SUBCLASS (not a new top-level
    class parallel to `LLMUnavailableError`):
      1. The route's `isinstance` chain must reach the parent
         FIRST so the 502 fallback works as a safety net if the
         specific-subclass branch is ever bypassed.
      2. Both subclasses share the same `cause` kwarg semantics
         (the underlying httpx layer error / JSON error) so a
         single constructor signature keeps the call sites uniform.

    Args:
        message: Human-readable error description (e.g.
            "stream status 500: <body>"). Surfaced in the SSE
            `event: error` `data.message` field and the access log.
        cause: Optional underlying exception. Its `repr()` is
            appended to `str(err)` for log diagnostics (mirrors
            `LLMUnavailableError`).
    """

    __slots__ = ("_cause", "_message")

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        # NOTE: we do NOT call `super().__init__(message)` on
        # `LLMUnavailableError` because the parent class's
        # `__init__` sets the `_cause` and `_message` slots; the
        # most reliable way to share the parent ctor is to
        # delegate directly. We DO call the grand-parent's
        # `__init__(message)` so `args[0]` is the message (the
        # contract the global `JobSearchError` handler reads).
        LLMUnavailableError.__init__(self, message, cause=cause)


class LLMRequestTimeoutError(LLMUnavailableError):
    """The LLM streaming request exceeded the configured timeout.

    Spec: `chat-streaming` change T-001 + design §1 (Stream layer
    mapping). Subclasses `LLMUnavailableError` for the same
    reason as `LLMStreamError` — the route's `isinstance` chain
    discriminates the subclass to map to the `llm_timeout`
    machine code (REQ-ERROR-MAPPING-001).

    Raised by `MiniMaxLLMClient.stream_complete` when the
    underlying `httpx` call raises `httpx.TimeoutException` (or
    `asyncio.TimeoutError`). NO retry mid-stream — the upstream
    request is allowed to complete in the background (the
    proposal's user decision; cost is negligible). The
    `event: error` is emitted and the connection closes.

    Args:
        message: Human-readable error description (e.g.
            "timeout after 15.0s"). Surfaced in the SSE
            `event: error` `data.message` field.
        cause: Optional underlying exception. Its `repr()` is
            appended to `str(err)` for log diagnostics.
    """

    __slots__ = ("_cause", "_message")

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        LLMUnavailableError.__init__(self, message, cause=cause)
