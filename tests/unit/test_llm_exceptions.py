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
    LLMResponseParseError,
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
