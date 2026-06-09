"""Defensive LLM response parser (T-008 of `ai-chat-filter`,
extended in T-005 of `chat-streaming`).

Spec: REQ-LLM-002 (the v1 `parse_llm_response` function) +
REQ-PARSE-001 (the new `StreamEventParser` dataclass for the
streaming endpoint).

The v1 `parse_llm_response(raw)` function attempts 3 tiers in
order, returning the first success:

  1. `json.loads(raw.strip())` — works for well-formed JSON, e.g.
     `{"matching_ids": ["a"], "explanation": "ok"}`.
  2. `re.search(r"\\{.*\\}", raw, re.DOTALL)` extracts the FIRST
     balanced `{...}` block, then `json.loads` parses it. This tier
     handles markdown-fenced responses (`` ```json ... ``` ``),
     leading/trailing prose ("Sure, here is the JSON: ..."), and
     trailing text ("Saludos.").
  3. If both tiers fail, raise `LLMResponseParseError` (NOT return
     an empty selection). The design decision is to RAISE on
     tier-1+tier-2 failure so the route maps to HTTP 422; silently
     returning an empty selection would mask a real model
     malfunction and the user would see "no matches" when the LLM
     actually returned garbage.

The streaming `StreamEventParser` (T-005) is a small dataclass
that accumulates chunks in a buffer, yields them verbatim for
live `text` events, and reuses `parse_llm_response` on the
buffer at the end. It also drops hallucinated `matching_ids`
(IDs not in the aggregator's actual returned ids) silently
with a WARNING log.

The returned shape is `LLMSelection(matching_ids, explanation)`. The
`matching_ids` field defaults to `[]` when missing from the JSON
(zero matches is a valid answer — the model can return an empty
list). The `explanation` field defaults to `""` when missing
(preserves the contract "explanation is always present, even when
the list is empty" by using an empty string as the default).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass

from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LLMSelection:
    """The structured result of parsing an LLM response.

    Mirrors the `Job` value-object style: `frozen=True, slots=True`
    (per the project's domain rules). Equality is field-wise
    (dataclass default), and assigning to either field raises
    `FrozenInstanceError`.

    Attributes:
        matching_ids: The IDs of the jobs the LLM selected. May be
            empty (zero matches is a valid answer). Each id is
            the same string used as `Job.id` (source-specific).
        explanation: A short Spanish explanation of why these
            offers match the user's intent. May be empty if the
            model returned no explanation (defaults to `""`).
    """

    matching_ids: list[str]
    explanation: str


# `re.DOTALL` makes `.` match newlines, so multi-line JSON inside
# markdown fences or with trailing prose is captured in a single
# match. The greedy `*` is intentional — the parser's contract is
# "the FIRST balanced `{...}` block in the input". Nested objects
# inside `explanation` text are tolerated by the greedy match
# (the first outer `{...}` captures everything up to the LAST
# `}` in the input, which still produces valid JSON if the model
# is well-behaved). The match's group(0) is then re-validated via
# `json.loads`.
_FIRST_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Truncation length for the `LLMResponseParseError` preview. Keeps
# the 422 body bounded when the LLM returns megabytes of garbage
# (defensive: a runaway model + log handler must not produce
# unbounded output).
_PREVIEW_MAX_CHARS = 200


def _coerce_to_selection(parsed: object) -> LLMSelection:
    """Coerce a `json.loads` result into an `LLMSelection`.

    Rejects anything that isn't a `dict` (lists, strings, numbers,
    booleans, null). Defaults `matching_ids` to `[]` and
    `explanation` to `""` when the keys are missing or when the
    values are not the expected types. A non-`list` `matching_ids`
    value is silently coerced to `[]` (defensive: the model may
    occasionally return `null` or a non-array; the route maps
    `LLMResponseParseError` for a HARD shape mismatch, but a
    soft mismatch is normalized to "no matches" so the user
    sees a sensible response).
    """
    if not isinstance(parsed, dict):
        raise LLMResponseParseError(
            f"LLM response is not a JSON object: got {type(parsed).__name__}"
        )
    raw_ids = parsed.get("matching_ids", [])
    raw_explanation = parsed.get("explanation", "")
    # Defensive normalization: matching_ids must be a list of strings.
    # The model may return null, a number, or a dict; treat all of
    # these as "no matches" rather than crash.
    if isinstance(raw_ids, list) and all(isinstance(i, str) for i in raw_ids):
        matching_ids: list[str] = list(raw_ids)
    else:
        matching_ids = []
    explanation = raw_explanation if isinstance(raw_explanation, str) else ""
    return LLMSelection(matching_ids=matching_ids, explanation=explanation)


def parse_llm_response(raw: str) -> LLMSelection:
    """Defensively extract an `LLMSelection` from an LLM response string.

    The 3-tier algorithm is documented in the module docstring. The
    function NEVER returns an empty selection as a fallback — when
    both tiers fail, it RAISES `LLMResponseParseError` so the
    presentation layer can surface a 422 to the user (rather than
    silently swallowing the error and returning "no matches").

    Args:
        raw: The raw LLM response body. May be a clean JSON object,
            a markdown-fenced JSON block, a JSON object with
            leading/trailing prose, or a completely malformed
            string. All four shapes are accepted (the first three
            succeed; the fourth raises).

    Returns:
        A `LLMSelection` with the extracted `matching_ids` and
        `explanation`. `matching_ids` defaults to `[]` and
        `explanation` defaults to `""` when the corresponding keys
        are missing from the parsed JSON.

    Raises:
        LLMResponseParseError: when the input cannot be parsed as
            a JSON object by either tier 1 or tier 2. The exception
            class subclasses `JobSearchError`; the route maps it
            to HTTP 422.
    """
    # Tier 1: try parsing the whole string (after stripping whitespace).
    stripped = raw.strip()
    if stripped:
        try:
            parsed = json.loads(stripped)
            return _coerce_to_selection(parsed)
        except (json.JSONDecodeError, ValueError):
            # Tier 1 failed — fall through to tier 2. The ValueError
            # catch is a defensive belt-and-suspenders: some json
            # implementations raise ValueError instead of
            # JSONDecodeError on certain inputs.
            pass

    # Tier 2: regex-extract the first balanced {...} block.
    match = _FIRST_OBJECT_RE.search(raw)
    if match is not None:
        try:
            parsed = json.loads(match.group(0))
            return _coerce_to_selection(parsed)
        except (json.JSONDecodeError, ValueError):
            # The extracted block was not valid JSON — fall through
            # to the final raise below.
            pass

    # Both tiers failed. RAISE per the design decision.
    # The preview is truncated to _PREVIEW_MAX_CHARS chars so the
    # 422 body is bounded and a model that returns megabytes of
    # garbage does not produce an unbounded response.
    preview = raw[:_PREVIEW_MAX_CHARS] + ("..." if len(raw) > _PREVIEW_MAX_CHARS else "")
    raise LLMResponseParseError(
        f"could not extract a JSON object from LLM response (preview: {preview!r})"
    )


# ---------------------------------------------------------------------------
# Streaming parser (T-005 of `chat-streaming`, REQ-PARSE-001)
#
# `StreamEventParser` is a small dataclass that accumulates chunks
# in a buffer (`self.buffer`), yields them verbatim for live `text`
# SSE events, and reuses the production `parse_llm_response` at
# the end. The design is the Strategy B from the proposal: "parse
# at the end" — incremental JSON parsing is over-engineering for
# a model that emits ~30-50 tokens/sec.
#
# The 2 methods are:
#   - `feed(chunk) -> Iterator[str]`:
#       Appends `chunk` to `self.buffer` and yields the chunk
#       verbatim. The yielded strings are what the use case
#       forwards as `text` SSE events (so the user sees
#       typewriter-style output in real time). The buffer is
#       the canonical state for end-of-stream re-parsing.
#
#   - `finalize(returned_ids: set[str]) -> LLMSelection`:
#       Reuses `parse_llm_response(self.buffer)`. Drops any
#       `matching_ids` NOT in `returned_ids` (the aggregator's
#       actual returned ids) with a `WARNING` log per dropped
#       id. The `explanation` is preserved verbatim (the drop
#       is silent — the user sees the same explanation text the
#       LLM emitted, NOT a rewrite like "N of M matched").
#
# The dataclass is NOT frozen (the buffer MUST mutate as
# chunks arrive). `field(default_factory=...)` is not needed
# for the simple `buffer: str = ""` field.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StreamEventParser:
    """The streaming parser for `POST /jobs/chat/stream`.

    Accumulates LLM tokens in `self.buffer`, yields them
    verbatim for live `text` SSE events, and reuses
    `parse_llm_response` to extract the final `LLMSelection`
    at end-of-stream. The class is intentionally small
    (~40 lines) so the parser logic is testable in isolation
    (T-005 tests) and the use case can depend on the
    dataclass + the 2 methods without touching
    `parse_llm_response` directly.

    Attributes:
        buffer: The accumulated text. Empty by default; grows
            as `feed(chunk)` is called. The end-of-stream
            re-parse runs on this string.

    Methods:
        feed(chunk): Append `chunk` to `buffer` and yield it
            verbatim. The yielded strings are the live
            `text` SSE events.
        finalize(returned_ids): Re-parse `self.buffer` with
            `parse_llm_response`. Drop hallucinated ids (not
            in `returned_ids`) with a WARNING log. Return the
            `LLMSelection`.
    """

    buffer: str = ""

    def feed(self, chunk: str) -> Iterator[str]:
        """Append `chunk` to `self.buffer` and yield it verbatim.

        The dual behavior is the design: the use case's
        `stream_execute` iterates the yielded strings to push
        `text` SSE events to the client (so the user sees
        typewriter output in real time), AND the buffer is
        the canonical state for end-of-stream re-parsing
        (a single `parse_llm_response` call on the
        concatenated text).

        Yields:
            A single `str` (`chunk` verbatim). The generator
            is one-shot: a test that calls `list(feed(c))`
            gets `[c]`; the next call to `feed(d)` returns
            a NEW generator that yields `[d]`.
        """
        self.buffer += chunk
        yield chunk

    def finalize(self, returned_ids: set[str]) -> LLMSelection:
        """Re-parse the accumulated buffer; drop hallucinated ids.

        The re-parse reuses the production `parse_llm_response`
        function (3-tier algorithm documented in the module
        docstring). After parsing, the `matching_ids` list is
        intersected with `returned_ids` (the aggregator's
        actual returned ids); any id in the LLM's list but
        NOT in the aggregator's set is a "hallucination" and
        is dropped silently with a WARNING log per id.

        The `explanation` field is preserved verbatim — the
        drop is silent on the user-facing text. A regression
        that rewrote the explanation would silently break the
        user-facing contract (the LLM's wording is part of
        the product, not a re-derivable value).

        Args:
            returned_ids: The set of job ids the aggregator
                actually returned (the v1 stage-3
                `valid_ids` set). The LLM's `matching_ids`
                is intersected with this set; ids not in
                the set are dropped.

        Returns:
            The `LLMSelection` with the strict-subset
            `matching_ids` and the preserved `explanation`.

        Raises:
            LLMResponseParseError: when the buffer cannot
                be parsed as a JSON object (both tier-1 and
                tier-2 fail). The route maps this to the
                `llm_parse` SSE error machine code.
        """
        selection = parse_llm_response(self.buffer)
        valid_matching_ids: list[str] = []
        for mid in selection.matching_ids:
            if mid in returned_ids:
                valid_matching_ids.append(mid)
            else:
                _logger.warning(
                    "LLMStreamEventParser: hallucinated id %r not in aggregator "
                    "returned_ids (had %d ids); dropping",
                    mid,
                    len(returned_ids),
                )
        return LLMSelection(matching_ids=valid_matching_ids, explanation=selection.explanation)
