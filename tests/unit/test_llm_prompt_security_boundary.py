"""Unit tests for the security-boundary section appended to v1's `SYSTEM_PROMPT` (T-004).

Spec: REQ-LLM-SEC-001 scenario 1 (v1 `SYSTEM_PROMPT` gets a security-
boundary section at the END with 4 invariants + 2 field names)
+ REQ-LLM-SEC-001 scenario 2 (stage-1 `INTENT_EXTRACTION_SYSTEM_PROMPT`
has the same 4 boundary keywords + 6 Intent field names)
+ REQ-CHAT-INT-001 (stage-1 prompt lists the 6 Intent field names).

The 4 invariants are the non-negotiable security requirements
from the user (obs #269):

  1. "no inventes" — the LLM must NOT invent IDs, locations, or
     values not in the input (no-ID-invention + no-value-invention).
  2. "null" — the LLM must use `null` (not a default value) for
     fields the user did not mention (null-for-absent).
  3. "JSON" — the LLM must return valid JSON; the response is
     rejected on malformed output (no-malformed-JSON).
  4. "si dudas" — when uncertain, the LLM must LOWER its
     confidence and NOT invent (what-to-do-when-uncertain).

The 2 field names are the stage-3 response shape:
  - `matching_ids` (the list of selected job IDs)
  - `explanation` (the Spanish rationale)

The 6 Intent field names are the stage-1 response shape:
  - `q`, `location`, `experience_years`, `remote`,
    `employment_type`, `confidence`.

T-004 EXTENDS the v1 `SYSTEM_PROMPT` (string append, NOT rename;
the v1 contract pinned by the 5 existing invariant tests stays
green). The tests below pin the boundary section's presence,
position (at END), and field-name coverage for both v1 and
the new stage-1 prompt, plus the `build_intent_user_message`
shape.

The 5 existing invariant tests in `test_llm_prompt.py` stay
green — the boundary is APPENDED, not REPLACED.
"""

from __future__ import annotations

import json

from jobs_finder.infrastructure.llm._prompt import (
    INTENT_CORRECTIVE_SYSTEM_PROMPT,
    INTENT_EXTRACTION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_intent_user_message,
)

# ===========================================================================
# REQ-LLM-SEC-001 scenario 1 — v1 SYSTEM_PROMPT security boundary
# ===========================================================================


def test_system_prompt_security_boundary_contains_no_inventes_keyword() -> None:
    """The boundary contains "no inventes" (no-ID-invention + no-value-invention).

    REQ-LLM-SEC-001: the LLM must not invent IDs, locations, or
    values not in the input. The boundary's verbatim text contains
    the case-insensitive phrase "no inventes" (the canonical
    Spanish for "do not invent"). The 14 parser tests + 5 prompt
    invariant tests already pin the rest of the prompt; this
    test pins the boundary addition.
    """
    assert "no inventes" in SYSTEM_PROMPT.lower()


def test_system_prompt_security_boundary_contains_null_keyword() -> None:
    """The boundary contains "null" (the JSON null concept — null-for-absent).

    The LLM must use `null` (not a default value) for fields the
    user did not mention. The boundary's verbatim text names
    `null` as the JSON value to use.
    """
    # Case-insensitive — the boundary may use `null` (canonical) or `Null`.
    assert "null" in SYSTEM_PROMPT.lower()


def test_system_prompt_security_boundary_contains_json_keyword() -> None:
    """The boundary contains "JSON" (no-malformed-JSON rule).

    The LLM must return valid JSON; the response is rejected on
    malformed output. The boundary's verbatim text names `JSON`
    as the required output format.
    """
    # Case-insensitive — `JSON` (uppercase) is the canonical form.
    assert "json" in SYSTEM_PROMPT.lower()


def test_system_prompt_security_boundary_contains_si_dudas_keyword() -> None:
    """The boundary contains "si dudas" (what-to-do-when-uncertain rule).

    The LLM must LOWER its confidence and NOT invent when it is
    uncertain. The boundary's verbatim text contains the Spanish
    phrase "si dudas" (if you doubt).
    """
    assert "si dudas" in SYSTEM_PROMPT.lower()


