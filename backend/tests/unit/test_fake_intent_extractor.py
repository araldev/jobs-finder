"""Unit tests for the `FakeIntentExtractor` test double (T-006 of `chat-filter-2stage`).

`FakeIntentExtractor` is the canonical test double for stage-1
intent extraction, defined in `tests/conftest.py` so any
test file (unit + integration) can import it via the conftest.

It mirrors the `FakeLLMClient` pattern from
`tests/integration/test_chat_endpoint.py`:
  - `calls: list[str]` — records every `message` passed to `extract()`
  - `canned: Intent` — returned on every call (default
    `Intent(confidence=0.95)`)
  - `error: Exception | None` — when set, `extract()` raises it

These tests pin the GREEN behavior so a future change to
the test double's surface (e.g. a Protocol-conforming refactor
in PR2) surfaces as a test failure, not a silent regression.
"""

from __future__ import annotations

import pytest

from jobs_finder.application.ports import Intent
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError
from tests.conftest import FakeIntentExtractor


async def test_fake_intent_extractor_default_canned_is_high_confidence() -> None:
    """Default `canned` is `Intent(confidence=0.95)` — the 2-stage path trigger.

    Spec: REQ-CHAT-INT-004 — the use case compares `intent.confidence`
    against `INTENT_EXTRACTION_CONFIDENCE_THRESHOLD` (default 0.7).
    A `canned` intent with `confidence=0.95` triggers the
    2-stage path. The default makes the most common test
    scenario (high-confidence happy path) the path of
    least setup.
    """
    fake = FakeIntentExtractor()
    assert fake.canned.confidence == 0.95


async def test_fake_intent_extractor_extract_returns_canned() -> None:
    """`extract(message=...)` returns `canned` and records the call."""
    canned = Intent(q="x", confidence=0.7, notes="hello")
    fake = FakeIntentExtractor(canned=canned)
    result = await fake.extract(message="any user message")
    assert result is canned
    assert result.q == "x"
    assert result.notes == "hello"
    assert fake.calls == ["any user message"]


async def test_fake_intent_extractor_records_all_calls_in_order() -> None:
    """Multiple `extract()` calls are recorded in order so tests can assert the sequence."""
    fake = FakeIntentExtractor()
    await fake.extract(message="first")
    await fake.extract(message="second")
    await fake.extract(message="third")
    assert fake.calls == ["first", "second", "third"]


async def test_fake_intent_extractor_error_raises_on_extract() -> None:
    """When `error` is set, `extract()` raises the injected exception.

    Used to test the stage-1 parse-failure path: the use case
    catches `LLMResponseParseError` from the extractor and
    falls back to v1 (REQ-CHAT-INT-004). The test double
    needs to support error injection for the use case tests
    in PR2.
    """
    err = LLMResponseParseError("simulated parse failure")
    fake = FakeIntentExtractor(error=err)
    with pytest.raises(LLMResponseParseError, match="simulated parse failure"):
        await fake.extract(message="any")
    # The call was still recorded (the use case forwards
    # the message BEFORE the parser decides it's invalid).
    assert fake.calls == ["any"]


async def test_fake_intent_extractor_custom_canned_intent() -> None:
    """A test can override `canned` to drive the use case through a specific path.

    Example: `FakeIntentExtractor(canned=Intent(confidence=0.3))`
    triggers the v1 fallback path (REQ-CHAT-INT-004) when
    used in a use case test.
    """
    low_confidence = Intent(confidence=0.3, notes="low")
    fake = FakeIntentExtractor(canned=low_confidence)
    result = await fake.extract(message="hola")
    assert result.confidence == 0.3
    assert result.notes == "low"
