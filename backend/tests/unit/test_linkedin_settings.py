"""Unit tests for `LinkedInScraperSettings` (renamed) and the new
LinkedIn-specific `Settings` env vars.

Spec: REQ-L-008.

The in-module settings class was `ScraperSettings`; this change renames
it to `LinkedInScraperSettings` for symmetry with `IndeedScraperSettings`
and `InfoJobsScraperSettings`. It gains two keyword-only fields:
`max_pages: int = 10` and `inter_page_delay_seconds: float = 1.0`. The
`Settings` class grows two LinkedIn-specific fields with their own
`LINKEDIN_*` env-var aliases:
`linkedin_max_pages` (env `LINKEDIN_MAX_PAGES`, default 10) and
`linkedin_inter_page_delay_seconds` (env
`LINKEDIN_INTER_PAGE_DELAY_SECONDS`, default 1.0).

The existing `LINKEDIN_*` env vars (`THROTTLE_SECONDS`, `USER_AGENT`,
`REQUEST_TIMEOUT_MS`, `CORS_ALLOW_ORIGINS`, `LOG_LEVEL`, `LOG_FORMAT`,
`HEADLESS`) keep working — regression checks in
`test_existing_linkedin_env_vars_remain_unchanged` pin that contract.

This file is the RED → GREEN → REFACTOR anchor for T-001.a of the
`linkedin-pagination` change. It must be authored BEFORE the
production code is updated, run to confirm it fails (RED), then the
rename + new fields are landed in `scraper.py` + `config.py`, then
the test passes (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

import pytest

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.linkedin.scraper import LinkedInScraperSettings

# ---------------------------------------------------------------------------
# `LinkedInScraperSettings` (REQ-L-008, part 1) — new in-module class.
# Mirrors `IndeedScraperSettings` / `InfoJobsScraperSettings`.
# ---------------------------------------------------------------------------


def test_linkedin_scraper_settings_default_max_pages_is_ten() -> None:
    """A fresh `LinkedInScraperSettings(user_agent, timeout_ms)` defaults
    `max_pages` to `10` (REQ-L-008 — mirror the Indeed default)."""
    settings = LinkedInScraperSettings(user_agent="ua", timeout_ms=10_000)
    assert settings.max_pages == 10


def test_linkedin_scraper_settings_default_inter_page_delay_is_one() -> None:
    """A fresh `LinkedInScraperSettings(user_agent, timeout_ms)` defaults
    `inter_page_delay_seconds` to `1.0` (REQ-L-008 — mirror the Indeed default)."""
    settings = LinkedInScraperSettings(user_agent="ua", timeout_ms=10_000)
    assert settings.inter_page_delay_seconds == 1.0


def test_linkedin_scraper_settings_equality_covers_new_fields() -> None:
    """`==` returns `False` when two settings differ only in `max_pages`
    or `inter_page_delay_seconds` (REQ-L-008 — the rename requires
    `__eq__` / `__hash__` / `__repr__` to cover ALL four slots)."""
    a = LinkedInScraperSettings(user_agent="ua", timeout_ms=10_000)
    b = LinkedInScraperSettings(
        user_agent="ua", timeout_ms=10_000, max_pages=3
    )  # different max_pages
    c = LinkedInScraperSettings(
        user_agent="ua", timeout_ms=10_000, inter_page_delay_seconds=2.5
    )  # different inter_page_delay_seconds
    assert a != b
    assert a != c


def test_linkedin_scraper_settings_repr_mentions_new_fields() -> None:
    """`__repr__` exposes both new fields so a debugging log line is
    useful (REQ-L-008 — `__repr__` covers all four slots)."""
    settings = LinkedInScraperSettings(
        user_agent="ua",
        timeout_ms=10_000,
        max_pages=3,
        inter_page_delay_seconds=2.5,
    )
    rendered = repr(settings)
    assert "max_pages=3" in rendered
    assert "inter_page_delay_seconds=2.5" in rendered


# ---------------------------------------------------------------------------
# `Settings` — new LinkedIn-specific env vars (REQ-L-008, part 2).
# Both fields use per-field `validation_alias=AliasChoices("LINKEDIN_*", "*")`
# so the env-var lookup reads the `LINKEDIN_*` env var (matching the
# Indeed/InfoJobs per-field alias pattern) AND the model-level
# `env_prefix="LINKEDIN_"` continues to drive the existing fields.
# ---------------------------------------------------------------------------


def test_settings_linkedin_max_pages_default_is_ten() -> None:
    """`Settings().linkedin_max_pages` defaults to `10` (REQ-L-008)."""
    assert Settings().linkedin_max_pages == 10


def test_settings_linkedin_inter_page_delay_seconds_default_is_one() -> None:
    """`Settings().linkedin_inter_page_delay_seconds` defaults to `1.0` (REQ-L-008)."""
    assert Settings().linkedin_inter_page_delay_seconds == 1.0


def test_settings_linkedin_max_pages_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LINKEDIN_MAX_PAGES=3` overrides the default `10` (REQ-L-008)."""
    monkeypatch.setenv("LINKEDIN_MAX_PAGES", "3")
    assert Settings().linkedin_max_pages == 3


