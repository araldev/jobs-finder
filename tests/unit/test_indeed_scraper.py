"""Unit tests for `IndeedPlaywrightScraper`.

Spec: REQ-I-007, REQ-I-016.
The scraper drives a real Chromium in production. Tests use minimal fake
`Page` / `Context` / `Browser` objects so the suite never launches a
browser and never contacts Indeed.

The 5 scenarios required by the design's §6 and the T-006 prompt are:
    1. Happy path returns list of `Job` (one per card, fields populated)
    2. Blocked page (Cloudflare challenge) -> `IndeedBlockedError`
    3. Missing cards on first page (empty content) -> `IndeedParseError`
    4. `wait_for_selector` timeout -> `IndeedTimeoutError`
    5. Pagination follows `start=10` when `limit > first_page_size`
       (e.g. limit=25, first page yields 15 -> expect 2 page requests,
       second page yields the remaining 10).

The test fakes mirror the LinkedIn scraper test fakes so the patterns
are aligned across the two sources.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from jobs_finder.infrastructure.indeed.exceptions import (
    IndeedBlockedError,
    IndeedParseError,
    IndeedTimeoutError,
)
from jobs_finder.infrastructure.indeed.scraper import (
    IndeedPlaywrightScraper,
    IndeedScraperSettings,
)
from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle
from tests.fixtures.indeed_search import BLOCKED_PAGE_HTML, SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePage:
    """Minimal Playwright `Page` stub for scraper tests.

    `html` may be:
      - a `str` returned for every navigation (default for static
        content), or
      - a callable `(url) -> str` that lets the test return different
        content for different pagination pages.
    """

    def __init__(
        self,
        html: str | Callable[[str], str] = "",
        *,
        selector_timeout: bool = False,
    ) -> None:
        self._html = html
        self.selector_timeout = selector_timeout
        self.goto_calls: list[str] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.wait_calls.append((selector, timeout))
        if self.selector_timeout:
            raise PlaywrightTimeoutError(f"selector {selector!r} not found")

    async def content(self) -> str:
        if callable(self._html):
            return self._html(self.goto_calls[-1])
        return self._html

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    """Minimal Playwright `BrowserContext` stub."""

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """Minimal Playwright `Browser` stub."""

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False
        self.new_context_calls: list[dict[str, Any]] = []

    async def new_context(self, **kwargs: Any) -> FakeContext:
        self.new_context_calls.append(kwargs)
        return FakeContext(self.page)

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    domain: str = "es.indeed.com",
    timeout_ms: int = 10_000,
    max_pages: int = 10,
) -> IndeedScraperSettings:
    return IndeedScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=timeout_ms,
        domain=domain,
        max_pages=max_pages,
    )


async def _make_scraper_with(
    page: FakePage,
    *,
    domain: str = "es.indeed.com",
    timeout_ms: int = 10_000,
    max_pages: int = 10,
) -> tuple[IndeedPlaywrightScraper, FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent.

    The throttle is configured with `min_interval_seconds=0.0` so the
    tests don't actually sleep between calls.
    """
    fake_browser = FakeBrowser(page)
    throttle = IndeedAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = IndeedPlaywrightScraper(
        throttle=throttle,
        settings=_settings(domain=domain, timeout_ms=timeout_ms, max_pages=max_pages),
        browser_factory=factory,
    )
    return scraper, fake_browser


def _build_n_cards_html(n: int, *, jk_prefix: int) -> str:
    """Build a search-results page with `n` cards starting at `<jk_prefix>`.

    Used to construct a custom second page in the pagination test.
    """
    cards: list[str] = []
    for i in range(n):
        jk = str(jk_prefix + i)
        cards.append(
            f"""
      <div class="job_seen_beacon" data-jk="{jk}">
        <h2 class="jobTitle">
          <a href="/viewjob?jk={jk}" title="Title {jk}">Title {jk}</a>
        </h2>
        <span class="companyName">Co {jk}</span>
        <div class="companyLocation">City {jk}</div>
        <span class="date">Hoy</span>
      </div>"""
        )
    return "<html><body><main><ul>" + "".join(cards) + "</ul></main></body></html>"


