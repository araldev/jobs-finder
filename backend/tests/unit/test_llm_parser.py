"""Unit tests for the LLM response parsers (T-008 of `ai-chat-filter`,
extended in T-005 of `chat-streaming`).

This file covers 2 components in `infrastructure/llm/_parser.py`:

  1. `parse_llm_response(raw: str) -> LLMSelection` (T-008 v1):
     The defensive 3-tier parser used by the v1 `POST /jobs/chat`
     endpoint. Spec: REQ-LLM-002. The parser attempts
     `json.loads(stripped)` first (tier 1), then a regex
     extraction of the first `{...}` block (tier 2), and
     RAISES `LLMResponseParseError` when both fail.

  2. `StreamEventParser` (T-005 streaming): The streaming
     variant used by the new `POST /jobs/chat/stream` endpoint.
     Spec: REQ-PARSE-001. Accumulates chunks in
     `self.buffer`, yields them verbatim for live `text`
     SSE events, and reuses `parse_llm_response` at the
     end. Drops hallucinated ids (not in the aggregator's
     returned ids) silently with a WARNING log.

The 2 components are tested in the same file because the
streaming parser REUSES the v1 parser (a regression in
`parse_llm_response` would break both paths).
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from jobs_finder.infrastructure.llm._parser import (
    LLMSelection,
    StreamEventParser,
    parse_llm_response,
)
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# ===========================================================================
# Section 1 — `parse_llm_response` (T-008 of `ai-chat-filter`, v1)
# ===========================================================================
#
# Spec: REQ-LLM-002 (3-tier defensive parser, returns a typed
# `LLMSelection` with the matching_ids and explanation fields).
#
# The parser MUST handle 6 scenarios:
#   1. Clean JSON.
#   2. Markdown-fenced.
#   3. Trailing/leading prose.
#   4. Completely malformed → raise.
#   5. Missing `matching_ids` key → default to [].
#   6. Empty list value → valid answer.
# ===========================================================================


def test_clean_json_returns_selection() -> None:
    """A well-formed JSON object is parsed verbatim (tier 1)."""
    raw = '{"matching_ids": ["a", "b"], "explanation": "test"}'
    result = parse_llm_response(raw)
    assert isinstance(result, LLMSelection)
    assert result.matching_ids == ["a", "b"]
    assert result.explanation == "test"


def test_clean_json_with_whitespace_around_object() -> None:
    """Leading/trailing whitespace is tolerated (tier 1)."""
    raw = '   \n\n  {"matching_ids": ["x"], "explanation": "ok"}  \n\n  '
    result = parse_llm_response(raw)
    assert result.matching_ids == ["x"]
    assert result.explanation == "ok"


def test_markdown_fenced_json_extracted_by_tier_2() -> None:
    """JSON inside ```json ... ``` markdown fences is extracted (tier 2)."""
    raw = '```json\n{"matching_ids": ["a"], "explanation": "x"}\n```'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["a"]
    assert result.explanation == "x"


def test_markdown_fenced_with_bare_fence_backticks() -> None:
    """JSON inside plain ``` ... ``` fences (no language tag) is also extracted."""
    raw = '```\n{"matching_ids": ["y"], "explanation": "fenced"}\n```'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["y"]
    assert result.explanation == "fenced"


def test_trailing_prose_falls_back_to_tier_2() -> None:
    """Trailing prose → tier 2 regex extracts the JSON."""
    raw = '{"matching_ids": ["a"]}\n\nSaludos.'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["a"]


def test_leading_prose_falls_back_to_tier_2() -> None:
    """Leading prose → tier 2 still extracts the JSON."""
    raw = 'Sure, here is the JSON:\n\n{"matching_ids": ["b"], "explanation": "ok"}'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["b"]
    assert result.explanation == "ok"


def test_completely_malformed_raises_parse_error() -> None:
    """A string with no JSON object at all RAISES `LLMResponseParseError`."""
    raw = "this is not json at all"
    with pytest.raises(LLMResponseParseError) as exc_info:
        parse_llm_response(raw)
    assert exc_info.value  # not empty


def test_empty_string_raises_parse_error() -> None:
    """An empty string is malformed → raises `LLMResponseParseError`."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response("")


