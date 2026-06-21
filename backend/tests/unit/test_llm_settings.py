"""Unit tests for the 9 new `llm_*` `Settings` fields added in T-006 of `ai-chat-filter`.

Spec: REQ-CHAT-001 (settings contract), REQ-CHAT-002 (rate-limit env var),
the preflight D2 (model = `MiniMax-M3`), and the preflight chat-disabled
default (Q3 — `llm_filter_enabled=False` so the route is OFF by default).

Each field reads from its own `LLM_*` env var via per-field
`validation_alias` (the same pattern used by the `indeed_*`,
`infojobs_*`, `linkedin_*` pagination, cache, rate-limit, and
aggregator fields above). The model-level `env_prefix="LINKEDIN_"`
does not apply to these fields because each declares its own alias.

Defaults pinned by the design (T-006):
    - `llm_api_key: SecretStr | None = None`  (kill switch — None disables the route)
    - `llm_base_url: str = "https://api.minimax.io"`
    - `llm_model: str = "MiniMax-M3"`  (D2 — only model that honors `thinking: disabled`)
    - `llm_temperature: float = 0.0`
    - `llm_max_tokens: int = 1024`
    - `llm_request_timeout_seconds: float = 15.0`
    - `llm_max_message_chars: int = 1000`  (spec Q2 — 400 explicit reject body uses this)
    - `llm_filter_enabled: bool = False`  (Q3 — route is OFF by default; operator flips on)
    - `llm_filter_rate_limit_rpm: int = 20`  (Q3 — per-user chat bucket; matches
      RATE_LIMIT_REQUESTS)

This is the RED → GREEN → REFACTOR anchor for T-006. It must be
authored BEFORE the production fields are added, run to confirm it
fails (RED), then the production fields are added, then the test
passes (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Defaults — each of the 9 new `llm_*` fields has a documented default.
# ---------------------------------------------------------------------------


def test_llm_api_key_default_is_none() -> None:
    """`llm_api_key` defaults to `None` — the kill switch (route NOT registered)."""
    settings = Settings()
    assert settings.llm_api_key is None


def test_llm_base_url_default_is_minimax_io() -> None:
    """`llm_base_url` defaults to `"https://api.minimax.io"` (per the design §4)."""
    settings = Settings()
    assert settings.llm_base_url == "https://api.minimax.io"


def test_llm_model_default_is_minimax_m3() -> None:
    """`llm_model` defaults to `"MiniMax-M3"` (preflight D2 — only model that
    honors `thinking: disabled`).
    """
    settings = Settings()
    assert settings.llm_model == "MiniMax-M3"


def test_llm_temperature_default_is_zero() -> None:
    """`llm_temperature` defaults to `0.0` (deterministic filter, no creativity)."""
    settings = Settings()
    assert settings.llm_temperature == 0.0


def test_llm_max_tokens_default_is_4096() -> None:
    """`llm_max_tokens` code default is `4096`.

    The code default was raised from 1024 to 4096 per the deliberate
    config change tracked in Q6 of the
    `refactor-pre-existing-baseline-debt` change — stage-3
    responses (full job matches with descriptions) need the
    larger budget to avoid truncation on complex queries.

    `_env_file=None` forces pydantic-settings to ignore the
    operator's local `.env` (which may override `LLM_MAX_TOKENS`).
    The test verifies the CODE default, not the env default.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_max_tokens == 4096


def test_llm_request_timeout_seconds_default_is_15() -> None:
    """`llm_request_timeout_seconds` defaults to `15.0` (per the design §4)."""
    settings = Settings()
    assert settings.llm_request_timeout_seconds == 15.0


def test_llm_max_message_chars_default_is_1000() -> None:
    """`llm_max_message_chars` defaults to `1000` (per the design §4)."""
    settings = Settings()
    assert settings.llm_max_message_chars == 1000


