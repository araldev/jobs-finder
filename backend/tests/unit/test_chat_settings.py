"""Unit tests for the `sse_keepalive_seconds` Settings field (T-002 of `chat-streaming`).

Spec: REQ-SSE-002 (keepalive comments during quiet periods).

The field has 4 acceptance criteria:
  1. Default value is 15.0 seconds.
  2. Upper bound `le=60.0` rejects values like 120.0
     (Chrome's idle timeout).
  3. Lower bound `ge=0.0` allows 0.0 (the kill switch
     — `SSE_KEEPALIVE_SECONDS=0` disables the keepalive
     feature entirely per REQ-SSE-002 3rd scenario).
  4. The env var `SSE_KEEPALIVE_SECONDS` is the primary
     alias (Pydantic reads it on `Settings()` construction).

The 4 tests are narrow (one assertion per behavior) and exercise
the Pydantic field validators directly so a regression in the
field declaration breaks the test loudly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Default
# ---------------------------------------------------------------------------


def test_sse_keepalive_seconds_default_is_15() -> None:
    """`Settings()` without `SSE_KEEPALIVE_SECONDS` set returns `15.0`.

    REQ-SSE-002 default. The default is the value that keeps a
    browser / nginx proxy from timing out during the 2-5s
    stage-2 aggregator wait (the 60s Chrome idle timeout is
    4x the default).
    """
    settings = Settings()
    assert settings.sse_keepalive_seconds == 15.0


# ---------------------------------------------------------------------------
# Upper bound
# ---------------------------------------------------------------------------


def test_sse_keepalive_seconds_above_60_raises_validation_error() -> None:
    """`SSE_KEEPALIVE_SECONDS=120.0` (above the 60.0 upper bound) is rejected.

    REQ-SSE-002 3rd scenario: Pydantic MUST raise a
    `ValidationError` at settings load so misconfiguration
    surfaces at startup, not on the first user request.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(sse_keepalive_seconds=120.0)
    # The error mentions the field name so an operator can
    # grep their config for the offender.
    assert "sse_keepalive_seconds" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Lower bound — `0.0` is the kill switch and MUST be valid
# ---------------------------------------------------------------------------


def test_sse_keepalive_seconds_zero_is_allowed() -> None:
    """`SSE_KEEPALIVE_SECONDS=0.0` is VALID (the keepalive kill switch).

    REQ-SSE-002 3rd scenario: when keepalive is disabled, the
    feature MUST be off (no `: keepalive\\n\\n` comments). The
    `ge=0.0` lower bound (NOT `gt=0.0`) is the design
    decision flagged in the proposal.

    A regression to `gt=0.0` would reject 0.0 and break the
    kill switch.
    """
    settings = Settings(sse_keepalive_seconds=0.0)
    assert settings.sse_keepalive_seconds == 0.0


def test_sse_keepalive_seconds_negative_is_rejected() -> None:
    """`SSE_KEEPALIVE_SECONDS=-1.0` is rejected (`ge=0.0`).

    A negative keepalive is nonsensical — `asyncio.wait_for`
    would raise immediately. Pydantic MUST reject it at
    settings load.
    """
    with pytest.raises(ValidationError):
        Settings(sse_keepalive_seconds=-1.0)


# ---------------------------------------------------------------------------
# Env var alias
# ---------------------------------------------------------------------------


def test_sse_keepalive_seconds_env_var_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`SSE_KEEPALIVE_SECONDS=7.5` env var is read by `Settings()`.

    The `validation_alias=AliasChoices("SSE_KEEPALIVE_SECONDS",
    "sse_keepalive_seconds")` pattern is the same one used by
    every other field group in `Settings` (e.g. `cache_*`,
    `rate_limit_*`, `llm_*`). A regression that drops the
    env-var alias would force operators to set the field
    programmatically only.
    """
    monkeypatch.setenv("SSE_KEEPALIVE_SECONDS", "7.5")
    settings = Settings()
    assert settings.sse_keepalive_seconds == 7.5