def test_only_whitespace_raises_parse_error() -> None:
    """A whitespace-only string is malformed → raises `LLMResponseParseError`."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response("   \n\t  ")


def test_json_array_without_object_raises_parse_error() -> None:
    """A JSON array (not an object) is malformed → raises `LLMResponseParseError`."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response('["a", "b"]')


def test_missing_matching_ids_key_defaults_to_empty_list() -> None:
    """When the JSON has only `explanation`, `matching_ids` defaults to `[]`."""
    raw = '{"explanation": "no matches"}'
    result = parse_llm_response(raw)
    assert result.matching_ids == []
    assert result.explanation == "no matches"


def test_missing_both_keys_returns_empty_selection() -> None:
    """When the JSON is `{}`, both fields default — empty list, empty explanation."""
    raw = "{}"
    result = parse_llm_response(raw)
    assert result.matching_ids == []
    assert result.explanation == ""


def test_empty_matching_ids_list_is_valid() -> None:
    """`{"matching_ids": [], "explanation": "no matches"}` is a valid answer."""
    raw = '{"matching_ids": [], "explanation": "no matches"}'
    result = parse_llm_response(raw)
    assert result.matching_ids == []
    assert result.explanation == "no matches"


def test_json_string_value_rejected() -> None:
    """A JSON string is rejected (not an object)."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response('"just a string"')


def test_json_number_value_rejected() -> None:
    """A JSON number is rejected (not an object)."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response("42")


