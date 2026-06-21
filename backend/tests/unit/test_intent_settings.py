"""Unit tests for the 6 NEW `Settings` fields added in T-007.

Spec: REQ-CHAT-INT-006 (chat-filter-2stage 2-stage LLM flow control).

The 6 fields added in T-007 (the `chat-filter-2stage` change's
PR2) configure the 2-stage LLM flow:

  - `intent_extraction_enabled: bool` (default True) — the master
    switch for the 2-stage flow. Setting it to `False` reverts
    the chat-filter use case to the v1 single-stage behavior.
  - `intent_extraction_confidence_threshold: float` (default 0.7,
    `ge=0.0, le=1.0`) — below this confidence, the use case
    falls back to the v1 path.
  - `intent_max_results: int` (default 100, `ge=1, le=500`) —
    the per-source cap for the stage-2 aggregator scrape
    (higher than the v1 `limit=20` to give the LLM more recall).
  - `llm_stage1_max_tokens: int` (default 256, `ge=64, le=1024`)
    — the stage-1 LLM response size cap (the 6-field extraction
    is small; this is intentionally tiny to keep cost low).
  - `llm_stage1_temperature: float` (default 0.0, `ge=0.0, le=2.0`)
    — the stage-1 LLM temperature. 0.0 = deterministic.
  - `intent_extraction_retry: int` (default 1, `ge=0, le=3`) —
    the number of retries on stage-1 parse failure.

The fields declare `validation_alias=AliasChoices(..., ...)`
so that env-var lookup reads the uppercase `INTENT_*` /
`LLM_STAGE1_*` env var, and programmatic construction
(`Settings(intent_extraction_enabled=False)`) works via the
second choice. This is the same pattern used by the existing
`indeed_*`, `infojobs_*`, `linkedin_*`, `cache_*`,
`rate_limit_*`, `llm_*`, and `aggregator_*` fields in
`Settings`.

These tests are the RED -> GREEN -> REFACTOR anchor for T-007.
Written BEFORE the production fields are added so the test
fails with the right reason: `AttributeError` or
`pydantic.ValidationError` from a missing / wrong field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Defaults — `Settings()` (no env, no kwargs) yields the spec defaults.
# ---------------------------------------------------------------------------


def test_settings_intent_extraction_enabled_default_is_true() -> None:
    """`intent_extraction_enabled` defaults to `True` (REQ-CHAT-INT-006).

    The master switch is ON by default. Operators set it to
    `False` to revert to v1 behavior (the kill switch).
    """
    settings = Settings()
    assert settings.intent_extraction_enabled is True


def test_settings_intent_extraction_confidence_threshold_default_is_0_0() -> None:
    """`intent_extraction_confidence_threshold` defaults to `0.0`.

    Below this confidence, the use case falls back to v1
    (REQ-CHAT-INT-004). 0.0 (deliberate per Q6 of the
    `refactor-pre-existing-baseline-debt` change) means
    "always use the 2-stage path with extracted keywords +
    location"; the v1 fallback is only triggered when
    operators explicitly raise the threshold above 0.0.
    """
    settings = Settings()
    assert settings.intent_extraction_confidence_threshold == 0.0


def test_settings_intent_max_results_default_is_100() -> None:
    """`intent_max_results` defaults to `100`.

    The per-source cap for the stage-2 repository query.
    Changed back to 100 to give the LLM more jobs to score
    and select the best matches for the user.
    """
    settings = Settings()
    assert settings.intent_max_results == 100


def test_settings_llm_stage1_max_tokens_default_is_256() -> None:
    """`llm_stage1_max_tokens` defaults to `256`.

    The 6-field extraction is small (a JSON object with ~6
    short fields); 256 tokens is generous and keeps cost low
    (~$0.0001 per call vs $0.0025 for the 1024-token stage-3
    call).
    """
    settings = Settings()
    assert settings.llm_stage1_max_tokens == 256


def test_settings_llm_stage1_temperature_default_is_0_0() -> None:
    """`llm_stage1_temperature` defaults to `0.0`.

    The 6-field extraction is well-defined; deterministic
    output is preferred.
    """
    settings = Settings()
    assert settings.llm_stage1_temperature == 0.0


def test_settings_intent_extraction_retry_default_is_1() -> None:
    """`intent_extraction_retry` defaults to `1`.

    Retry-once with the corrective system prompt on parse
    failure (the design's deliberate trade: one retry doubles
    the cost on failure, but a second retry is unlikely to
    succeed where the first retry failed).
    """
    settings = Settings()
    assert settings.intent_extraction_retry == 1


# ---------------------------------------------------------------------------
# Programmatic construction — `Settings(field=value)` works via the second
# choice in `AliasChoices`.
# ---------------------------------------------------------------------------


def test_settings_intent_extraction_confidence_threshold_programmatic_override() -> None:
    """`Settings(intent_extraction_confidence_threshold=0.5)` overrides the default.

    The second choice in `AliasChoices` enables programmatic
    construction (no env var required). This is the
    test-friendly path for `app_factory` and the use case
    tests.
    """
    settings = Settings(intent_extraction_confidence_threshold=0.5)
    assert settings.intent_extraction_confidence_threshold == 0.5


def test_settings_intent_extraction_enabled_programmatic_override() -> None:
    """`Settings(intent_extraction_enabled=False)` overrides the default.

    The default is True; setting it to False is the kill switch
    (reverts the chat-filter use case to the v1 single-stage
    behavior — REQ-CHAT-INT-005).
    """
    settings = Settings(intent_extraction_enabled=False)
    assert settings.intent_extraction_enabled is False


def test_settings_intent_max_results_programmatic_override() -> None:
    """`Settings(intent_max_results=50)` overrides the default."""
    settings = Settings(intent_max_results=50)
    assert settings.intent_max_results == 50


# ---------------------------------------------------------------------------
# Env-var override — `INTENT_*` / `LLM_STAGE1_*` env vars drive the fields.
# ---------------------------------------------------------------------------


def test_settings_intent_extraction_confidence_threshold_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INTENT_EXTRACTION_CONFIDENCE_THRESHOLD=0.5` env var → 0.5."""
    monkeypatch.setenv("INTENT_EXTRACTION_CONFIDENCE_THRESHOLD", "0.5")
    settings = Settings()
    assert settings.intent_extraction_confidence_threshold == 0.5


