"""Pre-check: backward-compat discipline for the v1 chat-filter use case.

Spec: REQ-CHAT-INT-005 (the v1 single-stage behavior must remain
intact when `intent_extraction_enabled=False`).

These tests are the T-008 backward-compat discipline check
(BEFORE the use case refactor lands). The 9 v1 scenarios in
`tests/unit/test_filter_use_case.py` already cover the v1
behavior; the tests here are SCOPED to the Protocol-existence
and structural-conformance checks (T-008 sub-step 1).

The 9 v1 scenarios in `test_filter_use_case.py` MUST pass
with the use case constructed with `intent_extraction_enabled=False`
after T-008 lands. That is the integration-style regression
check; the tests here are the unit-level anchor.
"""

from __future__ import annotations

import inspect

from jobs_finder.application.ports import Intent, IntentExtractorPort
from tests.conftest import FakeIntentExtractor


def test_intent_extractor_port_protocol_exists_in_application_ports() -> None:
    """`IntentExtractorPort` is defined in `application.ports` and importable.

    The Protocol is the seam between the use case (which lives
    in `application/`) and any `IntentExtractor` implementation
    (which lives in `infrastructure/`). Adding it is T-008
    sub-step 1.
    """
    assert IntentExtractorPort is not None


def test_fake_intent_extractor_is_structurally_compatible_with_protocol() -> None:
    """`FakeIntentExtractor` has an `async def extract(*, message: str) -> Intent` method.

    The Protocol is non-runtime-checkable (mirrors the
    `LLMClientPort` and `JobSearchPort` patterns), so
    `isinstance(fake, IntentExtractorPort)` would return False
    even for a structurally-conformant class. The test asserts
    the structural conformance via `hasattr` + callability,
    which is what mypy --strict enforces at type-check time.
    """
    fake = FakeIntentExtractor()
    assert hasattr(fake, "extract")
    assert callable(fake.extract)
    # The method takes a `message: str` keyword argument and
    # returns an `Intent` (async).
    sig = inspect.signature(fake.extract)
    # The single parameter is `message` and is keyword-only
    # (the `*` separator).
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "message"
    assert params[0].kind is inspect.Parameter.KEYWORD_ONLY
    # The return type annotation is `Intent` (string under PEP 563
    # `from __future__ import annotations`; `get_annotations` with
    # `eval_str=True` resolves it to the actual class).
    assert sig.return_annotation == "Intent"
    resolved = inspect.get_annotations(fake.extract, eval_str=True)
    assert resolved["return"] is Intent
    # The coroutine marker is preserved (it's an `async def`).
    assert inspect.iscoroutinefunction(fake.extract)
