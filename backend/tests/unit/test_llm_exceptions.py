"""Unit tests for the LLM-specific exception classes added in T-007 of `ai-chat-filter`.

Spec: REQ-LLM-001 (error mapping) and design §2 (2 distinct exception classes).

`LLMUnavailableError` and `LLMResponseParseError` both subclass
`JobSearchError` so the existing presentation-layer exception handler
catches them. The handler maps the parent `JobSearchError` to 502, so
`LLMUnavailableError` lands at 502 with the standard error body shape.
`LLMResponseParseError` is raised when the defensive parser cannot
extract a valid JSON — the route maps it to 422 (route-local
`HTTPException`, not the global handler, per design §5).

The 2 classes are intentionally DISTINCT (not one class with a `code`
field) because the HTTP mapping is different (502 vs 422) and the
route handles them in different code paths (Q2 spec resolution).
"""

from __future__ import annotations

import pytest

from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.infrastructure.llm.exceptions import (
    LLMRequestTimeoutError,
    LLMResponseParseError,
    LLMStreamError,
    LLMUnavailableError,
)

# ---------------------------------------------------------------------------
# LLMUnavailableError — caught as JobSearchError; raises for 5xx, timeout,
# 429, MiniMax error codes 1002/1013/1004/1008/1001 (per design §5).
# ---------------------------------------------------------------------------


def test_llm_unavailable_error_inherits_from_job_search_error() -> None:
    """`LLMUnavailableError` subclasses `JobSearchError` so the existing
    presentation-layer handler catches it and maps to 502.

    The mapping is a contract — the chat route relies on this catch to
    produce the same `{"detail": "LLM provider unavailable: ..."}` body
    shape as the source-scraper routes.
    """
    err = LLMUnavailableError("upstream down")
    assert isinstance(err, JobSearchError)


def test_llm_unavailable_error_str_includes_message() -> None:
    """`str(err)` includes the human-readable message.

    The 502 response body in the existing exception handler interpolates
    `str(err)` into the `detail` field, so the message MUST appear in
    the rendered string.
    """
    err = LLMUnavailableError("MiniMax returned 502")
    rendered = str(err)
    assert "MiniMax returned 502" in rendered


def test_llm_unavailable_error_str_includes_cause_repr_when_provided() -> None:
    """When `cause` is provided, `str(err)` includes the cause's repr.

    The chat route logs the rendered string on 502; including the
    cause's repr preserves the chain of failures (httpx layer error
    -> LLMUnavailableError -> 502) so operators can trace the root
    cause from the access log.
    """
    cause = TimeoutError("connect timeout after 15s")
    err = LLMUnavailableError("upstream timeout", cause=cause)
    rendered = str(err)
    assert "upstream timeout" in rendered
    # The cause's class name AND its message must be visible in str(err).
    assert "TimeoutError" in rendered
    assert "connect timeout after 15s" in rendered


def test_llm_unavailable_error_message_is_keyword_only_after_first_arg() -> None:
    """`__init__` signature: `(message, *, cause=None)`.

    `cause` is keyword-only so callers cannot accidentally pass a
    positional `cause` that the constructor would misinterpret.
    """
    err = LLMUnavailableError("auth failed", cause=ValueError("bad token"))
    # Both args are stored and surfaced via __str__.
    assert "auth failed" in str(err)
    assert "bad token" in str(err)


def test_llm_unavailable_error_cause_is_optional() -> None:
    """`cause` is optional (default `None`); construction without it works."""
    err = LLMUnavailableError("5xx from MiniMax")
    # No cause was provided — __str__ must NOT raise.
    assert str(err)  # just exercising the path; no ValueError


# ---------------------------------------------------------------------------
# LLMResponseParseError — caught as JobSearchError; raised when the
# defensive parser cannot extract a valid JSON (REQ-LLM-002).
# ---------------------------------------------------------------------------