def test_settings_linkedin_inter_page_delay_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LINKEDIN_INTER_PAGE_DELAY_SECONDS=0.5` overrides the default `1.0`
    (REQ-L-008)."""
    monkeypatch.setenv("LINKEDIN_INTER_PAGE_DELAY_SECONDS", "0.5")
    assert Settings().linkedin_inter_page_delay_seconds == 0.5


def test_settings_linkedin_max_pages_programmatic_construction_works() -> None:
    """`Settings(linkedin_max_pages=7)` works (second choice in `AliasChoices`
    preserves the programmatic-construction path)."""
    assert Settings(linkedin_max_pages=7).linkedin_max_pages == 7


# ---------------------------------------------------------------------------
# Regression: the existing LinkedIn fields are unchanged.
# ---------------------------------------------------------------------------


def test_existing_linkedin_user_agent_default_is_unchanged() -> None:
    """`Settings().user_agent` (LinkedIn) still defaults to the stealth UA."""
    settings = Settings()
    assert "Mozilla" in settings.user_agent
    assert "Chrome" in settings.user_agent


def test_existing_linkedin_throttle_seconds_default_is_unchanged() -> None:
    """`Settings().throttle_seconds` (LinkedIn) still defaults to `3.0`."""
    assert Settings().throttle_seconds == 3.0


def test_existing_linkedin_request_timeout_ms_default_is_unchanged() -> None:
    """`Settings().request_timeout_ms` (LinkedIn) still defaults to `10_000`."""
    assert Settings().request_timeout_ms == 10_000


def test_existing_linkedin_env_vars_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting `LINKEDIN_USER_AGENT` / `LINKEDIN_THROTTLE_SECONDS` /
    `LINKEDIN_REQUEST_TIMEOUT_MS` continues to override the original
    LinkedIn fields. REQ-L-008 invariant: "Existing `LINKEDIN_*` env vars
    keep working"."""
    monkeypatch.setenv("LINKEDIN_USER_AGENT", "CustomUA/1.0")
    monkeypatch.setenv("LINKEDIN_THROTTLE_SECONDS", "7.5")
    monkeypatch.setenv("LINKEDIN_REQUEST_TIMEOUT_MS", "12345")
    settings = Settings()
    assert settings.user_agent == "CustomUA/1.0"
    assert settings.throttle_seconds == 7.5
    assert settings.request_timeout_ms == 12_345


def test_linkedin_env_vars_dont_cross_bleed_with_indeed_or_infojobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the new `LINKEDIN_MAX_PAGES` /
    `LINKEDIN_INTER_PAGE_DELAY_SECONDS` env vars do NOT bleed into the
    Indeed or InfoJobs fields, and vice versa (each source's env var
    maps to its own field only)."""
    monkeypatch.setenv("LINKEDIN_MAX_PAGES", "3")
    monkeypatch.setenv("LINKEDIN_INTER_PAGE_DELAY_SECONDS", "0.7")
    monkeypatch.setenv("INDEED_MAX_PAGES", "4")
    monkeypatch.setenv("INFOJOBS_MAX_PAGES", "5")
    settings = Settings()
    assert settings.linkedin_max_pages == 3
    assert settings.linkedin_inter_page_delay_seconds == 0.7
    assert settings.indeed_max_pages == 4
    assert settings.infojobs_max_pages == 5


# ---------------------------------------------------------------------------
# `LinkedInScraperSettings.location_resolver` field (REQ-LOC-002, T-001)
#
# The `location_resolver: LocationResolverPort | None = None` field
# is added to the settings dataclass in the
# `backend-scraper-query-tuning` change. It MUST be optional with
# a `None` default (preserves backward compat with pre-change
# constructors), and `__eq__` / `__hash__` MUST include the new
# field so two settings with different resolvers are NOT
# `==`-equal (a hash collision in `app.state` would silently
# misroute the resolver).
# ---------------------------------------------------------------------------


def test_settings_optional_resolver_defaults_to_none() -> None:
    """`LinkedInScraperSettings(user_agent, timeout_ms)` → `location_resolver is None`.

    The new `location_resolver` field defaults to `None` so a
    pre-change caller that constructs the settings with the 4
    documented keyword args continues to work. The default
    preserves the v1 contract: a scraper built without a
    resolver falls back to `?location=<str>` (the broken path).
    """
    settings = LinkedInScraperSettings(user_agent="ua", timeout_ms=10_000)
    assert settings.location_resolver is None


def test_settings_equality_includes_resolver() -> None:
    """Two `LinkedInScraperSettings` differing ONLY in `location_resolver` are NOT `==`.

    The `__eq__` and `__hash__` methods on `LinkedInScraperSettings`
    MUST include the new `location_resolver` field. A regression
    that omits the field from `__eq__` would cause two scrapers
    with different resolvers to be `==`-equal; the first-registered
    resolver would shadow the second in any dict-keyed state.
    The test pins the contract: two settings with identical
    scalars but different resolvers are NOT equal.
    """

    class _StubResolver:
        def resolve(self, location: str) -> int | None:  # pragma: no cover
            return None

        def resolve_infojobs(  # pragma: no cover
            self, location: str
        ) -> tuple[int | None, int | None]:
            # REQ-PROV-004 backward-compat: pre-change test
            # doubles grow the second Protocol method with a
            # default `(None, None)` return. The settings test
            # never exercises InfoJobs, so the default is
            # sufficient.
            return (None, None)

        def resolve_structured(  # pragma: no cover
            self, location: str
        ) -> tuple[str, str, str] | None:
            return None

    a = LinkedInScraperSettings(user_agent="ua", timeout_ms=10_000)
    b = LinkedInScraperSettings(
        user_agent="ua",
        timeout_ms=10_000,
        location_resolver=_StubResolver(),
    )
    assert a != b
    # `__hash__` is also updated: the two settings have
    # different hashes (not a strict requirement, but pins
    # the contract that `__eq__` and `__hash__` agree).
    assert hash(a) != hash(b)


# ---------------------------------------------------------------------------
# `Settings` — `linkedin_cookie_refresh_*` fields
# (REQ-CF-301/302/303 — `linkedin-cookie-refresh` cycle 4).
#
# The 3 fields below are the kill switch + backoff + timeout for
# the new auto-refresh feature. Each declares its own
# `validation_alias` (`LINKEDIN_COOKIE_REFRESH_*` ↔ lowercase
# programmatic) per the pattern used by the existing
# `linkedin_max_pages` / `linkedin_inter_page_delay_seconds` /
# `indeed_*` / `infojobs_*` fields.
#
# Defaults:
#   - `enabled` defaults to `True` (REQ-CF-301: zero-touch
#     operation is the user's stated intent; the env var is
#     an explicit opt-OUT).
#   - `backoff_seconds` defaults to `3600.0` (REQ-CF-302: 1 hour
#     prevents refresh-storm on per-scheduler-cycle cadence of
#     ~25-35 min).
#   - `timeout_seconds` defaults to `300.0` (REQ-CF-303: matches
#     the existing `extract_linkedin_cookies.py` poll-up-to-300s
#     precedent).
# ---------------------------------------------------------------------------


def test_settings_linkedin_cookie_refresh_enabled_default_is_true() -> None:
    """REQ-CF-301 — `Settings().linkedin_cookie_refresh_enabled` defaults to `True`.

    Zero-touch operation is the user's stated intent; the env
    var is the explicit opt-OUT (set to `false` to disable).
    """
    assert Settings().linkedin_cookie_refresh_enabled is True


def test_settings_linkedin_cookie_refresh_enabled_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-CF-301 — `LINKEDIN_COOKIE_REFRESH_ENABLED=false` overrides the default.

    pydantic-settings auto-coerces `"false"` / `"0"` / `"no"` to
    `bool(False)`. The default `True` is replaced.
    """
    monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "false")
    assert Settings().linkedin_cookie_refresh_enabled is False


def test_settings_linkedin_cookie_refresh_enabled_programmatic_construction_works() -> None:
    """REQ-CF-301 — programmatic `Settings(linkedin_cookie_refresh_enabled=...)` works."""
    assert Settings(linkedin_cookie_refresh_enabled=False).linkedin_cookie_refresh_enabled is False


def test_settings_linkedin_cookie_refresh_backoff_seconds_default_is_3600() -> None:
    """REQ-CF-302 — `Settings().linkedin_cookie_refresh_backoff_seconds` defaults to `3600.0`.

    1 hour — the recommended value to prevent refresh-storm
    on per-scheduler-cycle cadence (~25-35 min).
    """
    assert Settings().linkedin_cookie_refresh_backoff_seconds == 3600.0


def test_settings_linkedin_cookie_refresh_backoff_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-CF-302 — `LINKEDIN_COOKIE_REFRESH_BACKOFF_SECONDS=120.0` overrides the default."""
    monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_BACKOFF_SECONDS", "120.0")
    assert Settings().linkedin_cookie_refresh_backoff_seconds == 120.0


def test_settings_linkedin_cookie_refresh_backoff_seconds_rejects_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-CF-302 — `backoff_seconds=0` is rejected (gt=0.0).

    The `gt=0.0` constraint enforces positive backoff. A
    zero backoff would disable backoff entirely, which the
    spec explicitly forbids (operators must use
    `linkedin_cookie_refresh_enabled=False` for that).
    """
    from pydantic import ValidationError

    monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_BACKOFF_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_linkedin_cookie_refresh_timeout_seconds_default_is_300() -> None:
    """REQ-CF-303 — `Settings().linkedin_cookie_refresh_timeout_seconds` defaults to `300.0`."""
    assert Settings().linkedin_cookie_refresh_timeout_seconds == 300.0


def test_settings_linkedin_cookie_refresh_timeout_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-CF-303 — `LINKEDIN_COOKIE_REFRESH_TIMEOUT_SECONDS=60.0` overrides the default."""
    monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_TIMEOUT_SECONDS", "60.0")
    assert Settings().linkedin_cookie_refresh_timeout_seconds == 60.0


def test_settings_linkedin_cookie_refresh_timeout_seconds_rejects_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-CF-303 — `timeout_seconds=0` is rejected (gt=0.0).

    A zero timeout would immediately time out — meaningless.
    """
    from pydantic import ValidationError

    monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()
