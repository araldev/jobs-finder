"""Integration tests for the LinkedIn cookie-refresh composition-root wiring
(T-LCR-016, REQ-LCR-007 + REQ-LS-201).

The composition root (`app_factory.build_app()`) wires the
`cookie_refresher` and `cache_invalidator` kwargs into
`LinkedInScraperSettings` per the `linkedin_cookie_refresh_enabled`
+ `LINKEDIN_EMAIL`/`PASSWORD` env-var decision. The 5 tests
below exercise the wiring through `build_app()` and assert:

1. **Enabled + creds** → `LinkedInPlaywrightScraper`'s settings
   have a `PlaywrightLinkedInCookieRefresher` instance.
2. **Disabled** (kill switch via
   `LINKEDIN_COOKIE_REFRESH_ENABLED=false`) → settings have a
   `DisabledLinkedInCookieRefresher` instance.
3. **Missing creds** → also `DisabledLinkedInCookieRefresher`
   (the safety default).
4. **`cache_invalidator=linkedin_cache.clear`** is wired.
5. **`backoff_seconds`** flows from `Settings` env-var override.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.linkedin.cookie_refresher import (
    DisabledLinkedInCookieRefresher,
    PlaywrightLinkedInCookieRefresher,
)
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort

if TYPE_CHECKING:
    pass


def _build_cached_indeed(port: FakeJobSearchPort) -> IndeedSearchJobsUseCase:
    """Build a cached Indeed use case (fake port, no real Playwright)."""
    return IndeedSearchJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )


def _build_cached_infojobs(port: FakeJobSearchPort) -> InfoJobsSearchJobsUseCase:
    """Build a cached InfoJobs use case (fake port, no real Playwright)."""
    return InfoJobsSearchJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )


def _unwrap_to_scraper(app: FastAPI) -> LinkedInPlaywrightScraper | None:
    """Walk one level through `CachedJobSearchUseCase` to the scraper.

    Mirrors `_unwrap_to_port` in `app_factory.py` but stops
    at the `LinkedInPlaywrightScraper` instance (rather than
    any port).
    """
    use_case = getattr(app.state, "use_case", None)
    if use_case is None:
        return None
    inner = getattr(use_case, "_port", None)
    if inner is None:
        return None
    deeper = getattr(inner, "_port", None)
    if deeper is not None:
        result: LinkedInPlaywrightScraper | None = deeper
    else:
        result = inner
    if not isinstance(result, LinkedInPlaywrightScraper):
        return None
    return result


class TestCookieRefreshWiring:
    """T-LCR-016 — composition-root wiring of cookie_refresher + cache_invalidator."""

    def test_wired_app_uses_playwright_refresher_when_enabled_with_creds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_indeed_port: FakeJobSearchPort,
        fake_infojobs_port: FakeJobSearchPort,
    ) -> None:
        """When `linkedin_cookie_refresh_enabled=True` AND both
        `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` env vars are
        set, the composition root wires a
        `PlaywrightLinkedInCookieRefresher` instance.
        """
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "true")
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        # The LinkedIn scraper is built when `use_case is None`,
        # so we don't pass `use_case=` here.
        app = build_app(
            indeed_use_case=_build_cached_indeed(fake_indeed_port),
            infojobs_use_case=_build_cached_infojobs(fake_infojobs_port),
        )
        scraper = _unwrap_to_scraper(app)
        assert scraper is not None
        assert isinstance(
            scraper._settings.cookie_refresher,
            PlaywrightLinkedInCookieRefresher,
        )
        assert scraper._settings.cookie_refresh_enabled is True
        assert scraper._settings.cookie_refresher_backoff_seconds == 3600.0

    def test_wired_app_uses_disabled_refresher_when_kill_switch_off(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_indeed_port: FakeJobSearchPort,
        fake_infojobs_port: FakeJobSearchPort,
    ) -> None:
        """When `LINKEDIN_COOKIE_REFRESH_ENABLED=false`, the
        composition root wires a
        `DisabledLinkedInCookieRefresher` (identity — returns
        the existing cookies unchanged).
        """
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "false")
        # Even with creds set, the kill switch wins.
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        app = build_app(
            indeed_use_case=_build_cached_indeed(fake_indeed_port),
            infojobs_use_case=_build_cached_infojobs(fake_infojobs_port),
        )
        scraper = _unwrap_to_scraper(app)
        assert scraper is not None
        assert isinstance(
            scraper._settings.cookie_refresher,
            DisabledLinkedInCookieRefresher,
        )

    def test_wired_app_uses_disabled_refresher_when_creds_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_indeed_port: FakeJobSearchPort,
        fake_infojobs_port: FakeJobSearchPort,
    ) -> None:
        """When `LINKEDIN_EMAIL` or `LINKEDIN_PASSWORD` is
        missing, the composition root wires a
        `DisabledLinkedInCookieRefresher` (the safety
        default — don't try to log in when we have no
        password).
        """
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "true")
        monkeypatch.delenv("LINKEDIN_EMAIL", raising=False)
        monkeypatch.delenv("LINKEDIN_PASSWORD", raising=False)
        app = build_app(
            indeed_use_case=_build_cached_indeed(fake_indeed_port),
            infojobs_use_case=_build_cached_infojobs(fake_infojobs_port),
        )
        scraper = _unwrap_to_scraper(app)
        assert scraper is not None
        assert isinstance(
            scraper._settings.cookie_refresher,
            DisabledLinkedInCookieRefresher,
        )

    def test_cache_invalidator_is_wired_to_linkedin_cache_clear(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_indeed_port: FakeJobSearchPort,
        fake_infojobs_port: FakeJobSearchPort,
    ) -> None:
        """The composition root wires
        `cache_invalidator=linkedin_cache.clear` so a
        successful refresh invalidates the per-source cache.
        """
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "true")
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        app = build_app(
            indeed_use_case=_build_cached_indeed(fake_indeed_port),
            infojobs_use_case=_build_cached_infojobs(fake_infojobs_port),
        )
        scraper = _unwrap_to_scraper(app)
        assert scraper is not None
        invalidator = scraper._settings.cache_invalidator
        assert invalidator is not None
        assert callable(invalidator)

    def test_backoff_seconds_flows_from_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_indeed_port: FakeJobSearchPort,
        fake_infojobs_port: FakeJobSearchPort,
    ) -> None:
        """`cookie_refresher_backoff_seconds` is sourced from
        `Settings.linkedin_cookie_refresh_backoff_seconds`
        and threaded into `LinkedInScraperSettings`. The
        env var override propagates end-to-end.
        """
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_ENABLED", "true")
        monkeypatch.setenv("LINKEDIN_COOKIE_REFRESH_BACKOFF_SECONDS", "120.0")
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        app = build_app(
            indeed_use_case=_build_cached_indeed(fake_indeed_port),
            infojobs_use_case=_build_cached_infojobs(fake_infojobs_port),
        )
        scraper = _unwrap_to_scraper(app)
        assert scraper is not None
        assert scraper._settings.cookie_refresher_backoff_seconds == 120.0
