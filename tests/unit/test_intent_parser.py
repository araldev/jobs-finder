"""Unit tests for `class Intent` and `parse_intent_response` (T-002 + T-003).

Spec: REQ-CHAT-INT-001 (7 typed fields) + REQ-LLM-SEC-002 (strict Pydantic
`extra="forbid"` parser with markdown-fence stripping).

The `Intent` model lives in `infrastructure/llm/_intent_parser.py`
(the single source of truth for the Pydantic schema) and is
re-exported from `application/ports.py` (so the use case can
import it as the port's contract — `ports.py` is the natural
seam for "what the application expects").

The class uses `model_config = ConfigDict(extra="forbid")` so an
LLM response with an unknown field (e.g. `"salary_range": 50000`)
raises `pydantic.ValidationError` instead of being silently
accepted (REQ-LLM-SEC-002, second defense after the
`INTENT_EXTRACTION_SYSTEM_PROMPT`'s "no inventes" rule).

`parse_intent_response(raw)` is the strict Pydantic parser that
strips markdown fences and calls `Intent.model_validate_json(...)`.
On any schema violation (unknown field, type mismatch,
`confidence` out of `[0.0, 1.0]`, malformed JSON, markdown-fenced
but invalid inner) it raises `LLMResponseParseError` (the
existing v1 exception from `infrastructure/llm/exceptions.py`).

This is the RED → GREEN → REFACTOR anchor for T-002 + T-003.
The 7 fields are: `q`, `location`, `experience_years`, `remote`,
`employment_type`, `confidence`, `notes`. The `notes` field is
the "unstructured intent" escape hatch (per explore §"Risks #5:
schema coverage" — users may ask about salary range, visa
sponsorship, etc.; the LLM puts that text in `notes`).
"""

from __future__ import annotations

import pydantic
import pytest

from jobs_finder.application.ports import Intent
from jobs_finder.infrastructure.llm._intent_parser import parse_intent_response
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# ===========================================================================
# Intent model — 7 typed fields with extra="forbid"
# ===========================================================================


def test_intent_q_field_can_be_populated() -> None:
    """`q: str | None` — the search keywords (e.g. 'ingeniero Python')."""
    intent = Intent(q="ingeniero", confidence=0.5)
    assert intent.q == "ingeniero"


def test_intent_q_field_can_be_null() -> None:
    """`q` is optional — user might only specify `location` (e.g. 'Madrid')."""
    intent = Intent(confidence=0.5)
    assert intent.q is None


def test_intent_location_field_can_be_populated() -> None:
    """`location: str | None` — the geographic filter (e.g. 'Madrid')."""
    intent = Intent(location="Madrid", confidence=0.5)
    assert intent.location == "Madrid"


def test_intent_location_field_can_be_null() -> None:
    """`location` is optional."""
    intent = Intent(confidence=0.5)
    assert intent.location is None


def test_intent_experience_years_field_can_be_populated() -> None:
    """`experience_years: int | None` — the integer years of experience (no string coercion)."""
    intent = Intent(experience_years=3, confidence=0.5)
    assert intent.experience_years == 3


def test_intent_experience_years_field_can_be_null() -> None:
    """`experience_years` is optional."""
    intent = Intent(confidence=0.5)
    assert intent.experience_years is None


def test_intent_remote_field_can_be_populated() -> None:
    """`remote: bool | None` — the remote-work flag."""
    intent = Intent(remote=True, confidence=0.5)
    assert intent.remote is True


def test_intent_remote_field_can_be_null() -> None:
    """`remote` is optional."""
    intent = Intent(confidence=0.5)
    assert intent.remote is None


def test_intent_employment_type_can_be_one_of_literal_values() -> None:
    """`employment_type: Literal[...] | None` — one of 5 typed values or None."""
    for value in ("full_time", "part_time", "contract", "internship", "freelance"):
        intent = Intent(employment_type=value, confidence=0.5)
        assert intent.employment_type == value


def test_intent_employment_type_can_be_null() -> None:
    """`employment_type` is optional."""
    intent = Intent(confidence=0.5)
    assert intent.employment_type is None


def test_intent_confidence_field_can_be_zero() -> None:
    """`confidence: float` (ge=0.0, le=1.0) — the lower boundary is valid."""
    intent = Intent(confidence=0.0)
    assert intent.confidence == 0.0


def test_intent_confidence_field_can_be_one() -> None:
    """`confidence: float` (ge=0.0, le=1.0) — the upper boundary is valid."""
    intent = Intent(confidence=1.0)
    assert intent.confidence == 1.0


