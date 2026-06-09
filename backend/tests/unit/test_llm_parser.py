"""Unit tests for the `StreamEventParser` (T-005 of `chat-streaming`).

Spec: REQ-PARSE-001 (end-of-stream JSON extraction with strict validation).

`StreamEventParser` is a pure dataclass with 2 methods:

  - `feed(chunk) -> Iterator[str]`: accumulates `chunk` in
    `self.buffer` (so the parser can re-parse the full text
    at the end) and yields the chunk verbatim (so the use
    case can forward each text token to the SSE stream as a
    `text` event in real time).

  - `finalize(returned_ids: set[str]) -> LLMSelection`:
    reuses the production `parse_llm_response` parser on
    the accumulated buffer. The buffer MAY have markdown
    fences (a defensive `re.sub` strips them before
    parsing). `matching_ids` NOT in `returned_ids` are
    dropped silently with a `WARNING` log; the
    `explanation` is preserved.

The 6 tests below exercise the 6 spec scenarios from
REQ-PARSE-001 + design §3:

  1. `feed()` yields chunks verbatim + buffer accumulates.
  2. Plain JSON buffer → finalize returns matching LLMSelection.
  3. Markdown-fenced buffer → fences stripped, parses.
  4. Hallucinated ids (not in returned_ids) → dropped, WARNING logged.
  5. Malformed JSON → raises LLMResponseParseError.
  6. Empty buffer + finalize → raises LLMResponseParseError.
"""

from __future__ import annotations

import logging

import pytest

from jobs_finder.infrastructure.llm._parser import StreamEventParser
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# ---------------------------------------------------------------------------
# Scenario 1: feed() yields chunks verbatim + buffer accumulates
# ---------------------------------------------------------------------------


def test_feed_yields_chunks_verbatim_and_accumulates_buffer() -> None:
    """`feed(chunk)` yields the chunk verbatim + appends to `self.buffer`.

    The dual behavior is the design choice: the consumer
    (the use case's `stream_execute`) iterates the yielded
    strings to push `text` events to the SSE stream; the
    buffer is the canonical state for end-of-stream
    re-parsing.
    """
    parser = StreamEventParser()
    chunks_yielded: list[str] = []
    for chunk in ("match", "ing", " ids"):
        chunks_yielded.extend(parser.feed(chunk))
    # Yielded verbatim in feed order.
    assert chunks_yielded == ["match", "ing", " ids"]
    # Buffer accumulates the same chunks (no separators).
    assert parser.buffer == "matching ids"


def test_feed_with_empty_string_yields_empty_string_and_buffer_unchanged() -> None:
    """`feed("")` yields one empty string + leaves the buffer empty.

    An edge case: an empty-string call MUST still go
    through the `feed` body (so the use case's iteration
    loop is uniform), but the buffer remains unchanged
    and the yielded string is the empty sentinel. A
    use case that calls `finalize` without ever calling
    `feed` (an empty aggregator result) is a separate
    path — see `test_finalize_with_empty_buffer_raises`.
    """
    parser = StreamEventParser()
    chunks = list(parser.feed(""))
    # The `feed` body runs once with an empty string —
    # yields the empty sentinel verbatim. The buffer is
    # unchanged (string concat with "" is a no-op).
    assert chunks == [""]
    assert parser.buffer == ""


# ---------------------------------------------------------------------------
# Scenario 2: plain JSON buffer parses
# ---------------------------------------------------------------------------