def test_llm_filter_enabled_default_is_false() -> None:
    """`llm_filter_enabled` defaults to `False` (preflight Q3 — route is OFF by default).

    The spec originally proposed `True`; the preflight confirmed `False`
    so the route is NOT registered in dev/CI and the operator flips the
    switch in prod via `LLM_FILTER_ENABLED=true` + `LLM_API_KEY=<key>`.
    """
    # Pass `_env_file=None` to force pydantic-settings to ignore
    # the operator's local `.env` (which may have
    # `LLM_FILTER_ENABLED=true`). The test verifies the CODE
    # default, not the env default.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_filter_enabled is False


def test_llm_filter_rate_limit_rpm_default_is_20() -> None:
    """`llm_filter_rate_limit_rpm` defaults to `20` (preflight Q3 — matches
    `RATE_LIMIT_REQUESTS`).
    """
    settings = Settings()
    assert settings.llm_filter_rate_limit_rpm == 20


# ---------------------------------------------------------------------------
# Env-var overrides — each `LLM_*` env var overrides its field via the
# per-field `validation_alias` (which overrides the model `env_prefix=
# "LINKEDIN_"` for the LLM fields).
# ---------------------------------------------------------------------------


def test_llm_api_key_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_API_KEY=sk-foo` overrides the default `None` to a `SecretStr`."""
    monkeypatch.setenv("LLM_API_KEY", "sk-foo")
    settings = Settings()
    assert settings.llm_api_key is not None
    # Pydantic wraps the env value in `SecretStr` to prevent accidental logging.
    assert isinstance(settings.llm_api_key, SecretStr)
    assert settings.llm_api_key.get_secret_value() == "sk-foo"


def test_llm_base_url_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_BASE_URL=https://custom.example.com` overrides the default."""
    monkeypatch.setenv("LLM_BASE_URL", "https://custom.example.com")
    settings = Settings()
    assert settings.llm_base_url == "https://custom.example.com"


def test_llm_model_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_MODEL=MiniMax-M2.7` overrides the default `MiniMax-M3`."""
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M2.7")
    settings = Settings()
    assert settings.llm_model == "MiniMax-M2.7"


def test_llm_temperature_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_TEMPERATURE=0.7` overrides the default `0.0`."""
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    settings = Settings()
    assert settings.llm_temperature == 0.7


def test_llm_max_tokens_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LLM_MAX_TOKENS=2048` overrides the default `1024`."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "2048")
    settings = Settings()
    assert settings.llm_max_tokens == 2048


def test_llm_request_timeout_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_REQUEST_TIMEOUT_SECONDS=30.0` overrides the default `15.0`."""
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "30.0")
    settings = Settings()
    assert settings.llm_request_timeout_seconds == 30.0


def test_llm_max_message_chars_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_MAX_MESSAGE_CHARS=400` overrides the default `1000` (spec Q2 example)."""
    monkeypatch.setenv("LLM_MAX_MESSAGE_CHARS", "400")
    settings = Settings()
    assert settings.llm_max_message_chars == 400


def test_llm_filter_enabled_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_FILTER_ENABLED=true` overrides the default `False`."""
    monkeypatch.setenv("LLM_FILTER_ENABLED", "true")
    settings = Settings()
    assert settings.llm_filter_enabled is True