# ---------------------------------------------------------------------------
# Navigation target (REQ-I-007)
# ---------------------------------------------------------------------------


async def test_search_navigates_to_indeed_jobs_search() -> None:
    """The URL contains the quoted keywords and location on the right host."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=10` keeps the test on a single page so the assertion
        # isolates the URL contract from the pagination contract.
        await scraper.search(keywords="python", location="madrid", limit=10)
    assert page.goto_calls == ["https://es.indeed.com/jobs?q=python&l=madrid&start=0"]


async def test_search_waits_for_results_selector_with_configured_timeout() -> None:
    """`wait_for_selector` is called with the configured `timeout_ms`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, timeout_ms=12_345)
    async with scraper:
        # `limit=10` keeps the test on a single page so the assertion
        # isolates the wait-for-selector contract from pagination.
        await scraper.search("python", "madrid", limit=10)
    assert page.wait_calls == [("div.job_seen_beacon", 12_345)]


async def test_search_creates_browser_context_with_user_agent() -> None:
    """`new_context` is called with the configured user-agent (no viewport)."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=10)
    assert len(fake_browser.new_context_calls) == 1
    assert fake_browser.new_context_calls[0]["user_agent"] == "test-agent/1.0"


# ---------------------------------------------------------------------------
# Happy path (REQ-I-007)
# ---------------------------------------------------------------------------


async def test_search_returns_one_job_per_card() -> None:
    """15 cards in the page yield 15 `Job` objects with the right fields."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=15` keeps the test on a single page so the assertion
        # isolates field-mapping from pagination.
        jobs = await scraper.search("python", "madrid", limit=15)
    assert len(jobs) == 15
    # First card (id 100000001) fields are populated.
    first = jobs[0]
    assert first.id == "100000001"
    assert first.title == "Senior Python Developer"
    assert first.company == "Indeed Co 1"
    assert first.location == "Madrid, Spain"
    assert first.url == "https://es.indeed.com/viewjob?jk=100000001"
    # `posted_at` is tz-aware UTC (parser returns tz-aware datetime).
    assert first.posted_at.tzinfo is not None


async def test_search_uses_configured_domain_in_viewjob_url() -> None:
    """Each `Job.url` is `https://{domain}/viewjob?jk={id}` for the configured domain."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, domain="fr.indeed.com")
    async with scraper:
        jobs = await scraper.search("python", "paris", limit=1)
    assert jobs[0].url == "https://fr.indeed.com/viewjob?jk=100000001"


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------


async def test_search_respects_limit() -> None:
    """A `limit=5` over 15 cards returns the first 5 jobs only."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=5)
    assert len(jobs) == 5
    assert [j.id for j in jobs] == [f"10000000{i}" for i in range(1, 6)]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


async def test_search_raises_blocked_on_cloudflare_challenge() -> None:
    """A `BLOCKED_PAGE_HTML` response raises `IndeedBlockedError`."""
    page = FakePage(BLOCKED_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(IndeedBlockedError):
            await scraper.search("python", "madrid")


async def test_search_raises_parse_error_when_first_page_has_no_cards() -> None:
    """A first page with no `div.job_seen_beacon` cards raises `IndeedParseError`."""
    empty_page = "<html><body><main><h1>No results</h1></main></body></html>"
    page = FakePage(empty_page)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(IndeedParseError, match="zero_cards_on_first_page"):
            await scraper.search("python", "madrid")


async def test_search_raises_timeout_when_results_never_appear() -> None:
    """A `PlaywrightTimeoutError` from `wait_for_selector` becomes `IndeedTimeoutError`."""
    page = FakePage(SEARCH_PAGE_HTML, selector_timeout=True)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(IndeedTimeoutError, match="timeout"):
            await scraper.search("python", "madrid")


# ---------------------------------------------------------------------------
# Pagination (REQ-I-007)
# ---------------------------------------------------------------------------


async def test_search_paginates_with_start_increment_when_limit_exceeds_first_page() -> None:
    """When `limit > first_page_size`, page 2 is fetched with `start=10`."""
    second_page = _build_n_cards_html(10, jk_prefix=200000001)
    page = FakePage(html=lambda url: SEARCH_PAGE_HTML if "start=0" in url else second_page)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=25)

    assert len(jobs) == 25
    assert page.goto_calls == [
        "https://es.indeed.com/jobs?q=python&l=madrid&start=0",
        "https://es.indeed.com/jobs?q=python&l=madrid&start=10",
    ]
    # First 15 are from the first page; last 10 are from the second page.
    assert jobs[0].id == "100000001"
    assert jobs[14].id == "100000015"
    assert jobs[15].id == "200000001"
    assert jobs[24].id == "200000010"