def test_intent_confidence_field_is_required() -> None:
    """`confidence` has no default — every Intent MUST declare its confidence.

    The use case reads `confidence` to decide between 2-stage and
    v1-fallback (REQ-CHAT-INT-004). A missing `confidence` would
    silently default to `0.0` and trigger the fallback without the
    user knowing — a surprise. Pydantic's `Field(...)` without a
    default makes the field required.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent()  # type: ignore[call-arg]


def test_intent_notes_field_defaults_to_none() -> None:
    """`notes: str | None = None` — the unstructured intent escape hatch (REQ-CHAT-INT-001)."""
    intent = Intent(confidence=0.5)
    assert intent.notes is None


def test_intent_notes_field_can_be_populated() -> None:
    """`notes` can hold free-form text the LLM could not fit into the 6 typed fields.

    Example: the user asks 'salary > 50k' — the LLM extracts
    `q=None, location=None, ..., notes='salary > 50k'`. The use case
    does not act on `notes` directly (stage 3 doesn't see it); ops
    can log it for visibility.
    """
    intent = Intent(notes="salary > 50k", confidence=0.5)
    assert intent.notes == "salary > 50k"


def test_intent_full_construction_with_all_7_fields() -> None:
    """All 7 fields populated simultaneously — the canonical happy path."""
    intent = Intent(
        q="ingeniero",
        location="Madrid",
        experience_years=3,
        remote=True,
        employment_type="full_time",
        confidence=0.95,
        notes="Visa sponsorship needed",
    )
    assert intent.q == "ingeniero"
    assert intent.location == "Madrid"
    assert intent.experience_years == 3
    assert intent.remote is True
    assert intent.employment_type == "full_time"
    assert intent.confidence == 0.95
    assert intent.notes == "Visa sponsorship needed"


# ===========================================================================
# Strict Pydantic enforcement — extra="forbid" and typed-field rejections
# ===========================================================================


def test_intent_rejects_extra_field() -> None:
    """`extra="forbid"` — an unknown field (e.g. `salary_range`) raises `ValidationError`.

    REQ-LLM-SEC-002 scenario 2: a model that returns an extra field
    (e.g. `{"q": "x", "salary_range": 50000, "confidence": 0.9}`)
    is rejected. Pydantic's `extra="forbid"` config is the gate.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent(q="x", confidence=0.9, salary_range=50000)  # type: ignore[call-arg]


def test_intent_rejects_string_for_int_field() -> None:
    """`experience_years: int | None` — a string value (e.g. '2-3') is rejected.

    REQ-LLM-SEC-002 scenario 3: a model that returns
    `experience_years: "2-3"` (a string range) does NOT coerce to
    an int. Pydantic's `int` type rejects the string at validation
    time, so the `IntentExtractor` retries once with a corrective
    prompt.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent(experience_years="2-3", confidence=0.5)  # type: ignore[arg-type]


def test_intent_rejects_confidence_above_one() -> None:
    """`confidence: float` (le=1.0) — a value > 1.0 is rejected.

    REQ-LLM-SEC-002 scenario 4: a model that returns
    `confidence: 1.5` is rejected. A model could otherwise
    influence the use case's threshold check by inflating its
    own confidence. Pydantic's `Field(le=1.0)` is the cap.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent(confidence=1.5)


def test_intent_rejects_confidence_below_zero() -> None:
    """`confidence: float` (ge=0.0) — a value < 0.0 is rejected.

    REQ-LLM-SEC-002 scenario 5: a model that returns
    `confidence: -0.1` is rejected. Negative confidence is
    nonsensical and a sign of model confusion.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent(confidence=-0.1)


def test_intent_rejects_unknown_employment_type() -> None:
    """`employment_type: Literal[...]` — a value outside the 5 named values is rejected.

    A model that returns `employment_type: "unknown"` (or
    `"freelancee"` typo) is rejected. Pydantic's `Literal` type
    enforces the closed set at validation time.
    """
    with pytest.raises(pydantic.ValidationError):
        Intent(employment_type="unknown", confidence=0.5)  # type: ignore[arg-type]


# ===========================================================================
# parse_intent_response — strict Pydantic + markdown-fence stripping
# ===========================================================================


def test_parse_intent_response_happy_path_returns_intent() -> None:
    """Valid JSON object → `Intent` with all 7 fields populated."""
    raw = (
        '{"q":"ingeniero","location":"Madrid","experience_years":3,'
        '"remote":true,"employment_type":"full_time","confidence":0.95,'
        '"notes":null}'
    )
    intent = parse_intent_response(raw)
    assert intent.q == "ingeniero"
    assert intent.location == "Madrid"
    assert intent.experience_years == 3
    assert intent.remote is True
    assert intent.employment_type == "full_time"
    assert intent.confidence == 0.95
    assert intent.notes is None


def test_parse_intent_response_with_extra_field_raises() -> None:
    """An unknown field in the JSON → `LLMResponseParseError` (cause: Pydantic `extra="forbid"`).

    REQ-LLM-SEC-002 scenario 2: the parser wraps the Pydantic
    `ValidationError` as `LLMResponseParseError` so the use case
    can catch one exception type and not have to know about
    Pydantic. The `cause` attribute is set to the Pydantic error
    for diagnostics.
    """
    raw = (
        '{"q":"ingeniero","location":"Madrid","experience_years":3,'
        '"remote":true,"employment_type":"full_time","confidence":0.95,'
        '"notes":null,"extra_field":"sneaky"}'
    )
    with pytest.raises(LLMResponseParseError):
        parse_intent_response(raw)


def test_parse_intent_response_with_type_mismatch_raises() -> None:
    """`experience_years: "2-3"` (string) → `LLMResponseParseError` (no coercion)."""
    raw = (
        '{"q":"ingeniero","location":"Madrid","experience_years":"2-3",'
        '"remote":true,"employment_type":"full_time","confidence":0.95}'
    )
    with pytest.raises(LLMResponseParseError):
        parse_intent_response(raw)


def test_parse_intent_response_with_confidence_above_one_raises() -> None:
    """`confidence: 1.5` → `LLMResponseParseError` (out of range)."""
    raw = (
        '{"q":"ingeniero","location":"Madrid","experience_years":3,'
        '"remote":true,"employment_type":"full_time","confidence":1.5}'
    )
    with pytest.raises(LLMResponseParseError):
        parse_intent_response(raw)


def test_parse_intent_response_with_confidence_below_zero_raises() -> None:
    """`confidence: -0.1` → `LLMResponseParseError` (out of range)."""
    raw = (
        '{"q":"ingeniero","location":"Madrid","experience_years":3,'
        '"remote":true,"employment_type":"full_time","confidence":-0.1}'
    )
    with pytest.raises(LLMResponseParseError):
        parse_intent_response(raw)


def test_parse_intent_response_with_non_json_raises() -> None:
    """Non-JSON string → `LLMResponseParseError` (json.loads fails first)."""
    with pytest.raises(LLMResponseParseError):
        parse_intent_response("this is not json at all")


def test_parse_intent_response_strips_markdown_fence_valid() -> None:
    """A markdown-fenced VALID JSON object → fence stripped, parsed, returns `Intent`."""
    raw = '```json\n{"q":"ingeniero","confidence":0.5}\n```'
    intent = parse_intent_response(raw)
    assert intent.q == "ingeniero"
    assert intent.confidence == 0.5


def test_parse_intent_response_strips_markdown_fence_invalid_raises() -> None:
    """A markdown-fenced INVALID JSON → `LLMResponseParseError` (fence stripped, Pydantic fails)."""
    raw = '```json\n{"q":"ingeniero","confidence":1.5}\n```'
    with pytest.raises(LLMResponseParseError):
        parse_intent_response(raw)


def test_parse_intent_response_preserves_null_fields() -> None:
    """JSON with all `null` (other than required `confidence`) → `Intent` with all nulls."""
    raw = (
        '{"q":null,"location":null,"experience_years":null,'
        '"remote":null,"employment_type":null,"confidence":0.3,"notes":null}'
    )
    intent = parse_intent_response(raw)
    assert intent.q is None
    assert intent.location is None
    assert intent.experience_years is None
    assert intent.remote is None
    assert intent.employment_type is None
    assert intent.confidence == 0.3
    assert intent.notes is None


def test_parse_intent_response_returns_llm_response_parse_error_not_pydantic_error() -> None:
    """The error type is `LLMResponseParseError`, NOT `pydantic.ValidationError`.

    REQ-LLM-SEC-002: the parser catches `ValidationError` and
    re-raises as `LLMResponseParseError` so the use case catches
    one type. The `LLMResponseParseError.cause` attribute (if
    exposed) carries the Pydantic error for diagnostics.
    """
    raw = '{"q":"x","confidence":2.0}'  # out of range
    with pytest.raises(LLMResponseParseError) as exc_info:
        parse_intent_response(raw)
    # The exception is LLMResponseParseError, not pydantic.ValidationError.
    assert isinstance(exc_info.value, LLMResponseParseError)
    assert not isinstance(exc_info.value, pydantic.ValidationError)
