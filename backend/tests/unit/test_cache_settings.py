"""Unit tests for the new `cache_ttl_seconds` Settings field.

Spec: REQ-C-002.

`Settings.cache_ttl_seconds: float = Field(default=60.0, validation_alias=...)`.
The env var is `CACHE_TTL_SECONDS` (case-insensitive, with the
`cache_ttl_seconds` programmatic alias as the second choice). Default
60.0; setting to 0.0 disables the cache (every call is a miss).
"""

from __future__ import annotations

import pytest

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# Default
# ---------------------------------------------------------------------------


def test_cache_ttl_seconds_default_is_sixty() -> None:
    """`cache_ttl_seconds` defaults to `60.0` (per REQ-C-002)."""
    settings = Settings()
    assert settings.cache_ttl_seconds == 60.0


def test_cache_ttl_seconds_is_a_float() -> None:
    """The default is a Python `float`, not an int."""
    settings = Settings()
    assert isinstance(settings.cache_ttl_seconds, float)


# ---------------------------------------------------------------------------
# Env-var override
# ---------------------------------------------------------------------------


def test_cache_ttl_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CACHE_TTL_SECONDS=120` overrides the default `60.0`."""
    monkeypatch.setenv("CACHE_TTL_SECONDS", "120")
    settings = Settings()
    assert settings.cache_ttl_seconds == 120.0


def test_cache_ttl_seconds_env_var_accepts_fractional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CACHE_TTL_SECONDS=0.5` overrides the default with a fractional value."""
    monkeypatch.setenv("CACHE_TTL_SECONDS", "0.5")
    settings = Settings()
    assert settings.cache_ttl_seconds == 0.5


def test_cache_ttl_seconds_zero_disables_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CACHE_TTL_SECONDS=0` overrides the default with `0.0` (cache disabled)."""
    monkeypatch.setenv("CACHE_TTL_SECONDS", "0")
    settings = Settings()
    assert settings.cache_ttl_seconds == 0.0


# ---------------------------------------------------------------------------
# Programmatic constructor override
# ---------------------------------------------------------------------------


def test_cache_ttl_seconds_programmatic_override() -> None:
    """`Settings(cache_ttl_seconds=300.0)` sets the field directly."""
    settings = Settings(cache_ttl_seconds=300.0)
    assert settings.cache_ttl_seconds == 300.0


# ---------------------------------------------------------------------------
# Regression: existing LinkedIn / Indeed / InfoJobs fields are unchanged.
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


# ---------------------------------------------------------------------------
# Persistent-cache backend + Redis config (REQ-PC-004, persistent-cache change)
#
# The 4 new fields + the namespace validator are exercised below. The
# defaults pin the in-memory backend (preserving the pre-persistent-cache
# behavior) and a localhost Redis URL (no production bias). The validator
# rejects empty and `:`-containing namespace values so misconfiguration
# surfaces at startup, not on the first cache write.
# ---------------------------------------------------------------------------


def test_cache_backend_default_is_memory() -> None:
    """REQ-PC-004: `cache_backend` defaults to `\"memory\"` (in-memory TTL cache)."""
    settings = Settings()
    assert settings.cache_backend == "memory"


def test_cache_redis_url_default_is_localhost() -> None:
    """REQ-PC-004: `cache_redis_url` defaults to `\"redis://localhost:6379/0\"`."""
    settings = Settings()
    assert settings.cache_redis_url == "redis://localhost:6379/0"


def test_cache_redis_namespace_default_is_jobs_finder() -> None:
    """REQ-PC-004: `cache_redis_namespace` defaults to `\"jobs-finder\"`."""
    settings = Settings()
    assert settings.cache_redis_namespace == "jobs-finder"


def test_cache_backend_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQ-PC-004: `CACHE_BACKEND=redis` overrides the default to `\"redis\"`."""
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    settings = Settings()
    assert settings.cache_backend == "redis"


def test_cache_redis_namespace_with_colon_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-PC-004: a `:` in `CACHE_REDIS_NAMESPACE` is rejected at construction.

    The runtime key format is `f\"{ns}:{source}:{hash}\"`. A `:` in the
    namespace would let two deployments share a key prefix and is
    rejected so misconfiguration surfaces at startup, not on the
    first cache write.
    """
    monkeypatch.setenv("CACHE_REDIS_NAMESPACE", "foo:bar")
    with pytest.raises(ValueError, match="must not contain ':'"):
        Settings()
