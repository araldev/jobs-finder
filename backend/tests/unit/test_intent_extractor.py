"""Unit tests for `class IntentExtractor` (T-005 of `chat-filter-2stage`).

Spec: REQ-CHAT-INT-001 (stage-1 intent extraction), REQ-LLM-SEC-001
(stage-1 prompt has security boundary), REQ-LLM-SEC-002
(retry-once with corrective prompt on parse failure).

The `IntentExtractor` is a class in `infrastructure/llm/_intent.py`
that mirrors `MiniMaxLLMClient` (the v1 chat filter's LLM client):

  - Ctor takes: `llm: LLMClientPort` (required), `parser: Callable`
    (default = `parse_intent_response`), `system_prompt: str`
    (default = `INTENT_EXTRACTION_SYSTEM_PROMPT`),
    `corrective_system_prompt: str` (default = `INTENT_CORRECTIVE_SYSTEM_PROMPT`),
    `max_retries: int = 1`.
  - `async def extract(*, message: str) -> Intent`:
    - Empty `message` short-circuits to `Intent(confidence=0.0)` with NO LLM call.
    - On parse failure, retries ONCE with the corrective system prompt
      (Q4 A1). On retry failure, raises `LLMResponseParseError`.
    - `max_retries=0` disables retry (raises on first failure).
    - `max_retries=2` retries twice (3 total attempts).

The class uses constructor injection (same pattern as v1's
`MiniMaxLLMClient`): no global state, no module-level caches.
A `FakeLLMClient` that records calls + returns canned raw strings
satisfies the `LLMClientPort` Protocol structurally (mypy --strict
enforces this).

This is the RED → GREEN → REFACTOR anchor for T-005. Tests are
authored BEFORE the production class is added, run to confirm
they fail (RED), then the class is added, then tests pass (GREEN).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from jobs_finder.application.ports import Intent
from jobs_finder.infrastructure.llm._intent import IntentExtractor
from jobs_finder.infrastructure.llm._prompt import (
    INTENT_CORRECTIVE_SYSTEM_PROMPT,
    INTENT_EXTRACTION_SYSTEM_PROMPT,
    build_intent_user_message,
)
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError

# ===========================================================================
# FakeLLMClient — Protocol-conforming test double
# ===========================================================================


class FakeLLMClient:
    """In-memory fake of `LLMClientPort` for `IntentExtractor` tests.

    Records every `complete(system, user)` call so tests can assert
    the `system` arg differs between attempts (regular → corrective
    on retry) and the `user` arg is the expected JSON. Returns
    canned `raw` strings from a queue (or a single `canned` value
    on every call if `responses` is not set).

    Mirrors the v1 `FakeLLMClient` pattern in
    `tests/unit/test_filter_use_case.py` (the canonical test
    double for `LLMClientPort`).
    """

    def __init__(
        self,
        canned: str | None = None,
        responses: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._canned = canned
        self._responses = list(responses) if responses is not None else None
        self._error = error
        # List of (system, user) tuples — appended on every complete() call.
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        """Record the call + return the next canned response.

        If `responses` is set, dequeues the next response. If a
        single `canned` is set, returns it on every call (the
        happy-path scenario). If `error` is set, raises it on
        every call (the unavailable-LLM scenario — but
        `IntentExtractor` doesn't catch LLMUnavailableError, so
        a 502 propagates from `extract()`).
        """
        self.calls.append((system, user))
        if self._error is not None:
            raise self._error
        if self._responses is not None:
            if not self._responses:
                raise IndexError("FakeLLMClient: no more canned responses")
            return self._responses.pop(0)
        if self._canned is None:
            raise IndexError("FakeLLMClient: no canned response set")
        return self._canned


# ===========================================================================
# Helper: build a valid Intent JSON string for the happy path
# ===========================================================================


def _intent_json(
    q: str | None = "ingeniero",
    location: str | None = "Madrid",
    experience_years: int | None = 3,
    remote: bool | None = True,
    employment_type: str | None = "full_time",
    confidence: float = 0.95,
    notes: str | None = None,
) -> str:
    """Build a valid Intent JSON string for tests.

    Default fields exercise the 6 typed fields + `notes`. Tests
    that need a different shape pass overrides.
    """
    payload: dict[str, Any] = {
        "q": q,
        "location": location,
        "experience_years": experience_years,
        "remote": remote,
        "employment_type": employment_type,
        "confidence": confidence,
        "notes": notes,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# ===========================================================================
# Happy path
# ===========================================================================


async def test_extract_happy_path_returns_parsed_intent() -> None:
    """Valid JSON response → `extract()` returns parsed `Intent`; 1 LLM call."""
    raw = _intent_json(confidence=0.95)
    llm = FakeLLMClient(canned=raw)
    extractor = IntentExtractor(llm=llm)
    intent = await extractor.extract(message="ingeniero en Madrid, 3 años, remoto")
    assert intent.q == "ingeniero"
    assert intent.location == "Madrid"
    assert intent.experience_years == 3
    assert intent.remote is True
    assert intent.employment_type == "full_time"
    assert intent.confidence == 0.95
    assert intent.notes is None
    assert len(llm.calls) == 1


async def test_extract_calls_llm_with_extraction_system_prompt() -> None:
    """The first LLM call uses `INTENT_EXTRACTION_SYSTEM_PROMPT` (NOT the corrective one)."""
    raw = _intent_json()
    llm = FakeLLMClient(canned=raw)
    extractor = IntentExtractor(llm=llm)
    await extractor.extract(message="hola")
    assert len(llm.calls) == 1
    system, _ = llm.calls[0]
    assert system == INTENT_EXTRACTION_SYSTEM_PROMPT
    assert system != INTENT_CORRECTIVE_SYSTEM_PROMPT


async def test_extract_calls_llm_with_compact_user_message() -> None:
    """The user message is the `{"message": "..."}` JSON from `build_intent_user_message`."""
    raw = _intent_json()
    llm = FakeLLMClient(canned=raw)
    extractor = IntentExtractor(llm=llm)
    await extractor.extract(message="hola")
    assert len(llm.calls) == 1
    _, user = llm.calls[0]
    # The user message is the canonical build_intent_user_message output.
    assert user == build_intent_user_message("hola")
    # And it's parseable JSON with the message field.
    parsed = json.loads(user)
    assert parsed["message"] == "hola"


# ===========================================================================
# Empty message short-circuit
# ===========================================================================


async def test_extract_empty_message_short_circuits_no_llm_call() -> None:
    """Empty `message` → `Intent(confidence=0.0)`; 0 LLM calls.

    REQ-CHAT-INT-001 scenario 3: an empty message short-circuits
    without an LLM call. The use case then sees a low-confidence
    intent and falls back to v1 (REQ-CHAT-INT-004).
    """
    llm = FakeLLMClient(canned=_intent_json())
    extractor = IntentExtractor(llm=llm)
    intent = await extractor.extract(message="")
    assert intent.confidence == 0.0
    assert intent.q is None
    assert intent.location is None
    assert intent.experience_years is None
    assert intent.remote is None
    assert intent.employment_type is None
    assert intent.notes is None
    # No LLM call was made.
    assert len(llm.calls) == 0


async def test_extract_whitespace_only_message_short_circuits() -> None:
    """Whitespace-only `message` (e.g. `"   "`) → also short-circuits; 0 LLM calls.

    The pre-NFC-normalized message is already stripped by the
    route, but a defensive check is in the extractor: any
    message that is empty AFTER `strip()` is treated as empty.
    """
    llm = FakeLLMClient(canned=_intent_json())
    extractor = IntentExtractor(llm=llm)
    intent = await extractor.extract(message="   \n\t  ")
    assert intent.confidence == 0.0
    assert len(llm.calls) == 0


# ===========================================================================
# Retry-once with corrective prompt (Q4 A1)
# ===========================================================================


async def test_extract_retry_once_with_corrective_prompt_on_parse_failure() -> None:
    """Invalid JSON on call 1, valid on call 2 → retry succeeds; 2 LLM calls.

    REQ-LLM-SEC-002 + Q4 A1: on parse failure, the extractor
    retries ONCE with the corrective system prompt. The
    corrective prompt names the schema explicitly so the model
    gets a clearer signal about the expected shape.
    """
    invalid = '{"q":"x","confidence":1.5}'  # out-of-range confidence
    valid = _intent_json(confidence=0.9)
    llm = FakeLLMClient(responses=[invalid, valid])
    extractor = IntentExtractor(llm=llm)
    intent = await extractor.extract(message="x")
    assert intent.confidence == 0.9
    assert len(llm.calls) == 2
    # Call 1: regular system prompt.
    assert llm.calls[0][0] == INTENT_EXTRACTION_SYSTEM_PROMPT
    # Call 2: corrective system prompt.
    assert llm.calls[1][0] == INTENT_CORRECTIVE_SYSTEM_PROMPT
    # Both calls use the same user message.
    assert llm.calls[0][1] == llm.calls[1][1]


async def test_extract_retry_exhausted_raises_llm_response_parse_error() -> None:
    """Invalid on both calls → raises `LLMResponseParseError`; 2 LLM calls.

    Spec: REQ-LLM-SEC-002 + Q4 A1 — "no second retry; a misbehaving
    model that fails twice is not going to succeed on the third".
    The use case catches `LLMResponseParseError` and falls back
    to v1 (REQ-CHAT-INT-004).
    """
    invalid = '{"q":"x","confidence":1.5}'  # out-of-range confidence
    llm = FakeLLMClient(responses=[invalid, invalid])
    extractor = IntentExtractor(llm=llm)
    with pytest.raises(LLMResponseParseError):
        await extractor.extract(message="x")
    assert len(llm.calls) == 2


async def test_extract_max_retries_zero_disables_retry() -> None:
    """`max_retries=0` → invalid on call 1 → raises immediately; 1 LLM call."""
    invalid = '{"q":"x","confidence":1.5}'  # out-of-range confidence
    llm = FakeLLMClient(canned=invalid)
    extractor = IntentExtractor(llm=llm, max_retries=0)
    with pytest.raises(LLMResponseParseError):
        await extractor.extract(message="x")
    # No retry: 1 LLM call.
    assert len(llm.calls) == 1


async def test_extract_max_retries_two_retries_twice() -> None:
    """`max_retries=2` → invalid on calls 1+2, valid on call 3 → returns; 3 LLM calls.

    Spec: REQ-LLM-SEC-002 — the default `max_retries=1` retries
    once (2 total attempts). Operators who want to be more
    forgiving can bump to `max_retries=2` (3 total attempts).
    The implementation must support any non-negative integer.
    """
    invalid = '{"q":"x","confidence":1.5}'
    valid = _intent_json(confidence=0.7)
    llm = FakeLLMClient(responses=[invalid, invalid, valid])
    extractor = IntentExtractor(llm=llm, max_retries=2)
    intent = await extractor.extract(message="x")
    assert intent.confidence == 0.7
    assert len(llm.calls) == 3
    # Call 1: regular; calls 2-3: corrective.
    assert llm.calls[0][0] == INTENT_EXTRACTION_SYSTEM_PROMPT
    assert llm.calls[1][0] == INTENT_CORRECTIVE_SYSTEM_PROMPT
    assert llm.calls[2][0] == INTENT_CORRECTIVE_SYSTEM_PROMPT


# ===========================================================================
# Constructor injection
# ===========================================================================


async def test_extract_uses_injected_parser() -> None:
    """A custom `parser` callable is used instead of the default `parse_intent_response`.

    Constructor injection lets tests substitute a different
    parser (e.g. one that returns a hard-coded `Intent` without
    JSON parsing). The production code uses the default
    `parse_intent_response` from `_intent_parser.py`.
    """

    def _fake_parser(raw: str) -> Intent:
        return Intent(confidence=0.42, notes=f"got: {raw}")

    raw = _intent_json()
    llm = FakeLLMClient(canned=raw)
    extractor = IntentExtractor(llm=llm, parser=_fake_parser)
    intent = await extractor.extract(message="x")
    assert intent.confidence == 0.42
    assert intent.notes == f"got: {raw}"


async def test_extract_uses_custom_system_prompt() -> None:
    """A custom `system_prompt` is used on the first attempt (NOT the default)."""
    custom_prompt = "CUSTOM EXTRACTION PROMPT"
    raw = _intent_json()
    llm = FakeLLMClient(canned=raw)
    extractor = IntentExtractor(llm=llm, system_prompt=custom_prompt)
    await extractor.extract(message="x")
    assert llm.calls[0][0] == custom_prompt


async def test_extract_uses_custom_corrective_system_prompt() -> None:
    """A custom `corrective_system_prompt` is used on the retry attempt."""
    custom_prompt = "CUSTOM CORRECTIVE"
    custom_corrective = "CUSTOM CORRECTIVE RETRY"
    invalid = '{"q":"x","confidence":1.5}'
    valid = _intent_json()
    llm = FakeLLMClient(responses=[invalid, valid])
    extractor = IntentExtractor(
        llm=llm,
        system_prompt=custom_prompt,
        corrective_system_prompt=custom_corrective,
    )
    await extractor.extract(message="x")
    assert llm.calls[0][0] == custom_prompt
    assert llm.calls[1][0] == custom_corrective


# ===========================================================================
# Default values
# ===========================================================================


def test_intent_extractor_default_max_retries_is_one() -> None:
    """`max_retries` defaults to 1 (Q4 A1: retry once)."""
    extractor = IntentExtractor(llm=FakeLLMClient())
    # The default is exposed via __slots__ (no public attr by design,
    # but mypy --strict verifies the type). We test the BEHAVIOR via
    # the retry-once test above; this test pins the DEFAULT VALUE
    # so a future refactor that changes the default would surface.
    assert extractor._max_retries == 1  # noqa: SLF001 (test introspection)


def test_intent_extractor_default_system_prompts_are_module_constants() -> None:
    """The default `system_prompt` and `corrective_system_prompt` are the module constants.

    Spec: REQ-LLM-SEC-001 + REQ-CHAT-INT-001 — the prompts
    come from `infrastructure/llm/_prompt.py`. A constructor
    without those kwargs uses the module-level constants.
    """
    extractor = IntentExtractor(llm=FakeLLMClient())
    assert extractor._system_prompt == INTENT_EXTRACTION_SYSTEM_PROMPT  # noqa: SLF001
    assert extractor._corrective_system_prompt == INTENT_CORRECTIVE_SYSTEM_PROMPT  # noqa: SLF001