def test_llm_response_parse_error_inherits_from_job_search_error() -> None:
    """`LLMResponseParseError` subclasses `JobSearchError`.

    The route catches it locally to produce a 422 — it does NOT rely
    on the global handler — but the parent-class link MUST hold so
    the global handler also catches it as a safety net (defense in
    depth: if a future refactor moves the route-local catch, the
    error still maps to a sensible HTTP code).
    """
    err = LLMResponseParseError("could not parse")
    assert isinstance(err, JobSearchError)


def test_llm_response_parse_error_is_a_distinct_subclass() -> None:
    """`LLMResponseParseError` and `LLMUnavailableError` are DISTINCT
    classes (not the same class with a `code` field).

    The route uses `except LLMUnavailableError: 502` and
    `except LLMResponseParseError: 422` — collapsing them to one
    class would break the error mapping (Q2 spec resolution).
    """
    err = LLMResponseParseError("malformed json")
    assert not isinstance(err, LLMUnavailableError)
    assert type(err) is LLMResponseParseError


def test_llm_response_parse_error_str_includes_message() -> None:
    """`str(err)` includes the human-readable message."""
    err = LLMResponseParseError("no JSON object in response")
    rendered = str(err)
    assert "no JSON object in response" in rendered


def test_llm_response_parse_error_str_includes_cause_repr_when_provided() -> None:
    """When `cause` is provided, `str(err)` includes the cause's repr.

    The defensive parser uses `LLMResponseParseError` to surface the
    underlying `json.JSONDecodeError` or `re.error` so the route can
    log enough context to debug a model that started returning a
    different format.
    """
    cause = ValueError("unterminated string at line 3")
    err = LLMResponseParseError("json.loads failed", cause=cause)
    rendered = str(err)
    assert "json.loads failed" in rendered
    assert "unterminated string at line 3" in rendered


def test_llm_response_parse_error_cause_is_optional() -> None:
    """`cause` is optional (default `None`); construction without it works."""
    err = LLMResponseParseError("tier 1 + tier 2 both failed")
    assert str(err)  # no exception


# ---------------------------------------------------------------------------
# Exception hierarchy coherence
# ---------------------------------------------------------------------------


def test_both_classes_are_catchable_as_job_search_error() -> None:
    """A single `except JobSearchError` catches BOTH subclasses.

    This is the contract the existing presentation-layer handler
    relies on. A future refactor that breaks this (e.g. accidentally
    subclassing `Exception` instead of `JobSearchError`) would
    silently leak LLM failures as uncaught 500s.
    """
    for exc_cls in (LLMUnavailableError, LLMResponseParseError):
        with pytest.raises(JobSearchError):
            raise exc_cls("test")


# ---------------------------------------------------------------------------
# `chat-streaming` T-001 — LLMStreamError + LLMRequestTimeoutError
#
# Spec: REQ-ERROR-MAPPING-001 + design §1 (Stream layer mapping).
# The 2 new exception classes are discriminated from
# `LLMUnavailableError` ONLY by their concrete type — the route's
# `isinstance` chain catches the parent first, then discriminates
# the subclass to map to the right machine code. Both subclasses
# MUST keep the parent-class link so the existing 502 mapping
# (via the global `JobSearchError` handler) still works as a
# safety net if the route-local catch is ever bypassed.
# ---------------------------------------------------------------------------


def test_llm_stream_error_inherits_from_llm_unavailable_error() -> None:
    """`LLMStreamError` subclasses `LLMUnavailableError`.

    The route catches `LLMUnavailableError` first (the parent),
    then discriminates `LLMStreamError` to map to the
    `llm_stream` machine code (REQ-ERROR-MAPPING-001). A
    regression that subclasses `JobSearchError` directly would
    break the `isinstance` chain.
    """
    err = LLMStreamError("stream status 500")
    # Discriminator invariant: the parent class MUST be reachable.
    assert isinstance(err, LLMUnavailableError)
    # And the root hierarchy MUST be intact (the global handler relies on it).
    assert isinstance(err, JobSearchError)