def test_settings_intent_extraction_enabled_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INTENT_EXTRACTION_ENABLED=false` env var → False (the kill switch)."""
    monkeypatch.setenv("INTENT_EXTRACTION_ENABLED", "false")
    settings = Settings()
    assert settings.intent_extraction_enabled is False


def test_settings_intent_max_results_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INTENT_MAX_RESULTS=50` env var → 50."""
    monkeypatch.setenv("INTENT_MAX_RESULTS", "50")
    settings = Settings()
    assert settings.intent_max_results == 50


def test_settings_llm_stage1_max_tokens_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_STAGE1_MAX_TOKENS=128` env var → 128."""
    monkeypatch.setenv("LLM_STAGE1_MAX_TOKENS", "128")
    settings = Settings()
    assert settings.llm_stage1_max_tokens == 128


def test_settings_llm_stage1_temperature_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_STAGE1_TEMPERATURE=0.5` env var → 0.5."""
    monkeypatch.setenv("LLM_STAGE1_TEMPERATURE", "0.5")
    settings = Settings()
    assert settings.llm_stage1_temperature == 0.5


def test_settings_intent_extraction_retry_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INTENT_EXTRACTION_RETRY=2` env var → 2."""
    monkeypatch.setenv("INTENT_EXTRACTION_RETRY", "2")
    settings = Settings()
    assert settings.intent_extraction_retry == 2


# ---------------------------------------------------------------------------
# Pydantic bounds — invalid values raise `ValidationError` at construction.
# ---------------------------------------------------------------------------


def test_settings_intent_extraction_confidence_threshold_above_1_raises() -> None:
    """`Settings(intent_extraction_confidence_threshold=1.5)` raises `ValidationError` (`le=1.0`).

    Out-of-range confidence would silently mis-route the
    request. The bound is enforced at construction so
    misconfiguration fails fast at startup, not on the first
    2-stage request.
    """
    with pytest.raises(ValidationError):
        Settings(intent_extraction_confidence_threshold=1.5)


def test_settings_intent_extraction_confidence_threshold_below_0_raises() -> None:
    """`Settings(intent_extraction_confidence_threshold=-0.1)` raises `ValidationError`.

    The bound is `ge=0.0`; a negative confidence would silently
    mis-route the request (the use case would always see
    `intent.confidence < threshold` and fall back to v1, even
    when the model returned a perfectly good extraction).
    """
    with pytest.raises(ValidationError):
        Settings(intent_extraction_confidence_threshold=-0.1)


def test_settings_intent_max_results_below_1_raises() -> None:
    """`Settings(intent_max_results=0)` raises `ValidationError` (`ge=1`).

    A 0-result scrape would be useless and could mask a
    misconfiguration. The bound is enforced at construction.
    """
    with pytest.raises(ValidationError):
        Settings(intent_max_results=0)


def test_settings_intent_max_results_above_500_raises() -> None:
    """`Settings(intent_max_results=501)` raises `ValidationError` (`le=500`).

    500 is the upper bound to keep cost predictable. The
    bound is enforced at construction.
    """
    with pytest.raises(ValidationError):
        Settings(intent_max_results=501)


def test_settings_llm_stage1_max_tokens_below_64_raises() -> None:
    """`Settings(llm_stage1_max_tokens=32)` raises `ValidationError` (`ge=64`)."""
    with pytest.raises(ValidationError):
        Settings(llm_stage1_max_tokens=32)


def test_settings_llm_stage1_max_tokens_above_1024_raises() -> None:
    """`Settings(llm_stage1_max_tokens=2048)` raises `ValidationError` (`le=1024`)."""
    with pytest.raises(ValidationError):
        Settings(llm_stage1_max_tokens=2048)


def test_settings_llm_stage1_temperature_above_2_raises() -> None:
    """`Settings(llm_stage1_temperature=3.0)` raises `ValidationError` (`le=2.0`)."""
    with pytest.raises(ValidationError):
        Settings(llm_stage1_temperature=3.0)


def test_settings_intent_extraction_retry_above_3_raises() -> None:
    """`Settings(intent_extraction_retry=4)` raises `ValidationError` (`le=3`).

    3 is the upper bound on retries — 4 total attempts
    (initial + 3 retries) would multiply cost by 4x with
    diminishing returns.
    """
    with pytest.raises(ValidationError):
        Settings(intent_extraction_retry=4)


def test_settings_intent_extraction_retry_negative_raises() -> None:
    """`Settings(intent_extraction_retry=-1)` raises `ValidationError` (`ge=0`)."""
    with pytest.raises(ValidationError):
        Settings(intent_extraction_retry=-1)


def test_settings_intent_max_results_invalid_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INTENT_MAX_RESULTS=invalid` env var raises `ValidationError` (REQ-CHAT-INT-006).

    Pydantic-settings surfaces unparseable integers as
    `ValidationError` at construction. This is the
    "fails-fast at startup" contract — misconfiguration
    surfaces in container logs at boot, not on the first
    user request.
    """
    monkeypatch.setenv("INTENT_MAX_RESULTS", "not-an-integer")
    with pytest.raises(ValidationError):
        Settings()
