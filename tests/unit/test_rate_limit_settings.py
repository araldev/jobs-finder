"""Unit tests for the 10 new `Settings` fields added for the rate limiter.

Spec: REQ-RL-008.

`Settings` adds 10 new fields, each with
`validation_alias=AliasChoices("RATE_LIMIT_*", "rate_limit_*")`. The
`RATE_LIMIT_REDIS_URL` and `RATE_LIMIT_REDIS_DB` fields have a
computed fallback to `cache_redis_url` / `cache_redis_db` when unset
(via a `model_validator(mode="after")`, NOT `AliasChoices` — those
don't support computed fallbacks). `RATE_LIMIT_EXEMPT_PATHS` parses
a JSON list per the spec's OQ-B (Pydantic-friendly format).

The 6 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

import pytest

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# REQ-RL-008 — Defaults (1 scenario, 10 sub-assertions)
# ---------------------------------------------------------------------------


def test_rate_limit_settings_defaults_match_spec() -> None:
    """Fresh `Settings()` exposes the 10 documented defaults (REQ-RL-008 defaults row).

    The defaults are pinned in the spec REQ-RL-008 table:
    - `rate_limit_enabled` -> `True`
    - `rate_limit_backend` -> `"memory"`
    - `rate_limit_requests` -> `20` (was 60 pre-`rate-limit-followups`;
      aligned to per-source `AsyncThrottle.min_interval_seconds=3.0` → 20 req/min)
    - `rate_limit_window_seconds` -> `60.0`
    - `rate_limit_redis_url` -> falls back to `cache_redis_url`
      (`"redis://localhost:6379/0"` by default)
    - `rate_limit_redis_namespace` -> `"rate-limiter"`
    - `rate_limit_redis_db` -> falls back to `cache_redis_db` (`0` by default)
    - `rate_limit_exempt_paths` -> `frozenset({"/health"})`
    - `rate_limit_aggregator_path_cost` -> `1` (was 3 pre-`rate-limit-followups`;
      the per-source throttles already pace the 3 parallel scraper calls)
    - `rate_limit_per_source_path_cost` -> `1`
    """
    settings = Settings()
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_backend == "memory"
    assert settings.rate_limit_requests == 20
    assert settings.rate_limit_window_seconds == 60.0
    assert settings.rate_limit_redis_url == "redis://localhost:6379/0"  # fell back to cache
    assert settings.rate_limit_redis_namespace == "rate-limiter"
    assert settings.rate_limit_redis_db == 0  # fell back to cache
    assert settings.rate_limit_exempt_paths == frozenset({"/health"})
    assert settings.rate_limit_aggregator_path_cost == 1
    assert settings.rate_limit_per_source_path_cost == 1


# ---------------------------------------------------------------------------
# REQ-RL-008 — AliasChoices work (env-var + lower)
# ---------------------------------------------------------------------------


def test_rate_limit_requests_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`RATE_LIMIT_REQUESTS=10` overrides the default `60` (env-var alias)."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "10")
    settings = Settings()
    assert settings.rate_limit_requests == 10


def test_rate_limit_requests_lower_alias_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`rate_limit_requests=10` (lowercase alias) overrides the default."""
    monkeypatch.setenv("rate_limit_requests", "10")
    settings = Settings()
    assert settings.rate_limit_requests == 10


# ---------------------------------------------------------------------------
# REQ-RL-008 — Cache-Redis fallback semantics
# ---------------------------------------------------------------------------


def test_rate_limit_redis_url_falls_back_to_cache_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `RATE_LIMIT_REDIS_URL` is unset, the field equals `CACHE_REDIS_URL`.

    The model_validator copies `cache_redis_url` into the
    rate-limit field at construction time so callers can
    configure the cache and rate-limiter against the same Redis
    instance with zero extra env vars.
    """
    monkeypatch.setenv("CACHE_REDIS_URL", "redis://cache-host:6379/2")
    # Ensure `RATE_LIMIT_REDIS_URL` is unset.
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    settings = Settings()
    assert settings.rate_limit_redis_url == "redis://cache-host:6379/2"


def test_rate_limit_redis_db_falls_back_to_cache_redis_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `RATE_LIMIT_REDIS_DB` is unset, the field equals `CACHE_REDIS_DB`."""
    monkeypatch.setenv("CACHE_REDIS_DB", "3")
    monkeypatch.delenv("RATE_LIMIT_REDIS_DB", raising=False)
    settings = Settings()
    assert settings.rate_limit_redis_db == 3


def test_explicit_rate_limit_redis_url_wins_over_cache_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `RATE_LIMIT_REDIS_URL` wins over the cache-Redis fallback.

    The fallback is ONLY applied when the rate-limit field is
    unset. An explicit value (any value, including empty) bypasses
    the fallback so a deployment can split the cache and the
    rate-limiter across two Redis instances.
    """
    monkeypatch.setenv("CACHE_REDIS_URL", "redis://cache-host:6379/2")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://rl-host:6379/5")
    settings = Settings()
    assert settings.rate_limit_redis_url == "redis://rl-host:6379/5"
