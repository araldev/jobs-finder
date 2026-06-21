"""Integration tests for the composition-root wiring of the LinkedIn
multi-cookie + playwright-stealth path (T-005 of
`backend-linkedin-stealth`).

Spec coverage (REQ-LST-COOKIE-001 wire + REQ-LST-SCR-001 Stealth wire):
- `app_factory.build_app()` wires `MultiEnvLinkedInAuthCookiesAdapter`
  (4 cookies) when the 4 `LINKEDIN_*` env vars are set; the
  `LinkedInScraperSettings.auth_cookies` slot is a
  `MultiEnvLinkedInAuthCookiesAdapter` instance.
- `app_factory.build_app()` wires `Stealth()` for the production
  wire; the `LinkedInScraperSettings.stealth` slot is a
  `playwright_stealth.Stealth` instance (not `None`).
- The v1 `auth_cookie` slot is `None` in the production wire (the
  v1 adapter is preserved for backward compat with the 35 v1 tests
  that construct it directly).
- The startup WARNING fires when ALL 4 cookies are `None`; it
  does NOT fire when at least 1 cookie is set.

The tests build the app via `build_app(use_case=...)` and inject
fake ports (no Playwright launch) so the test stays offline per
AGENTS.md rule #1. The only thing under test is the
composition-root wiring + the startup WARNING.

The synthetic test values `"AQEAAAAQEAAA"`, `"ajax:12345"`,
`"v2_xyz"`, `"gc_abc"` are the canonical NON-REAL placeholders per
the `backend-linkedin-stealth` exploration (obs #365). Real
LinkedIn cookies are forbidden from the repo by AGENTS.md rule #7.
NOTE: the values `"v2_xyz"` and `"gc_abc"` are 6 chars and would
be rejected by the `Settings._reject_short_*` validators (T-002).
The test uses 8+ char synthetic values (`v2_xyz_padded`,
`gc_abc_padded`) so the validator accepts them — the values are
still obviously non-real. The unit tests in
`test_linkedin_stealth.py` (T-001) construct the adapter directly
(bypassing `Settings`) and use the 6-char sentinels as-is.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.linkedin.auth_cookie import (
    MultiEnvLinkedInAuthCookiesAdapter,
)
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort


def _build_app_with_linkedin_fake() -> object:
    """Build a FastAPI app with a fake LinkedIn port (no Playwright)."""
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = SearchLinkedInJobsUseCase(
        port=linkedin_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )
    return build_app(use_case=linkedin_use_case)


def _build_app_with_production_wire() -> FastAPI:
    """Build a FastAPI app using the production wire (no `use_case=` arg).

    Unlike `_build_app_with_linkedin_fake`, this builder does
    NOT inject a use case — it lets `app_factory.build_app()`
    construct the real `LinkedInPlaywrightScraper` + use case
    chain. The T-005 tests need to assert the
    `LinkedInScraperSettings.auth_cookies` + `stealth` slots on
    the production-wired scraper, which is reachable via
    `app.state.use_case._port._port`.
    """
    return build_app()


class TestBuildAppMultiCookieWire:
    """T-005 of `backend-linkedin-stealth` — the composition root
    wires the new `MultiEnvLinkedInAuthCookiesAdapter` (NOT the v1
    `EnvLinkedInAuthCookieAdapter`) + `Stealth()`.
    """

    def test_build_app_wires_multi_env_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`build_app()` wires `MultiEnvLinkedInAuthCookiesAdapter` (not v1).

        The 4 LINKEDIN_* env vars are set; the resulting scraper's
        `LinkedInScraperSettings.auth_cookies` MUST be a
        `MultiEnvLinkedInAuthCookiesAdapter` (NOT the v1
        single-cookie shim); the `auth_cookie` slot MUST be `None`
        (the v1 slot is kept for backward compat with the 35 v1
        tests that construct `EnvLinkedInAuthCookieAdapter`
        directly).
        """
        from playwright_stealth import Stealth  # type: ignore[import-untyped]  # noqa: PLC0415

        # The factory prefers the JsonLinkedInAuthCookiesAdapter when a
        # linkedin_cookies.json is present in the repo root (e.g., from a
        # prior manual capture). Force the Json adapter to "no cookies" so
        # the MultiEnv adapter from env vars is wired instead — this is
        # what the test asserts.
        from jobs_finder.infrastructure.linkedin import auth_cookie as ac_module

        def _json_cookies_none(self: object) -> None:
            return None

        monkeypatch.setattr(ac_module.JsonLinkedInAuthCookiesAdapter, "cookies", _json_cookies_none)
        # Also force the constructor to NOT find the file by stubbing the
        # path resolution. The simpler path is the .cookies() override above.
        monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
        monkeypatch.setenv("LINKEDIN_JSESSIONID", "ajax:12345678")
        monkeypatch.setenv("LINKEDIN_BCOOKIE", "v2_xyz_padded")
        monkeypatch.setenv("LINKEDIN_LI_GC", "gc_abc_padded")
        monkeypatch.setenv("LINKEDIN_BSCOOKIE", "bs_xyz_padded")
        # NOTE: the values `"ajax:12345"`, `"v2_xyz"`, `"gc_abc"`
        # from the orchestrator's spec (the canonical sentinels)
        # are <8 chars and would be rejected by the
        # `Settings._reject_short_*` validators (T-002 of
        # `backend-linkedin-stealth`). The test uses 8+ char
        # synthetic values (still obviously non-real) so the
        # validator accepts them.
        app = _build_app_with_production_wire()
        # Reach into the wired scraper via the use case chain.
        # `app.state.use_case` is the `CachedJobSearchUseCase`;
        # `._port` is the `RawLinkedInJobsUseCase`; `._port` is
        # the `LinkedInPlaywrightScraper` (the production wire).
        use_case = app.state.use_case
        raw_use_case = use_case._port
        scraper = raw_use_case._port
        assert isinstance(
            scraper._settings.auth_cookies,
            MultiEnvLinkedInAuthCookiesAdapter,
        )
        # v1 `auth_cookie` slot is None in the production wire.
        assert scraper._settings.auth_cookie is None
        # `Stealth()` is wired (not `None`).
        assert scraper._settings.stealth is not None
        assert isinstance(scraper._settings.stealth, Stealth)

    def test_build_app_emits_startup_warning_when_all_cookies_unset(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`build_app()` with ALL 4 `LINKEDIN_*` env vars unset emits 1 WARNING.

        The T-005 startup WARNING has the prefix
        `"LinkedIn scraper running without any auth cookies; SERP
        will hit the Cloudflare / auth wall and return a reduced
        list"`. The v1 message was the shorter
        `"LinkedIn scraper running without auth cookie"` prefix;
        the new message is a strict superset that covers all 4
        cookies (the operator may have set any of the 4 in
        practice; the WARNING is only suppressed when AT LEAST 1
        is set).
        """
        monkeypatch.delenv("LINKEDIN_LI_AT", raising=False)
        monkeypatch.delenv("LINKEDIN_JSESSIONID", raising=False)
        monkeypatch.delenv("LINKEDIN_BCOOKIE", raising=False)
        monkeypatch.delenv("LINKEDIN_LI_GC", raising=False)
        with caplog.at_level(logging.WARNING):
            _build_app_with_linkedin_fake()
        matching = [
            r
            for r in caplog.records
            if "LinkedIn scraper running without any auth cookies" in r.getMessage()
        ]
        assert len(matching) == 1, f"expected exactly 1 startup WARNING, got {len(matching)}"
        # The message names the 4 env vars (the operator's
        # recovery path is to set at least 1).
        msg = matching[0].getMessage()
        assert "LINKEDIN_LI_AT" in msg

    def test_build_app_no_startup_warning_when_at_least_one_cookie_set(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`build_app()` with at least 1 `LINKEDIN_*` env var set emits NO WARNING.

        The T-005 startup WARNING is gated on ALL 4 cookies
        being `None`. When at least 1 is set, the warning is
        suppressed (the operator has opted in to the
        authenticated path).
        """
        monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
        monkeypatch.delenv("LINKEDIN_JSESSIONID", raising=False)
        monkeypatch.delenv("LINKEDIN_BCOOKIE", raising=False)
        monkeypatch.delenv("LINKEDIN_LI_GC", raising=False)
        with caplog.at_level(logging.WARNING):
            _build_app_with_linkedin_fake()
        matching = [
            r
            for r in caplog.records
            if "LinkedIn scraper running without any auth cookies" in r.getMessage()
        ]
        assert matching == []
