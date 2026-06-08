"""Unit tests for the T-001 baseline fix on `Settings.llm_api_key`.

Spec: REQ-SET-LLM-001 (T-001 of `chat-filter-2stage`).

The bug: `Settings()` with an empty `LLM_API_KEY` env var (`.env`
has `LLM_API_KEY=` empty) returns `SecretStr('')`, NOT `None`.
This breaks the kill-switch contract (`app_factory` treats
`llm_api_key is None` as "route not registered" — `SecretStr('')`
is truthy, so the route gets registered and the LLM client crashes
on the first request with an empty `Authorization` header).

T-001 adds a `field_validator(mode="before")` on `Settings.llm_api_key`
that normalizes empty inputs to `None`:

    None          → None
    ""            → None
    SecretStr("") → None
    "real-key"    → SecretStr("real-key")
    SecretStr(rk) → SecretStr(rk)   (passthrough)

This test file pins the GREEN behavior of T-001. The 4 currently-
failing v1 tests in `test_aggregator_settings.py`,
`test_chat_wiring.py`, `test_llm_factory.py`, and
`test_llm_settings.py` are the regression anchor; they are
re-run alongside this file in the RED → GREEN cycle.
"""

from __future__ import annotations

from typing import cast

from pydantic import SecretStr

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Programmatic constructor behavior (REQ-SET-LLM-001)
# ---------------------------------------------------------------------------


def test_settings_with_empty_string_llm_api_key_returns_none() -> None:
    """`Settings(llm_api_key="")` → `settings.llm_api_key is None`.

    The user-side "no key set" state. The empty string is the
    canonical representation of "no value" in env files and
    programmatic construction; the validator MUST treat it as
    `None` (the kill-switch sentinel).
    """
    settings = Settings(llm_api_key=cast(SecretStr | None, ""))
    assert settings.llm_api_key is None


def test_settings_with_real_string_llm_api_key_wraps_as_secretstr() -> None:
    """`Settings(llm_api_key="real-key")` → `SecretStr("real-key")`.

    The non-empty case: a real key is wrapped in `SecretStr` to
    prevent accidental leakage in logs/repr. The `.get_secret_value()`
    accessor reveals the underlying string when needed.
    """
    settings = Settings(llm_api_key=cast(SecretStr | None, "real-key"))
    assert settings.llm_api_key is not None
    assert isinstance(settings.llm_api_key, SecretStr)
    assert settings.llm_api_key.get_secret_value() == "real-key"


def test_settings_with_secretstr_passthrough_preserves_value() -> None:
    """`Settings(llm_api_key=SecretStr("real-key"))` → passthrough.

    When the caller already wrapped the value in `SecretStr`, the
    validator MUST NOT re-wrap (idempotent). The same value is
    returned as-is.
    """
    settings = Settings(llm_api_key=SecretStr("real-key"))
    assert settings.llm_api_key is not None
    assert isinstance(settings.llm_api_key, SecretStr)
    assert settings.llm_api_key.get_secret_value() == "real-key"


def test_settings_with_no_llm_api_key_returns_none() -> None:
    """`Settings()` (no env, no arg) → `llm_api_key is None`.

    The default state. The `llm_api_key` field has `default=None`,
    so the absence of any input lands as `None` directly. This
    pins the GREEN behavior of the validator's `None` branch.
    """
    settings = Settings()
    assert settings.llm_api_key is None


# ---------------------------------------------------------------------------
# Additional edge cases (covering SecretStr("") normalization)
# ---------------------------------------------------------------------------


def test_settings_with_empty_secretstr_llm_api_key_returns_none() -> None:
    """`Settings(llm_api_key=SecretStr(""))` → `None`.

    This is the exact failure mode from the baseline bug:
    pydantic-settings wraps the env-var empty string in
    `SecretStr('')` and feeds it to the validator. The validator
    MUST unwrap and re-emit `None` (otherwise the `is None` kill
    switch never triggers).
    """
    settings = Settings(llm_api_key=SecretStr(""))
    assert settings.llm_api_key is None