def test_llm_filter_rate_limit_rpm_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LLM_FILTER_RATE_LIMIT_RPM=5` overrides the default `20` (spec Q6 env override)."""
    monkeypatch.setenv("LLM_FILTER_RATE_LIMIT_RPM", "5")
    settings = Settings()
    assert settings.llm_filter_rate_limit_rpm == 5


# ---------------------------------------------------------------------------
# Programmatic constructor override (same as the env override, but
# without going through the env var layer).
# ---------------------------------------------------------------------------


def test_llm_settings_programmatic_override() -> None:
    """`Settings(llm_api_key="x", llm_model="m", ...)` sets the fields directly."""
    settings = Settings(
        llm_api_key=SecretStr("sk-test"),
        llm_base_url="https://test.example.com",
        llm_model="MiniMax-Test",
        llm_temperature=0.5,
        llm_max_tokens=512,
        llm_request_timeout_seconds=10.0,
        llm_max_message_chars=2000,
        llm_filter_enabled=True,
        llm_filter_rate_limit_rpm=60,
    )
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test"
    assert settings.llm_base_url == "https://test.example.com"
    assert settings.llm_model == "MiniMax-Test"
    assert settings.llm_temperature == 0.5
    assert settings.llm_max_tokens == 512
    assert settings.llm_request_timeout_seconds == 10.0
    assert settings.llm_max_message_chars == 2000
    assert settings.llm_filter_enabled is True
    assert settings.llm_filter_rate_limit_rpm == 60


# ---------------------------------------------------------------------------
# Regression: the existing LinkedIn / Indeed / InfoJobs / cache / rate-limit
# fields are unchanged. Setting `LLM_*` env vars does NOT bleed into them,
# and vice versa.
# ---------------------------------------------------------------------------


def test_existing_linkedin_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `throttle_seconds` (LinkedIn) still defaults to `3.0`."""
    settings = Settings()
    assert settings.throttle_seconds == 3.0


def test_existing_indeed_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `indeed_throttle_seconds` still defaults to `3.0`."""
    settings = Settings()
    assert settings.indeed_throttle_seconds == 3.0


def test_existing_infojobs_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `infojobs_throttle_seconds` still defaults to `3.0`."""
    settings = Settings()
    assert settings.infojobs_throttle_seconds == 3.0


def test_llm_env_vars_do_not_cross_bleed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: setting `LLM_*` env vars does NOT bleed into LinkedIn / Indeed / InfoJobs.

    The model-level `env_prefix="LINKEDIN_"` would naively map
    `LLM_BASE_URL` to `linkedin_base_url`. The per-field
    `validation_alias=AliasChoices("LLM_BASE_URL", "llm_base_url")`
    on `llm_base_url` (and every other LLM field) is the
    protection — it explicitly says "look at `LLM_BASE_URL`", NOT
    `LINKEDIN_LLM_BASE_URL` or similar.
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-xyz")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_FILTER_ENABLED", "true")
    settings = Settings()
    # LLM fields are set.
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-xyz"
    assert settings.llm_base_url == "https://llm.example.com"
    assert settings.llm_filter_enabled is True
    # Pre-existing fields are untouched.
    assert settings.throttle_seconds == 3.0
    assert settings.indeed_throttle_seconds == 3.0
    assert settings.infojobs_throttle_seconds == 3.0
    assert settings.cache_ttl_seconds == 60.0
    assert settings.rate_limit_requests == 20


# ---------------------------------------------------------------------------
# Type / contract — `llm_api_key` MUST be a `SecretStr | None` (not `str`).
# ---------------------------------------------------------------------------


def test_llm_api_key_when_set_is_secretstr_not_plain_str() -> None:
    """`llm_api_key`, when set, is wrapped in `SecretStr` so accidental
    `str()` / f-string interpolations do not leak the key into logs.

    This is a security contract — Pydantic's `SecretStr` overrides
    `__repr__` and `__str__` to return `'**********'` so the key is
    only accessible via `.get_secret_value()`. A regression to plain
    `str` would silently leak the key into tracebacks + log lines.
    """
    settings = Settings(llm_api_key=SecretStr("sk-very-secret-key"))
    assert settings.llm_api_key is not None
    # Plain-string construction would have type `str`; SecretStr is its own type.
    assert not isinstance(settings.llm_api_key, str)
    assert isinstance(settings.llm_api_key, SecretStr)
    # The repr is masked — even repr() does not leak the key.
    assert "sk-very-secret-key" not in repr(settings.llm_api_key)
    assert "sk-very-secret-key" not in str(settings.llm_api_key)
