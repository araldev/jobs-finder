"""Strict Pydantic `parse_intent_response` parser (T-003 of `chat-filter-2stage`).

Spec: REQ-LLM-SEC-002 (strict Pydantic `extra="forbid"` validation,
markdown-fence stripping, re-raise `pydantic.ValidationError` as
`LLMResponseParseError`).

The `Intent` Pydantic model itself lives in
`application/ports.py` — the port's contract (REQ-CHAT-INT-001).
This module OWNS ONLY the parser; the model is imported from
`ports.py` (infrastructure → application is fine; the reverse is
forbidden by the dependency rule).

`parse_intent_response(raw: str) -> Intent` is the strict parser:

  1. Strip leading/trailing whitespace.
  2. If markdown-fenced (``` ```json ... ``` ```), extract the
     inner JSON block.
  3. `Intent.model_validate_json(stripped)` — Pydantic enforces
     `extra="forbid"` and the typed-field constraints.
  4. On `pydantic.ValidationError`, raise `LLMResponseParseError`
     (the v1 exception class from `infrastructure/llm/exceptions.py`)
     with the Pydantic error attached as `cause`.

The `LLMResponseParseError` is the canonical "stage-1 parse
failure" signal the `IntentExtractor` (T-005) catches to decide
between retry-once and raise-to-use-case.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from jobs_finder.application.ports import Intent
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# Regex that matches a single markdown-fence block: opening
# ``` or ```json, then the body, then the closing ```. The
# capture group is the JSON body. We use a non-greedy body
# match so a multi-fence input (rare, but defensive) only
# captures the first one.
#
# Pattern breakdown:
#   `` ``` ``         - opening fence (3 backticks)
#   `(?:json)?`       - optional language tag (e.g. "json")
#   `\s*`             - any leading whitespace/newline
#   `([\s\S]*?)`      - captured body (non-greedy; [\s\S] is "any char including newline")
#   `\s*`             - any trailing whitespace before the closing fence
#   `` ``` ``         - closing fence
_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.DOTALL)


def parse_intent_response(raw: str) -> Intent:
    """Strictly parse an LLM intent response into an `Intent`.

    The algorithm:

      1. Strip leading/trailing whitespace.
      2. If the stripped input matches the markdown-fence regex
         (``` ```json ... ``` ```), extract the inner block.
      3. Call `Intent.model_validate_json(stripped_inner)` —
         Pydantic enforces `extra="forbid"` and the typed-field
         constraints.
      4. On `pydantic.ValidationError`, raise `LLMResponseParseError`
         with the Pydantic error attached as `cause`.
      5. On `json.JSONDecodeError` (malformed inner), also raise
         `LLMResponseParseError` with the JSON error as `cause`.

    Args:
        raw: The raw LLM response body. May be a clean JSON
            object, a markdown-fenced JSON block, or a completely
            malformed string. The first two succeed; the third
            raises.

    Returns:
        An `Intent` with the extracted 7 fields. `confidence`
        is required (every Intent declares its own confidence
        so the use case can compare against the threshold).

    Raises:
        LLMResponseParseError: on malformed JSON, unknown fields,
            type mismatches, or `confidence` out of `[0.0, 1.0]`.
            The exception class is the v1 `LLMResponseParseError`
            from `infrastructure/llm/exceptions.py`; subclasses
            `JobSearchError`. The `cause` attribute (inherited
            from the v1 class) carries the Pydantic or JSON error
            for diagnostics.
    """
    stripped = raw.strip()
    # Step 1: strip markdown fence if present.
    fence_match = _FENCE_RE.match(stripped)
    if fence_match is not None:
        stripped = fence_match.group(1).strip()
    # Step 2: Pydantic strict validation. `model_validate_json`
    # parses the JSON AND validates against the `Intent` schema
    # in one atomic operation. Any schema violation (extra field,
    # type mismatch, out-of-range `confidence`, missing
    # `confidence`) raises `pydantic.ValidationError`.
    try:
        return Intent.model_validate_json(stripped)
    except ValidationError as e:
        raise LLMResponseParseError(
            f"intent response failed schema validation: {e!r}",
            cause=e,
        ) from e
    except json.JSONDecodeError as e:
        raise LLMResponseParseError(
            f"intent response is not valid JSON: {e!r}",
            cause=e,
        ) from e