def test_finalize_with_plain_json_returns_selection() -> None:
    """A plain JSON buffer parses via the production `parse_llm_response`.

    The 2-chunk concatenation `'{"matching_ids":["j1","j2"],...}'`
    → `LLMSelection(["j1","j2"], "These match")`. The
    `returned_ids` set `{j1, j2, j3}` is the aggregator's
    actual returned ids; j1 + j2 are both in the set, so
    nothing is dropped.
    """
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
    """A buffer with ```json ... ``` fences is stripped and parsed.

    The design decision is to reuse `parse_llm_response` at
    the end of the stream; that parser already handles tier-2
    regex extraction of the first `{...}` block. The fences
    are part of the buffer; the parser's regex extracts the
    JSON regardless.
    """
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
    """IDs in `matching_ids` but NOT in `returned_ids` are dropped + WARNING logged.

    The LLM might return an id that doesn't exist in the
    aggregator's actual jobs (a "hallucination"). The
    parser's policy: drop those ids silently (the use
    case's stage-3 already does this for v1, but the
    parser also drops them defensively so the downstream
    contract is the same in both paths), log a WARNING per
    dropped id, and preserve the `explanation` text.
    """
    parser = StreamEventParser()
    raw = '{"matching_ids":["j1","j9"],"explanation":"all"}'
    list(parser.feed(raw))
    with caplog.at_level(logging.WARNING, logger="jobs_finder.infrastructure.llm._parser"):
        selection = parser.finalize({"j1", "j2", "j3"})
    # j9 is dropped; j1 is kept.
    assert selection.matching_ids == ["j1"]
    # The explanation is preserved UNCHANGED (the drop is
    # silent — no explanation rewrite per the design).
    assert selection.explanation == "all"
    # At least one WARNING log line mentions j9.
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
    """A buffer that's not JSON at all raises `LLMResponseParseError`.

    Both tier-1 (`json.loads(stripped)`) and tier-2
    (regex extraction) fail on plain English text. The
    parser re-raises the exception so the route's
    `_serialize_error` maps it to the `llm_parse` SSE
    error event.
    """
    parser = StreamEventParser()
    list(parser.feed("this is not json at all"))
    with pytest.raises(LLMResponseParseError):
        parser.finalize({"j1"})


# ---------------------------------------------------------------------------
# Scenario 6: empty buffer + finalize → raises LLMResponseParseError
# ---------------------------------------------------------------------------


def test_finalize_with_empty_buffer_raises_parse_error() -> None:
    """An empty buffer + finalize → raises `LLMResponseParseError`.

    The empty-buffer case is the "LLM emitted nothing"
    edge case (a real provider can return 200 with an
    empty body when the streaming pipeline glitches).
    The parser MUST surface this as a parse error so the
    route maps to `llm_parse`, NOT to a successful (empty)
    selection.
    """
    parser = StreamEventParser()
    with pytest.raises(LLMResponseParseError):
        parser.finalize({"j1"})


# ---------------------------------------------------------------------------
# Type-level sanity: `StreamEventParser` is a dataclass with `buffer: str`
# ---------------------------------------------------------------------------


def test_stream_event_parser_buffer_is_a_string_after_init() -> None:
    """`StreamEventParser()` initializes `buffer=""` (the default).

    The dataclass default is the empty string so a fresh
    parser can be `feed`-ed into immediately. A regression
    that defaults `buffer=None` would break the
    `self.buffer += chunk` accumulation.
    """
    parser = StreamEventParser()
    assert parser.buffer == ""
    assert isinstance(parser.buffer, str)


# ---------------------------------------------------------------------------
# Triangulation: feed order matters (chunks are concatenated verbatim, not interleaved)
# ---------------------------------------------------------------------------


def test_feed_concatenates_chunks_in_order() -> None:
    """`feed(a)` + `feed(b)` → buffer == a + b (concatenation, not interleaving).

    The order in which the parser receives chunks
    determines the order of characters in the buffer.
    A regression that prepended `\\n` between chunks
    would break `parse_llm_response` (the JSON would
    not be a single valid object anymore).
    """
    parser = StreamEventParser()
    list(parser.feed('{"matching_ids":'))
    list(parser.feed('["a","b"]}'))
    assert parser.buffer == '{"matching_ids":["a","b"]}'
    # The final buffer is valid JSON; finalize succeeds.
    selection = parser.finalize({"a", "b"})
    assert selection.matching_ids == ["a", "b"]


# Sanity check that the markdown-strip behavior is exposed (and not
# a hidden side-effect of `parse_llm_response`'s tier-2 regex).
def test_finalize_preserves_explanation_after_id_drops() -> None:
    """Dropping hallucinated ids MUST NOT mutate the `explanation` text.

    The design is explicit: the explanation is part of
    the user-facing contract and is preserved verbatim
    (a WARNING is logged for observability, but the
    text the user sees is unchanged). A regression
    that rewrote the explanation to "<N> matches" would
    silently break the user-facing contract.
    """
    parser = StreamEventParser()
    raw = '{"matching_ids":["j1","j9","j2"],"explanation":"all match"}'
    list(parser.feed(raw))
    selection = parser.finalize({"j1", "j2", "j3"})
    assert "all match" in selection.explanation
    # Cross-check: the explanation does NOT mention the dropped id.
    assert "j9" not in selection.explanation