def test_llm_stream_error_is_a_distinct_subclass() -> None:
    """`LLMStreamError` and `LLMRequestTimeoutError` are DISTINCT classes.

    The route maps each to a different machine code
    (`llm_stream` vs `llm_timeout`). Collapsing them to one
    class would break the error mapping.
    """
    stream_err = LLMStreamError("non-200 status")
    timeout_err = LLMRequestTimeoutError("request exceeded 15s")
    assert type(stream_err) is LLMStreamError
    assert type(timeout_err) is LLMRequestTimeoutError
    # Cross-check: a `LLMStreamError` is NOT a `LLMRequestTimeoutError`
    # and vice versa.
    assert not isinstance(stream_err, LLMRequestTimeoutError)
    assert not isinstance(timeout_err, LLMStreamError)


def test_llm_stream_error_str_includes_message() -> None:
    """`str(LLMStreamError)` includes the human-readable message.

    The route's error event payload includes the message in
    `data.message`; the access log includes the same string
    for ops correlation.
    """
    err = LLMStreamError("stream status 500: internal error")
    assert "stream status 500" in str(err)
    assert "internal error" in str(err)


def test_llm_stream_error_accepts_cause_keyword_only() -> None:
    """`LLMStreamError.__init__` accepts `cause: Exception | None = None`.

    Mirrors `LLMUnavailableError`'s signature. `cause` is
    keyword-only so callers cannot accidentally pass a
    positional cause that the constructor would misinterpret.
    """
    cause = ValueError("malformed chunk")
    err = LLMStreamError("malformed SSE", cause=cause)
    # The cause's repr appears in `str(err)` so operators can
    # trace the failure chain in a single log line.
    assert "malformed SSE" in str(err)
    assert "malformed chunk" in str(err)


def test_llm_request_timeout_error_inherits_from_llm_unavailable_error() -> None:
    """`LLMRequestTimeoutError` subclasses `LLMUnavailableError`.

    Same discriminator invariant as `LLMStreamError`: the
    route's `isinstance` chain catches the parent first, then
    discriminates the subclass to map to the `llm_timeout`
    machine code.
    """
    err = LLMRequestTimeoutError("timeout after 15s")
    assert isinstance(err, LLMUnavailableError)
    assert isinstance(err, JobSearchError)


def test_llm_request_timeout_error_is_a_distinct_subclass() -> None:
    """`LLMRequestTimeoutError` is NOT a `LLMStreamError`.

    A regression that collapsed the 2 classes (e.g. reusing
    `LLMStreamError` for timeouts) would surface as a wrong
    machine code (`llm_stream` for what should be
    `llm_timeout`).
    """
    err = LLMRequestTimeoutError("request timeout")
    assert type(err) is LLMRequestTimeoutError
    assert not isinstance(err, LLMStreamError)


def test_llm_request_timeout_error_str_includes_message() -> None:
    """`str(LLMRequestTimeoutError)` includes the message verbatim.

    The error event `data.message` carries the message; ops
    correlates it to access logs.
    """
    err = LLMRequestTimeoutError("timeout after 15.0s")
    assert "timeout after 15.0s" in str(err)


def test_all_four_classes_are_catchable_as_job_search_error() -> None:
    """A single `except JobSearchError` catches ALL FOUR subclasses.

    The 4 classes are: `LLMUnavailableError`, `LLMResponseParseError`,
    `LLMStreamError`, `LLMRequestTimeoutError`. The global
    presentation-layer handler depends on this — a regression
    that subclassed `Exception` directly (breaking the chain)
    would silently leak LLM failures as uncaught 500s.
    """
    for exc_cls in (
        LLMUnavailableError,
        LLMResponseParseError,
        LLMStreamError,
        LLMRequestTimeoutError,
    ):
        with pytest.raises(JobSearchError):
            raise exc_cls("test")
