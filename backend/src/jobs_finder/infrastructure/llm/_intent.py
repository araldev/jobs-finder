"""Stage-1 intent extractor (T-005 of `chat-filter-2stage`).

Spec: REQ-CHAT-INT-001 (stage-1 extraction returns 7-field
`Intent`), REQ-LLM-SEC-001 (per-LLM-call system prompts with
security boundary), REQ-LLM-SEC-002 (retry-once with corrective
prompt on parse failure), Q4 A1 (corrective prompt includes
schema explicitly + one-line example).

`IntentExtractor` is a class that mirrors the v1 `MiniMaxLLMClient`
(`infrastructure/llm/_client.py`) structural style:

  - Constructor takes all dependencies as keyword-only kwargs.
  - `__slots__` documents the per-instance state.
  - No module-level caches or globals.

The class is the canonical stage-1 implementation. PR2's T-009
wires it into `app_factory.build_app()` via a Protocol-conforming
`IntentExtractorPort` (defined in `application/ports.py`); PR3
adds the `FakeIntentExtractor` to `tests/conftest.py` for the
use case integration tests.

Algorithm (the `extract(*, message)` method):

  1. Empty `message` (after `strip()`) short-circuits to
     `Intent(confidence=0.0)` with NO LLM call. Defensive:
     a garbage message must not waste a paid LLM call.

  2. For attempt in `range(max_retries + 1)`:
       - If `attempt == 0`, use `_system_prompt` (the regular
         extraction prompt with security boundary).
       - Else, use `_corrective_system_prompt` (schema-explicit
         retry prompt with one-line example).
       - Call `llm.complete(system=..., user=build_intent_user_message(message))`.
       - Call `parser(raw)`. On success, return the parsed `Intent`.
       - On `LLMResponseParseError`, continue to the next attempt.
       - On any OTHER exception (e.g. `LLMUnavailableError`),
         re-raise — the use case handles the 502 path.

  3. After the loop, raise `LLMResponseParseError` (retry
     exhaustion). The use case catches this and falls back
     to v1 (REQ-CHAT-INT-004).
"""

from __future__ import annotations

from collections.abc import Callable

from jobs_finder.application.ports import Intent, LLMClientPort
from jobs_finder.infrastructure.llm._intent_parser import parse_intent_response
from jobs_finder.infrastructure.llm._prompt import (
    INTENT_CORRECTIVE_SYSTEM_PROMPT,
    INTENT_EXTRACTION_SYSTEM_PROMPT,
    build_intent_user_message,
)
from jobs_finder.infrastructure.llm.exceptions import LLMResponseParseError


class IntentExtractor:
    """Stage-1 intent extractor (REQ-CHAT-INT-001, REQ-LLM-SEC-001/002).

    Mirrors the v1 `MiniMaxLLMClient` structural style: ctor
    takes keyword-only dependencies, `__slots__` documents the
    per-instance state, and there is no module-level global
    state. A `FakeLLMClient` (Protocol-conforming) can be
    substituted in tests; the `LLMClientPort` Protocol is
    enforced at mypy --strict time.

    The retry strategy is RETRY ONCE with a corrective system
    prompt (Q4 A1). The corrective prompt is a NEW constant
    (different from the regular extraction prompt) that names
    the schema explicitly + includes a one-line valid-JSON
    example so the model gets a clearer signal about the
    expected shape. The default `max_retries=1` (2 total
    attempts) is a deliberate trade: one retry doubles the
    cost on failure, but a second retry is unlikely to succeed
    where the first retry failed (the model has the same
    schema info on both retries). Operators can bump
    `max_retries` to 2 for more tolerance.
    """

    __slots__ = (
        "_llm",
        "_parser",
        "_system_prompt",
        "_corrective_system_prompt",
        "_max_retries",
    )

    def __init__(
        self,
        *,
        llm: LLMClientPort,
        parser: Callable[[str], Intent] = parse_intent_response,
        system_prompt: str = INTENT_EXTRACTION_SYSTEM_PROMPT,
        corrective_system_prompt: str = INTENT_CORRECTIVE_SYSTEM_PROMPT,
        max_retries: int = 1,
    ) -> None:
        self._llm = llm
        self._parser = parser
        self._system_prompt = system_prompt
        self._corrective_system_prompt = corrective_system_prompt
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        self._max_retries = max_retries

    async def extract(self, *, message: str) -> Intent:
        """Extract structured intent from a free-form user message.

        Empty / whitespace-only `message` short-circuits to
        `Intent(confidence=0.0)` with NO LLM call (the use
        case then sees a low-confidence intent and falls
        back to v1 — REQ-CHAT-INT-004).

        On `LLMResponseParseError` from the parser, retries
        ONCE (default `max_retries=1`) with the corrective
        system prompt. On retry failure, re-raises the
        `LLMResponseParseError` for the use case to handle.

        Args:
            message: The user's message (pre-NFC-normalized by
                the route). May be empty or whitespace-only.

        Returns:
            The parsed `Intent` (7 typed fields per
            REQ-CHAT-INT-001).

        Raises:
            LLMResponseParseError: on parse failure after
                retry exhaustion. The use case catches this
                and falls back to v1 (REQ-CHAT-INT-004).
            LLMUnavailableError: when the LLM provider is
                down (NOT caught here — propagates to the
                route which maps to HTTP 502).
        """
        # Step 1: short-circuit on empty / whitespace-only message.
        if not message or not message.strip():
            return Intent(confidence=0.0)

        # Step 2: build the user message ONCE (the same `user` arg
        # is sent on every attempt; only the `system` arg changes).
        user_message = build_intent_user_message(message)

        # Step 3: try with regular prompt, then retry with corrective.
        last_error: LLMResponseParseError | None = None
        for attempt in range(self._max_retries + 1):
            system = self._system_prompt if attempt == 0 else self._corrective_system_prompt
            raw = await self._llm.complete(system=system, user=user_message)
            try:
                return self._parser(raw)
            except LLMResponseParseError as e:
                # Capture the last error so the final raise preserves
                # the underlying Pydantic cause (for diagnostics).
                last_error = e
                # Continue to the next attempt. If this was the
                # last attempt, the loop exits and we raise below.
                continue

        # Step 4: retry exhaustion. The loop above returns on
        # success; reaching this point means ALL attempts raised
        # `LLMResponseParseError`. Re-raise the last one (it
        # carries the most-recent Pydantic error as `cause`).
        assert last_error is not None  # invariant: loop entered at least once
        raise last_error


# Re-export the JSON helper to keep the IntentExtractor usable as
# a drop-in for callers that don't import `_prompt` directly.
__all__ = ["IntentExtractor", "build_intent_user_message"]