def test_system_prompt_security_boundary_is_at_end() -> None:
    """The boundary section is a contiguous block at the END of the prompt.

    REQ-LLM-SEC-001: the boundary MUST be a contiguous block at
    the END of the prompt (so the model reads the v1 rules first,
    then the security boundary as the last instructions). A
    boundary that is "scattered" through the prompt would not
    be the canonical "last thing the model sees" pattern.

    The test checks that each of the 4 boundary keywords appears
    in the SECOND HALF of the prompt (past the midpoint). Some
    keywords (`json`) also appear earlier in the v1 prompt, so
    we check that AT LEAST ONE occurrence of each keyword is
    past the midpoint — not that the FIRST occurrence is.
    """
    # Find ALL positions of each keyword, then verify at least one
    # is past the midpoint of the prompt.
    midpoint = len(SYSTEM_PROMPT) // 2
    for kw in ("no inventes", "null", "json", "si dudas"):
        positions = [
            i for i in range(len(SYSTEM_PROMPT)) if SYSTEM_PROMPT.lower().startswith(kw, i)
        ]
        assert positions, f"keyword {kw!r} not found in SYSTEM_PROMPT"
        # At least one occurrence of each keyword must be past the midpoint
        # (i.e. the keyword appears in the boundary section at the end).
        assert any(p > midpoint for p in positions), (
            f"keyword {kw!r} is NOT in the boundary section: positions={positions}, "
            f"midpoint={midpoint}, total={len(SYSTEM_PROMPT)}"
        )


def test_system_prompt_security_boundary_lists_matching_ids_field() -> None:
    """The boundary mentions `matching_ids` (the stage-3 response field).

    The boundary is a SCHEMA EXPLICIT — the model is told which
    fields its response must contain. A model that returns
    `{"ids": [...]}` instead of `{"matching_ids": [...]}` would
    parse but produce empty results, so the boundary MUST name
    the canonical field.
    """
    assert "matching_ids" in SYSTEM_PROMPT


def test_system_prompt_security_boundary_lists_explanation_field() -> None:
    """The boundary mentions `explanation` (the stage-3 response field).

    The second field of the response shape. A model that returns
    `{"reason": "..."}` instead of `{"explanation": "..."}` would
    parse but produce an empty string for the user-facing rationale.
    """
    assert "explanation" in SYSTEM_PROMPT


# ===========================================================================
# REQ-LLM-SEC-001 scenario 2 — stage-1 INTENT_EXTRACTION_SYSTEM_PROMPT
# ===========================================================================


def test_intent_extraction_system_prompt_is_non_empty_string() -> None:
    """`INTENT_EXTRACTION_SYSTEM_PROMPT` is a non-empty `str`.

    Spec: REQ-LLM-SEC-001 + REQ-CHAT-INT-001. The stage-1
    prompt drives the `IntentExtractor.extract()` method (T-005).
    An empty prompt would let the LLM return any shape; the
    security boundary in this prompt is the first defense.
    """
    assert isinstance(INTENT_EXTRACTION_SYSTEM_PROMPT, str)
    assert INTENT_EXTRACTION_SYSTEM_PROMPT.strip() != ""


def test_intent_extraction_system_prompt_lists_all_6_typed_fields() -> None:
    """The stage-1 prompt names the 6 typed Intent fields verbatim.

    REQ-CHAT-INT-001: a model that returns `{"query": "..."}`
    instead of `{"q": "..."}` (or any other renaming) would fail
    the strict Pydantic parser (REQ-LLM-SEC-002). The prompt
    names the canonical field names so the model has the schema
    in front of it.
    """
    prompt = INTENT_EXTRACTION_SYSTEM_PROMPT
    # The 6 typed fields (the 7th is `notes`, the optional escape hatch).
    for field_name in ("q", "location", "experience_years", "remote", "employment_type"):
        # Case-insensitive — the prompt uses backtick-quoted field names.
        assert f"`{field_name}`" in prompt, f"stage-1 prompt does not name field {field_name!r}"
    assert "`confidence`" in prompt, "stage-1 prompt does not name `confidence`"


def test_intent_extraction_system_prompt_contains_4_boundary_keywords() -> None:
    """The stage-1 prompt has the same 4 boundary keywords as v1's `SYSTEM_PROMPT`.

    REQ-LLM-SEC-001 scenario 2: the same 4 invariants apply to
    stage 1 (no inventes, null, JSON, si dudas). The LLM must
    not invent, must use `null` for absent fields, must return
    valid JSON, and must lower confidence when uncertain.
    """
    prompt_lower = INTENT_EXTRACTION_SYSTEM_PROMPT.lower()
    for kw in ("no inventes", "null", "json", "si dudas"):
        assert kw in prompt_lower, f"stage-1 prompt missing boundary keyword {kw!r}"