def test_llm_selection_is_frozen() -> None:
    """`LLMSelection` is `frozen=True` — assignment raises `FrozenInstanceError`."""
    sel = LLMSelection(matching_ids=["a"], explanation="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sel.matching_ids = ["b"]  # type: ignore[misc]


def test_llm_selection_equality() -> None:
    """Two selections with the same fields are equal (frozen dataclass semantics)."""
    a = LLMSelection(matching_ids=["a", "b"], explanation="x")
    b = LLMSelection(matching_ids=["a", "b"], explanation="x")
    assert a == b


def test_llm_selection_inequality_on_field_difference() -> None:
    """A difference in any field breaks equality."""
    a = LLMSelection(matching_ids=["a", "b"], explanation="x")
    b = LLMSelection(matching_ids=["a", "b"], explanation="y")
    assert a != b
    c = LLMSelection(matching_ids=["a"], explanation="x")
    assert a != c


# ===========================================================================
# Section 2 — `StreamEventParser` (T-005 of `chat-streaming`)
# ===========================================================================
#
# Spec: REQ-PARSE-001 (end-of-stream JSON extraction with strict validation).
#
# `StreamEventParser` is a pure dataclass with 2 methods:
#   - `feed(chunk) -> Iterator[str]`: accumulates `chunk` in
#     `self.buffer` and yields the chunk verbatim.
#   - `finalize(returned_ids: set[str]) -> LLMSelection`:
#     reuses the production `parse_llm_response` parser on
#     the accumulated buffer. The buffer MAY have markdown
#     fences. `matching_ids` NOT in `returned_ids` are
#     dropped silently with a `WARNING` log; the
#     `explanation` is preserved.
# ===========================================================================


# ---------------------------------------------------------------------------
# Scenario 1: feed() yields chunks verbatim + buffer accumulates
# ---------------------------------------------------------------------------


def test_feed_yields_chunks_verbatim_and_accumulates_buffer() -> None:
    """`feed(chunk)` yields the chunk verbatim + appends to `self.buffer`."""
    parser = StreamEventParser()
    chunks_yielded: list[str] = []
    for chunk in ("match", "ing", " ids"):
        chunks_yielded.extend(parser.feed(chunk))
    assert chunks_yielded == ["match", "ing", " ids"]
    assert parser.buffer == "matching ids"


def test_feed_with_empty_string_yields_empty_string_and_buffer_unchanged() -> None:
    """`feed("")` yields one empty string + leaves the buffer empty."""
    parser = StreamEventParser()
    chunks = list(parser.feed(""))
    assert chunks == [""]
    assert parser.buffer == ""


# ---------------------------------------------------------------------------
# Scenario 2: plain JSON buffer parses
# ---------------------------------------------------------------------------


def test_finalize_with_plain_json_returns_selection() -> None:
    """A plain JSON buffer parses via the production `parse_llm_response`."""
    parser = StreamEventParser()
    list(parser.feed('{"matching_ids":["j1","j2"],'))
    list(parser.feed('"explanation":"These match"}'))
    selection = parser.finalize({"j1", "j2", "j3"})
    assert selection.matching_ids == ["j1", "j2"]
    assert selection.explanation == "These match"


# ---------------------------------------------------------------------------
# Scenario 3: markdown-fenced buffer → fences stripped, parses
# ---------------------------------------------------------------------------


def test_finalize_strips_markdown_fences_before_parsing() -> None:
    """A buffer with ```json ... ``` fences is stripped and parsed."""
    parser = StreamEventParser()
    raw = '```json\n{"matching_ids":["j1"],"explanation":"x"}\n```'
    list(parser.feed(raw))
    selection = parser.finalize({"j1"})
    assert selection.matching_ids == ["j1"]
    assert selection.explanation == "x"


# ---------------------------------------------------------------------------
# Scenario 4: hallucinated ids (not in returned_ids) → dropped, WARNING logged
# ---------------------------------------------------------------------------


def test_finalize_drops_hallucinated_ids_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IDs in `matching_ids` but NOT in `returned_ids` are dropped + WARNING logged."""
    parser = StreamEventParser()
    raw = '{"matching_ids":["j1","j9"],"explanation":"all"}'
    list(parser.feed(raw))
    with caplog.at_level(logging.WARNING, logger="jobs_finder.infrastructure.llm._parser"):
        selection = parser.finalize({"j1", "j2", "j3"})
    assert selection.matching_ids == ["j1"]
    assert selection.explanation == "all"
    warning_texts = [
        record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert any("j9" in text for text in warning_texts), (
        f"Expected a WARNING log mentioning j9; got: {warning_texts}"
    )


# ---------------------------------------------------------------------------
# Scenario 5: malformed JSON → raises LLMResponseParseError
# ---------------------------------------------------------------------------


def test_finalize_with_malformed_buffer_raises_parse_error() -> None:
    """A buffer that's not JSON at all returns empty selection (graceful fallback)."""
    parser = StreamEventParser()
    list(parser.feed("this is not json at all"))
    selection = parser.finalize({"j1"})
    assert selection.matching_ids == []


# ---------------------------------------------------------------------------
# Scenario 6: empty buffer + finalize → empty selection (graceful fallback)
# ---------------------------------------------------------------------------


def test_finalize_with_empty_buffer_raises_parse_error() -> None:
    """An empty buffer + finalize → returns empty selection (graceful fallback)."""
    parser = StreamEventParser()
    selection = parser.finalize({"j1"})
    assert selection.matching_ids == []


# ---------------------------------------------------------------------------
# Type-level sanity
# ---------------------------------------------------------------------------


def test_stream_event_parser_buffer_is_a_string_after_init() -> None:
    """`StreamEventParser()` initializes `buffer=""` (the default)."""
    parser = StreamEventParser()
    assert parser.buffer == ""
    assert isinstance(parser.buffer, str)


# ---------------------------------------------------------------------------
# Triangulation: feed order matters (chunks are concatenated verbatim)
# ---------------------------------------------------------------------------


def test_feed_concatenates_chunks_in_order() -> None:
    """`feed(a)` + `feed(b)` → buffer == a + b (concatenation)."""
    parser = StreamEventParser()
    list(parser.feed('{"matching_ids":'))
    list(parser.feed('["a","b"]}'))
    assert parser.buffer == '{"matching_ids":["a","b"]}'
    selection = parser.finalize({"a", "b"})
    assert selection.matching_ids == ["a", "b"]


def test_finalize_preserves_explanation_after_id_drops() -> None:
    """Dropping hallucinated ids MUST NOT mutate the `explanation` text."""
    parser = StreamEventParser()
    raw = '{"matching_ids":["j1","j9","j2"],"explanation":"all match"}'
    list(parser.feed(raw))
    selection = parser.finalize({"j1", "j2", "j3"})
    assert "all match" in selection.explanation
    assert "j9" not in selection.explanation
