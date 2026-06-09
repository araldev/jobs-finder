"""Unit tests for the `Settings` fields added for the rate limiter.

Spec: REQ-RL-008.

`Settings` adds 11 new fields (10 + 1 for the `rate-limit-followups`
change: `rate_limit_trusted_proxies`), each with
`validation_alias=AliasChoices("RATE_LIMIT_*", "rate_limit_*")`. The
`RATE_LIMIT_REDIS_URL` and `RATE_LIMIT_REDIS_DB` fields have a
computed fallback to `cache_redis_url` / `cache_redis_db` when unset
(via a `model_validator(mode="after")`, NOT `AliasChoices` — those
don't support computed fallbacks). `RATE_LIMIT_EXEMPT_PATHS` parses
a JSON list per the spec's OQ-B (Pydantic-friendly format).
`RATE_LIMIT_TRUSTED_PROXIES` parses a JSON list of CIDR strings
into a `frozenset[IPv4Network | IPv6Network]` (REQ-RL-008 scenarios
8, 9, 10; REQ-RL-011).

The 10 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

import ipaddress

import pytest
from pydantic import ValidationError

from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# REQ-RL-008 — Defaults (1 scenario, 10 sub-assertions)
# ---------------------------------------------------------------------------


def test_rate_limit_settings_defaults_match_spec() -> None:
    """Fresh `Settings()` exposes the 11 documented defaults (REQ-RL-008 defaults row).

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
    - `rate_limit_trusted_proxies` -> `frozenset()` (NEW in
      `rate-limit-followups`; the security default — no proxy trust,
      `X-Forwarded-For` is ignored. Spec REQ-RL-011.)
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
    assert settings.rate_limit_trusted_proxies == frozenset()


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


# ---------------------------------------------------------------------------
# REQ-RL-008 (scenarios 8, 9, 10) + REQ-RL-011 — TRUSTED_PROXIES env-var
#
# `RATE_LIMIT_TRUSTED_PROXIES` is a JSON list of CIDR strings (e.g.
# `'["10.0.0.0/8","::1/128"]'`). The `field_validator(mode="before")`
# parses each entry with `ipaddress.ip_network(s, strict=False)` and
# returns a `frozenset[IPv4Network | IPv6Network]`. Invalid CIDR or
# malformed JSON raises `pydantic.ValidationError` at startup so
# misconfiguration surfaces immediately, not on the first request.
# ---------------------------------------------------------------------------


def test_rate_limit_trusted_proxies_env_var_parses_json_cidr_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8","::1/128"]'` parses to a frozenset.

    REQ-RL-008 scenario 8 (rate-limit-followups): the JSON-list
    env-var is parsed into a 2-element frozenset with one
    `IPv4Network` and one `IPv6Network`.
    """
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", '["10.0.0.0/8", "192.168.0.0/16", "::1/128"]')
    settings = Settings()
    assert isinstance(settings.rate_limit_trusted_proxies, frozenset)
    assert len(settings.rate_limit_trusted_proxies) == 3
    assert ipaddress.IPv4Network("10.0.0.0/8") in settings.rate_limit_trusted_proxies
    assert ipaddress.IPv4Network("192.168.0.0/16") in settings.rate_limit_trusted_proxies
    assert ipaddress.IPv6Network("::1/128") in settings.rate_limit_trusted_proxies


def test_rate_limit_trusted_proxies_invalid_cidr_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid CIDR in `RATE_LIMIT_TRUSTED_PROXIES` raises `ValidationError` at startup.

    REQ-RL-008 scenario 9 (rate-limit-followups): the
    `field_validator` calls `ipaddress.ip_network("not-a-cidr", strict=False)`
    which raises `ValueError`; Pydantic surfaces it as a
    `ValidationError`. Misconfiguration fails fast (at app
    construction), not lazily (on the first 429).
    """
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", '["not-a-cidr"]')
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    # The error message mentions the bad value so the operator
    # can grep the boot log for the misconfigured CIDR.
    assert "not-a-cidr" in str(exc_info.value)


def test_rate_limit_trusted_proxies_malformed_json_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON in `RATE_LIMIT_TRUSTED_PROXIES` raises at startup.

    REQ-RL-008 scenario 10 (rate-limit-followups): a
    `'[unclosed'` value (missing closing bracket) fails to parse.
    `pydantic_settings` raises `SettingsError` (a `ValueError`
    subclass) BEFORE the `mode="before"` validator runs. Both
    `pydantic.ValidationError` and `pydantic_settings.SettingsError`
    are `ValueError` subclasses, so the test asserts on
    `ValueError` to cover both paths. The spec's intent is
    "malformed JSON fails fast at startup" — the exact exception
    class is an implementation detail.
    """
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", "[unclosed")
    with pytest.raises(ValueError) as exc_info:
        Settings()
    # The error message surfaces the malformed JSON so the
    # operator can find the env-var in the deployment manifest.
    error_text = str(exc_info.value)
    assert (
        "unclosed" in error_text
        or "JSON" in error_text.upper()
        or "rate_limit_trusted_proxies" in error_text.lower()
    )