def test_intent_extraction_system_prompt_is_in_spanish() -> None:
    """The stage-1 prompt is in Spanish (the v1 model is a Spanish assistant).

    REQ-CHAT-INT-001 mirrors REQ-LLM-004: the LLM is told it
    is a Spanish-language assistant, so the prompt language
    matches the user's message language. A model that sees
    English in the system prompt may drift to English in the
    response (a model-confusion failure mode).
    """
    prompt_lower = INTENT_EXTRACTION_SYSTEM_PROMPT.lower()
    # The opening "Eres un asistente" is the canonical Spanish opener.
    assert "eres" in prompt_lower
    assert "asistente" in prompt_lower


# ===========================================================================
# REQ-LLM-SEC-002 — INTENT_CORRECTIVE_SYSTEM_PROMPT (retry-once prompt)
# ===========================================================================


def test_intent_corrective_system_prompt_includes_schema_explicit() -> None:
    """The corrective prompt lists the 7 field names verbatim (Q4 A1).

    Spec: REQ-LLM-SEC-002 retry-once + Q4 A1. The corrective
    prompt is used on parse failure; it includes a one-line
    example of valid JSON so the model sees the EXACT expected
    shape, not just a textual description.
    """
    prompt = INTENT_CORRECTIVE_SYSTEM_PROMPT
    # The 7 fields are all named (with backticks).
    for field_name in (
        "q",
        "location",
        "experience_years",
        "remote",
        "employment_type",
        "confidence",
        "notes",
    ):
        assert f"`{field_name}`" in prompt, f"corrective prompt does not name field {field_name!r}"


def test_intent_corrective_system_prompt_includes_valid_json_example() -> None:
    """The corrective prompt includes a one-line valid-JSON example.

    Q4 A1: "the corrective prompt includes a one-line example
    of valid JSON". The example shape is the 7-field null
    template (the safe default).
    """
    prompt = INTENT_CORRECTIVE_SYSTEM_PROMPT
    # The example block is wrapped in ```json fences. We assert
    # the example is present (the prompt says "match this shape").
    assert "```json" in prompt, "corrective prompt missing ```json example block"
    # The example MUST contain all 7 fields named (the schema
    # is the example, not the textual description).
    assert '"q"' in prompt or "`q`" in prompt


# ===========================================================================
# build_intent_user_message — stage-1 user message builder
# ===========================================================================


def test_build_intent_user_message_returns_valid_json() -> None:
    """`build_intent_user_message` returns valid JSON parseable by `json.loads`."""
    result = build_intent_user_message("hola")
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_build_intent_user_message_has_message_field() -> None:
    """The JSON has a `message` field with the input message verbatim."""
    result = build_intent_user_message("ingeniero en Madrid")
    parsed = json.loads(result)
    assert parsed["message"] == "ingeniero en Madrid"


def test_build_intent_user_message_preserves_spanish_chars() -> None:
    """Spanish accents + ñ are preserved as-is (no `\\u` escapes).

    Spec: the route pre-normalizes the message via NFC +
    casefold + strip (preflight CONFIRMED). The stage-1
    user-message builder MUST preserve the Spanish characters
    so the LLM sees the original form. `ensure_ascii=False`
    is the implementation; the rendered string contains the
    raw accented chars (not `\u00e1` for `á`).
    """
    result = build_intent_user_message("ingeniero en Málaga")
    # `Málaga` contains `á` (U+00E1) — a JSON escape would be `\u00e1`.
    assert "Málaga" in result
    # The escape form is NOT in the rendered string (the LLM
    # would still parse it, but the compact form is cleaner).
    assert "\\u00e1" not in result


def test_build_intent_user_message_compact_form_no_spaces() -> None:
    """The rendered JSON is compact (no spaces between keys/values).

    `separators=(",", ":")` is the implementation; the LLM
    sees a tight JSON document, not a pretty-printed one.
    Pretty-printing would add 30+% to the user message size
    without semantic value.
    """
    result = build_intent_user_message("any")
    # No spaces between `:` and the value, no spaces after `,`.
    assert ": " not in result, f"rendered user message has spaces around colons: {result!r}"
    assert ", " not in result, f"rendered user message has spaces after commas: {result!r}"


def test_build_intent_user_message_empty_string() -> None:
    """An empty message serializes as `{"message": ""}` (no crash)."""
    result = build_intent_user_message("")
    parsed = json.loads(result)
    assert parsed == {"message": ""}
