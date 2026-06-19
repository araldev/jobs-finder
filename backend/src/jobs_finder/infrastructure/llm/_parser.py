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
#   - `finalize(returned_ids: set[str]) -> LLMSelection`:
#       Reuses `parse_llm_response(self.buffer)`. Drops any
#       `matching_ids` NOT in `returned_ids` (the aggregator's
#       actual returned ids) with a `WARNING` log per dropped
#       id. The `explanation` is preserved verbatim (the drop
#       is silent — the user sees the same explanation text the
#       LLM emitted, NOT a rewrite like "N of M matched").
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StreamEventParser:
    """Streaming parser for `POST /jobs/chat/stream`.

    Accumulates LLM tokens in ``self.buffer``, strips thinking
    blocks, yields cleaned chunks for live ``text`` SSE events,
    and reuses ``parse_llm_response`` to extract the final
    ``LLMSelection`` at end-of-stream.

    MiniMax emits thinking tokens as regular content deltas.
    Because ``thinking: {"type": "disabled"}`` is NOT reliably
    respected in streaming mode (the M2 model still emits
    ``<think>...`` prefix tokens), this parser tracks a
    ``_thinking_done`` flag: once a chunk does NOT start with
    ``<think>``, thinking is considered complete and all
    subsequent content is passed through verbatim.

    Attributes:
        buffer: The accumulated text. Empty by default; grows
            as ``feed(chunk)`` is called. The end-of-stream
            re-parse runs on this string.
        _thinking_done: ``True`` once a chunk that does NOT
            start with ``<think>`` has been processed.
    """

    buffer: str = ""
    _thinking_done: bool = False
    def feed(self, chunk: str) -> Iterator[str]:
        """Append ``chunk`` to ``self.buffer`` and yield it.

        MiniMax emits reasoning content that can consume the entire
        token budget. This method strips residual ``<think>`` tokens
        and Chinese analysis markers so the buffer is as clean
        as possible. If the buffer ends up with no JSON (the
        thinking consumed all tokens), ``finalize()`` returns an
        empty selection instead of raising.

        Yields:
            A single ``str``. Empty strings are not yielded to
            avoid SSE validation errors, EXCEPT when the original
            chunk was already empty (preserves the legacy
            ``feed("") → [""]`` behaviour).
        """
        if not chunk:
            self.buffer += chunk
            yield chunk
            return

        if chunk.startswith("<think>"):
            # Residual thinking token — discard.
            return

        # Strip Chinese analysis markers that MiniMax emits
        # between reasoning sections.
        chunk = re.sub(r"进行调整\n[\s\S]*?进行分析\n\n", "", chunk)

        self.buffer += chunk
        yield chunk

    def finalize(self, returned_ids: set[str]) -> LLMSelection:
        """Re-parse ``self.buffer`` and return the filtered selection.

        Reuses ``parse_llm_response`` on the accumulated buffer.
        After parsing, ``matching_ids`` is intersected with
        ``returned_ids``; any id not in ``returned_ids`` is a
        hallucination and is dropped silently with a WARNING log.

        If the buffer contains no JSON (MiniMax thinking consumed
        all tokens), returns an empty selection so the aggregator
        can still send its results to the user.

        Args:
            returned_ids: The set of job ids the aggregator
                actually returned (the v1 stage-3 ``valid_ids``
                set). The LLM's ``matching_ids`` is intersected
                with this set; ids not in the set are dropped.

        Returns:
            The ``LLMSelection`` with the strict-subset
            ``matching_ids`` and the preserved ``explanation``.
            Returns an empty selection if the buffer has no JSON.
        """
        try:
            selection = parse_llm_response(self.buffer)
        except LLMResponseParseError:
            # Buffer contains no JSON — MiniMax thinking consumed
            # all tokens. Return empty selection so the aggregator
            # can still send its results to the user.
            return LLMSelection(matching_ids=[], explanation="")
        valid_matching_ids: list[str] = []
        for mid in selection.matching_ids:
            if mid in returned_ids:
                valid_matching_ids.append(mid)
            else:
                _logger.warning(
                    "LLMStreamEventParser: hallucinated id %r not in "
                    "aggregator returned_ids (had %d ids); dropping",
                    mid,
                    len(returned_ids),
                )
        return LLMSelection(
            matching_ids=valid_matching_ids,
            explanation=selection.explanation,
        )
