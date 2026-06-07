"""Unit tests for the defensive `parse_llm_response` parser (T-008 of `ai-chat-filter`).

Spec: REQ-LLM-002 (3-tier defensive parser, returns a typed
`LLMSelection` with the matching_ids and explanation fields).

The parser MUST handle 6 scenarios:

  1. Clean JSON: `'{"matching_ids": ["a"], "explanation": "ok"}'` →
     `LLMSelection(["a"], "ok")` (tier 1 succeeds).
  2. Markdown-fenced: `` ```json\\n{"matching_ids":["a"]}\\n``` `` →
     tier 2 regex extracts the JSON object from inside the fences.
  3. Trailing prose: `'{"matching_ids":["a"]}\\n\\nSaludos.'` →
     tier 1 fails (whole string is not valid JSON), tier 2 regex
     extracts the first `{...}` block.
  4. Completely malformed: `'not json at all'` → both tiers fail,
     `LLMResponseParseError` raised.
  5. Missing `matching_ids` key: `'{"explanation":"none"}'` → returns
     `LLMSelection([], "none")` (the field is OPTIONAL, defaults to []).
  6. Empty list: `'{"matching_ids":[],"explanation":"none"}'` → returns
     `LLMSelection([], "none")` (zero matches is a valid answer).

The design decision is to RAISE on tier-1+tier-2 failure (not return
an empty `LLMSelection`). The route maps `LLMResponseParseError` to
HTTP 422; the defensive fallback to `[]` would mask a real model
malfunction and silently produce empty results.
"""

from __future__ import annotations

import dataclasses

import pytest

from jobs_finder.infrastructure.llm._parser import LLMSelection, parse_llm_response
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# ---------------------------------------------------------------------------
# Scenario 1: clean JSON
# ---------------------------------------------------------------------------


def test_clean_json_returns_selection() -> None:
    """A well-formed JSON object is parsed verbatim (tier 1).

    `'{"matching_ids": ["a", "b"], "explanation": "test"}'`
    → `LLMSelection(["a", "b"], "test")`
    """
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


# ---------------------------------------------------------------------------
# Scenario 2: markdown-fenced
# ---------------------------------------------------------------------------


def test_markdown_fenced_json_extracted_by_tier_2() -> None:
    """JSON inside ```json ... ``` markdown fences is extracted (tier 2).

    Tier 1 (`json.loads` on the whole string) fails because the
    fenced text is not valid JSON. Tier 2 regex extracts the first
    `{...}` block, which IS valid JSON, and parses it.
    """
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


# ---------------------------------------------------------------------------
# Scenario 3: trailing prose
# ---------------------------------------------------------------------------


def test_trailing_prose_falls_back_to_tier_2() -> None:
    """When the model appends a 'Saludos.' after the JSON, tier 1 fails
    (the whole string is not valid JSON), tier 2 regex extracts the
    first balanced `{...}` block.
    """
    raw = '{"matching_ids": ["a"]}\n\nSaludos.'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["a"]


def test_leading_prose_falls_back_to_tier_2() -> None:
    """When the model prepends prose, tier 2 still extracts the JSON."""
    raw = 'Sure, here is the JSON:\n\n{"matching_ids": ["b"], "explanation": "ok"}'
    result = parse_llm_response(raw)
    assert result.matching_ids == ["b"]
    assert result.explanation == "ok"


# ---------------------------------------------------------------------------
# Scenario 4: completely malformed — RAISE
# ---------------------------------------------------------------------------


def test_completely_malformed_raises_parse_error() -> None:
    """A string with no JSON object at all RAISES `LLMResponseParseError`.

    The design decision is to RAISE on tier-1+tier-2 failure (not
    return an empty selection). The route maps the exception to
    HTTP 422; silently returning an empty selection would mask a
    real model malfunction.
    """
    raw = "this is not json at all"
    with pytest.raises(LLMResponseParseError) as exc_info:
        parse_llm_response(raw)
    # The exception message is human-readable for the 422 body.
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
    """A JSON array (not an object) is malformed → raises `LLMResponseParseError`.

    The parser expects an object shape (`{...}`) so the response can
    carry the `explanation` field alongside `matching_ids`. A bare
    array is rejected so the model can't accidentally bypass the
    shape contract.
    """
    with pytest.raises(LLMResponseParseError):
        parse_llm_response('["a", "b"]')


# ---------------------------------------------------------------------------
# Scenario 5: missing `matching_ids` key — default to []
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 6: empty list value
# ---------------------------------------------------------------------------


def test_empty_matching_ids_list_is_valid() -> None:
    """`{"matching_ids": [], "explanation": "no matches"}` is a valid answer."""
    raw = '{"matching_ids": [], "explanation": "no matches"}'
    result = parse_llm_response(raw)
    assert result.matching_ids == []
    assert result.explanation == "no matches"


# ---------------------------------------------------------------------------
# Shape validation — non-dict JSON
# ---------------------------------------------------------------------------


def test_json_string_value_rejected() -> None:
    """A JSON string is rejected (not an object)."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response('"just a string"')


def test_json_number_value_rejected() -> None:
    """A JSON number is rejected (not an object)."""
    with pytest.raises(LLMResponseParseError):
        parse_llm_response("42")


# ---------------------------------------------------------------------------
# LLMSelection dataclass — frozen, slots, equality
# ---------------------------------------------------------------------------


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
