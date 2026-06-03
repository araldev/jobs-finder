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