async def test_search_does_not_paginate_when_first_page_satisfies_limit() -> None:
    """When `limit <= first_page_size`, only one page is fetched."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=3)
    assert page.goto_calls == ["https://es.indeed.com/jobs?q=python&l=madrid&start=0"]


async def test_search_stops_at_max_pages() -> None:
    """The pagination loop never exceeds `settings.indeed_max_pages`.

    Every page returns the same 15-card HTML, so the loop would otherwise
    run forever. With `max_pages=2` and `limit=200`, we get exactly 2
    page requests and 30 jobs (15 per page, capped at limit=200).
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, max_pages=2)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=200)

    assert len(page.goto_calls) == 2
    assert page.goto_calls == [
        "https://es.indeed.com/jobs?q=python&l=madrid&start=0",
        "https://es.indeed.com/jobs?q=python&l=madrid&start=10",
    ]
    assert len(jobs) == 30


# ---------------------------------------------------------------------------
# Async context manager shape
# ---------------------------------------------------------------------------


async def test_scraper_is_an_async_context_manager() -> None:
    """`IndeedPlaywrightScraper` is an async context manager.

    The injected browser must NOT be closed on `__aexit__` (we don't
    own it). This is the same invariant the LinkedIn test pins.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        pass
    assert not fake_browser.closed


# ---------------------------------------------------------------------------
# Stealth integration (REQ-S-001, REQ-S-004)
# ---------------------------------------------------------------------------


class TestStealthIntegration:
    """`playwright-stealth`'s `Stealth().apply_stealth_async` is wired into
    `search()` so the live scraper can bypass Cloudflare's bot detection.

    REQ-S-001: stealth is opt-in via the `stealth=` constructor parameter.
    REQ-S-004: a unit test proves the wiring WITHOUT launching Chromium
    (the `browser_factory` injection pattern isolates the integration).
    """

    async def test_stealth_is_applied_when_provided(self) -> None:
        """`stealth.apply_stealth_async` is awaited once with the created context."""
        page = FakePage(SEARCH_PAGE_HTML)
        scraper, _ = await _make_scraper_with(page)
        stealth = MagicMock()
        stealth.apply_stealth_async = AsyncMock()
        # The helper used by the existing tests does not expose a
        # `stealth=` kwarg. We assign `scraper._stealth` directly so
        # the test stays focused on the integration in `search()`.
        scraper._stealth = stealth
        async with scraper:
            await scraper.search("python", "madrid", limit=5)
        # Exactly one call, exactly one positional argument, the
        # context the scraper just created. The mock is `AsyncMock`
        # so `await_count` records the awaited invocations.
        assert stealth.apply_stealth_async.await_count == 1
        assert stealth.apply_stealth_async.await_args is not None
        args, _ = stealth.apply_stealth_async.await_args
        assert len(args) == 1
        # The single argument is the FakeContext the FakeBrowser
        # produced (a `FakeContext(page)` instance). Identity is the
        # simplest, most precise assertion.
        assert isinstance(args[0], FakeContext)

    async def test_stealth_is_not_applied_when_none(self) -> None:
        """No `apply_stealth_async` call when `stealth=None` (the default)."""
        page = FakePage(SEARCH_PAGE_HTML)
        scraper, _ = await _make_scraper_with(page)
        # `stealth` defaults to None; assert the attribute exists and
        # no stealth call happens during `search()`.
        assert scraper._stealth is None
        async with scraper:
            await scraper.search("python", "madrid", limit=5)
        # The test passes if `search()` returns without raising. The
        # RED state for this test is `AttributeError` on
        # `scraper._stealth` before the constructor parameter lands.
