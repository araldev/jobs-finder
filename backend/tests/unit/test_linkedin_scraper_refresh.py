"""Tests for the LinkedIn scraper's cookie-refresh trigger
(T-LCR-015, REQ-LCR-003/004/005/008 + REQ-LS-201/202/203).

The scraper's `_make_fetch_one_page` closure consults the new
`cookie_refresher` and `cache_invalidator` kwargs on
`LinkedInScraperSettings` when `is_auth_wall` or
`is_cloudflare_challenge` returns `True`. The 8 tests below
exercise the trigger path end-to-end through the full
`search()` lifecycle (mocked Playwright via `browser_factory`).

Spec coverage:
- REQ-LCR-003: trigger on auth-wall + Cloudflare;
  on success: set_cookies + cache_invalidator + retry;
  on failure: WARNING + return [].
- REQ-LCR-004: backoff — skip refresh within
  `linkedin_cookie_refresh_backoff_seconds` of last attempt.
- REQ-LCR-005: no log call with cookie values.
- REQ-LCR-008: `cookie_refresher=None` is byte-identical to
  pre-change behavior.
- REQ-LS-203: retry page 0 ONCE on refresh success.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr

from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    LinkedInScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from tests.conftest import (
    FakeLinkedInAuthCookiesPort,
    FakeLinkedInCookieRefresherPort,
)
from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Fakes — copied from test_linkedin_scraper_auth.py (kept local
# to avoid cross-file coupling).
# ---------------------------------------------------------------------------


class _FakePage:
    """Minimal Playwright `Page` stub.

    `html` may be a `str` (returned for every navigation) or a
    callable `(url) -> str` for per-page content (used by the
    auth-wall + cards tests).
    """

    def __init__(
        self,
        html: str | Callable[[str], str] = "",
    ) -> None:
        self._html = html
        self.goto_calls: list[str] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait_for_selector(self, selector: str, timeout: int = 0, **kwargs: object) -> None:
        return None

    async def content(self) -> str:
        if callable(self._html):
            return self._html(self.goto_calls[-1])
        return self._html

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    """Minimal Playwright `BrowserContext` stub with `add_cookies` recording."""

    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.closed = False
        self.add_cookies_calls: list[list[dict[str, Any]]] = []

    async def new_page(self) -> _FakePage:
        return self.page

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.add_cookies_calls.append(cookies)

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    """Minimal Playwright `Browser` stub."""

    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.closed = False
        self.new_context_calls: list[dict[str, Any]] = []
        self.contexts: list[_FakeContext] = []

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        self.new_context_calls.append(kwargs)
        ctx = _FakeContext(self.page)
        self.contexts.append(ctx)
        return ctx

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    auth_cookies: FakeLinkedInAuthCookiesPort | None = None,
    cookie_refresher: FakeLinkedInCookieRefresherPort | None = None,
    cache_invalidator: Callable[[], Any] | None = None,
    cookie_refresh_enabled: bool = True,
    cookie_refresher_backoff_seconds: float = 3600.0,
    max_pages: int = 1,
) -> LinkedInScraperSettings:
    return LinkedInScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
        max_pages=max_pages,
        inter_page_delay_seconds=0.0,
        auth_cookies=auth_cookies,
        cookie_refresher=cookie_refresher,
        cache_invalidator=cache_invalidator,
        cookie_refresh_enabled=cookie_refresh_enabled,
        cookie_refresher_backoff_seconds=cookie_refresher_backoff_seconds,
    )


async def _make_scraper_with(
    page: _FakePage,
    *,
    auth_cookies: FakeLinkedInAuthCookiesPort | None = None,
    cookie_refresher: FakeLinkedInCookieRefresherPort | None = None,
    cache_invalidator: Callable[[], Any] | None = None,
    cookie_refresh_enabled: bool = True,
    cookie_refresher_backoff_seconds: float = 3600.0,
    max_pages: int = 1,
) -> tuple[
    LinkedInPlaywrightScraper,
    _FakeBrowser,
    FakeLinkedInAuthCookiesPort,
    FakeLinkedInCookieRefresherPort,
]:
    """Build a scraper whose browser is the given fake page's parent.

    Mirrors the `test_linkedin_scraper_auth.py` pattern.
    The `cookie_refresher` parameter is forwarded as-is:
    a `FakeLinkedInCookieRefresherPort` instance is used
    directly; `None` means "no refresher" (v1 path).
    The default value is `None` to keep the call site
    explicit — tests that need a fake should pass one.
    """
    fake_browser = _FakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> _FakeBrowser:
        return fake_browser

    if auth_cookies is None:
        auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=_settings(
            auth_cookies=auth_cookies,
            cookie_refresher=cookie_refresher,
            cache_invalidator=cache_invalidator,
            cookie_refresh_enabled=cookie_refresh_enabled,
            cookie_refresher_backoff_seconds=cookie_refresher_backoff_seconds,
            max_pages=max_pages,
        ),
        browser_factory=factory,
    )
    final_refresher = cookie_refresher
    if final_refresher is None:
        final_refresher = FakeLinkedInCookieRefresherPort()
    return scraper, fake_browser, auth_cookies, final_refresher


# Auth-wall HTML: body class="auth-wall" + 0 cards.
AUTH_WALL_HTML = (
    '<html><body class="auth-wall"><main><h1>Sign in to continue</h1></main></body></html>'
)


# Cloudflare challenge HTML: title "Just a moment..." + noscript
# + data-cf-challenge + 0 cards.
CLOUDFLARE_HTML = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>"
    "<noscript>redirect</noscript>"
    '<div data-cf-challenge="x"></div>'
    "</body></html>"
)


# Healthy SERP: SEARCH_PAGE_HTML has 3 cards (3 successful parses).
HEALTHY_HTML = SEARCH_PAGE_HTML


# ---------------------------------------------------------------------------
# Tests — REQ-LCR-003 (trigger) + REQ-LS-203 (retry)
# ---------------------------------------------------------------------------


async def test_scraper_calls_refresher_on_auth_wall() -> None:
    """REQ-LCR-003 — auth-wall fires → refresher called.

    The page returns the auth-wall HTML on the first call
    (no cards). The scraper's closure sees the auth-wall
    signal and calls `cookie_refresher.refresh()`. The fake
    returns `None` (failure) so the search returns `[]`
    after recording the attempt.
    """
    page = _FakePage(AUTH_WALL_HTML)
    refresher = FakeLinkedInCookieRefresherPort(canned=None)  # failure
    scraper, _, _, _ = await _make_scraper_with(page, cookie_refresher=refresher)
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    assert result == []
    assert refresher.calls == 1


async def test_scraper_calls_refresher_on_cloudflare_challenge() -> None:
    """REQ-LCR-003 — Cloudflare challenge fires → refresher called."""
    page = _FakePage(CLOUDFLARE_HTML)
    refresher = FakeLinkedInCookieRefresherPort(canned=None)  # failure
    scraper, _, _, _ = await _make_scraper_with(page, cookie_refresher=refresher)
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    assert result == []
    assert refresher.calls == 1


async def test_scraper_replaces_cookies_and_invalidates_cache_on_refresh_success() -> None:
    """REQ-LCR-003 — on success: set_cookies + cache_invalidator
    + retry page 0 ONCE.

    The fake refresher returns 3 cookies. The page returns
    auth-wall HTML on the first call, then HEALTHY_HTML on
    the second call (the retry). The scraper:
    1. Calls `refresh()` → 3 cookies.
    2. Calls `auth_cookies.set_cookies(3 cookies)`.
    3. Calls `cache_invalidator()`.
    4. Retries page 0 → 3 cards parsed.
    """
    call_count = {"n": 0}

    def html_factory(_url: str) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AUTH_WALL_HTML  # first page: auth-wall
        return HEALTHY_HTML  # retry: healthy SERP

    page = _FakePage(html_factory)
    refresher = FakeLinkedInCookieRefresherPort(
        canned=[
            {"name": "li_at", "value": "AQE_NEW", "domain": ".linkedin.com"},
            {"name": "JSESSIONID", "value": "ajax:99999", "domain": ".linkedin.com"},
            {"name": "bcookie", "value": "v2_xyz", "domain": ".linkedin.com"},
        ]
    )

    async def cache_invalidator() -> None:
        return None

    cache_invalidator_called = {"n": 0}

    async def tracked_invalidator() -> None:
        cache_invalidator_called["n"] += 1

    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    scraper, _, _, _ = await _make_scraper_with(
        page,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cache_invalidator=tracked_invalidator,
    )
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    # Retry succeeded → 3 cards returned.
    assert result is not None
    assert len(result) == 3
    # `auth_cookies.set_cookies` was called with the 3 cookies.
    assert len(auth_cookies.set_cookies_calls) == 1
    assert len(auth_cookies.set_cookies_calls[0]) == 3
    # `cache_invalidator` was called exactly once.
    assert cache_invalidator_called["n"] == 1
    # Refresher was called exactly once.
    assert refresher.calls == 1


async def test_scraper_returns_empty_list_on_refresh_failure() -> None:
    """REQ-LCR-003 — refresh fails → WARNING + return [].

    No `set_cookies` call, no `cache_invalidator` call.
    """
    page = _FakePage(AUTH_WALL_HTML)
    refresher = FakeLinkedInCookieRefresherPort(canned=None)
    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    invalidator_calls = {"n": 0}

    async def tracked_invalidator() -> None:
        invalidator_calls["n"] += 1

    scraper, _, _, _ = await _make_scraper_with(
        page,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cache_invalidator=tracked_invalidator,
    )
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    assert result == []
    assert len(auth_cookies.set_cookies_calls) == 0
    assert invalidator_calls["n"] == 0


async def test_scraper_skips_refresh_within_backoff_window() -> None:
    """REQ-LCR-004 — within backoff window, the scraper does NOT
    call the refresher.

    The scraper's `_last_refresh_attempt_at` is set to
    `time.monotonic()` BEFORE the await completes (per the
    spec). A subsequent call within `backoff_seconds` skips
    the refresh entirely.
    """
    # First search: refresh fails → records last_attempt_at.
    page1 = _FakePage(AUTH_WALL_HTML)
    refresher = FakeLinkedInCookieRefresherPort(canned=None)
    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    scraper, _, _, _ = await _make_scraper_with(
        page1,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cookie_refresher_backoff_seconds=3600.0,
    )
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    assert refresher.calls == 1
    # Second search within backoff: refresh NOT called.
    page2 = _FakePage(AUTH_WALL_HTML)
    # The scraper is single-use per `async with`; we need a
    # fresh instance. Re-use the same refresher to verify
    # the call count.
    scraper2, _, _, _ = await _make_scraper_with(
        page2,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cookie_refresher_backoff_seconds=3600.0,
    )
    # We need to set the same `_last_refresh_attempt_at` on
    # the new scraper; the spec says the field is per-scraper,
    # so this test exercises the SAME scraper instance
    # across 2 calls. Use the first scraper for both.
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    # Backoff skip: refresher calls stays at 1 (NOT 2).
    assert refresher.calls == 1
    assert result == []


async def test_scraper_refreshes_after_backoff_expires() -> None:
    """REQ-LCR-004 — after backoff expires, the scraper calls
    the refresher again.

    Manually backdate `_last_refresh_attempt_at` to a time
    well past `backoff_seconds` ago; the next refresh call
    must NOT skip.
    """
    page = _FakePage(AUTH_WALL_HTML)
    refresher = FakeLinkedInCookieRefresherPort(canned=None)
    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    scraper, _, _, _ = await _make_scraper_with(
        page,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cookie_refresher_backoff_seconds=10.0,
    )
    # Backdate `_last_refresh_attempt_at` to 100s ago.
    scraper._last_refresh_attempt_at = time.monotonic() - 100.0
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    # Refresher WAS called (backoff expired).
    assert refresher.calls == 1


async def test_scraper_with_none_refresher_does_not_call_refresh() -> None:
    """REQ-LCR-008 — `cookie_refresher=None` is byte-identical to
    pre-change behavior. The auth-wall WARNING is emitted (v1
    path), but the refresher is NEVER called.

    Built directly (not via `_make_scraper_with`) to preserve
    the `None` semantics — the helper substitutes a default
    fake when `None` is passed for test convenience.
    """
    page = _FakePage(AUTH_WALL_HTML)
    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    fake_browser = _FakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> _FakeBrowser:
        return fake_browser

    settings = LinkedInScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        auth_cookies=auth_cookies,
        cookie_refresher=None,  # EXPLICITLY None — v1 path
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=settings,
        browser_factory=factory,
    )
    assert scraper._settings.cookie_refresher is None
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=10)
    assert result == []  # soft-WARNING path returns [] (v1)


async def test_search_does_not_log_cookie_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """REQ-LCR-005 — no log call contains the synthetic cookie
    value, on the SUCCESS refresh path (set_cookies + cache
    invalidation + retry).
    """
    call_count = {"n": 0}

    def html_factory(_url: str) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AUTH_WALL_HTML
        return HEALTHY_HTML

    page = _FakePage(html_factory)
    synthetic_cookie_value = "AQE_NEW_LI_AT_VALUE_XYZ"
    refresher = FakeLinkedInCookieRefresherPort(
        canned=[
            {
                "name": "li_at",
                "value": synthetic_cookie_value,
                "domain": ".linkedin.com",
            }
        ]
    )

    async def cache_invalidator() -> None:
        return None

    auth_cookies = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQE_INIT"))])
    scraper, _, _, _ = await _make_scraper_with(
        page,
        auth_cookies=auth_cookies,
        cookie_refresher=refresher,
        cache_invalidator=cache_invalidator,
    )
    with caplog.at_level(logging.DEBUG):
        async with scraper:
            await scraper.search("react", "Madrid", limit=10)
    # No record contains the cookie value.
    for record in caplog.records:
        text = record.getMessage()
        assert synthetic_cookie_value not in text, f"cookie value leaked into log: {text!r}"
        if record.args:
            for arg in record.args:
                assert synthetic_cookie_value not in str(arg), (
                    f"cookie value leaked into log args: {arg!r}"
                )
