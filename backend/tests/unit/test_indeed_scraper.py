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

# Type alias for the per-call selector-timeout hook used by `FakePage`.
# `True` means every `wait_for_selector` raises; a callable receives the
# most-recent `goto` URL and returns `True` if that page should time out.
SelectorTimeout = bool | Callable[[str], bool]

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
        selector_timeout: SelectorTimeout = False,
    ) -> None:
        self._html = html
        self.selector_timeout: SelectorTimeout = selector_timeout
        self.goto_calls: list[str] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait_for_selector(self, selector: str, *, timeout: int = 0, **kwargs: object) -> None:
        self.wait_calls.append((selector, timeout))
        if callable(self.selector_timeout):
            if self.selector_timeout(self.goto_calls[-1]):
                raise PlaywrightTimeoutError(f"selector {selector!r} not found")
        elif self.selector_timeout:
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
    inter_page_delay_seconds: float = 0.0,
) -> IndeedScraperSettings:
    return IndeedScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=timeout_ms,
        domain=domain,
        max_pages=max_pages,
        inter_page_delay_seconds=inter_page_delay_seconds,
    )


async def _make_scraper_with(
    page: FakePage,
    *,
    domain: str = "es.indeed.com",
    timeout_ms: int = 10_000,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 0.0,
) -> tuple[IndeedPlaywrightScraper, FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent.

    The throttle is configured with `min_interval_seconds=0.0` so the
    tests don't actually sleep between calls. The inter-page delay
    defaults to `0.0` for the same reason; tests that exercise the
    pacing behavior pass a non-zero value and monkeypatch
    `asyncio.sleep`.
    """
    fake_browser = FakeBrowser(page)
    throttle = IndeedAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = IndeedPlaywrightScraper(
        throttle=throttle,
        settings=_settings(
            domain=domain,
            timeout_ms=timeout_ms,
            max_pages=max_pages,
            inter_page_delay_seconds=inter_page_delay_seconds,
        ),
        browser_factory=factory,
    )
    return scraper, fake_browser


def _build_n_cards_html(n: int, *, jk_prefix: int) -> str:
    """Build a search-results page with `n` cards starting at `<jk_prefix>`.

    Used to construct a custom second page in the pagination test.
    The card shape mirrors the real DOM observed 2026-06-02 against
    real es.indeed.com HTML: `data-jk` is on the title anchor
    `<a class="jcs-JobTitle">`; company uses
    `[data-testid="company-name"]`; location uses
    `[data-testid="text-location"]`. The v1 placeholder shape
    (`<h2>`, `span.companyName`, `div.companyLocation`) is no longer
    what the parsers expect.
    """
    cards: list[str] = []
    for i in range(n):
        jk = str(jk_prefix + i)
        cards.append(
            f"""
      <div class="job_seen_beacon">
        <h3 class="jobTitle">
          <a class="jcs-JobTitle" data-jk="{jk}">Title {jk}</a>
        </h3>
        <span data-testid="company-name">Co {jk}</span>
        <div data-testid="text-location">City {jk}</div>
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
    """16 cards in the page (real es.indeed.com capture) yield 16 `Job` objects.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    renders 16 cards on the first page of the Python/Madrid SERP.
    The first card's fields are pinned to the real capture so the
    field-mapping contract is verified end-to-end:
        id     = "dd6cc0f5b0f0cfc9" (16-char hex, not 9-digit decimal)
        title  = "Desarrollador Python Junior (Madrid) | Sigma AI"
        company = "Sigma Group" (from `[data-testid="company-name"]`)
        location = "Madrid, Madrid provincia" (from
                   `[data-testid="text-location"]`)
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=16` keeps the test on a single page (the real
        # capture has exactly 16 cards) so the assertion isolates
        # field-mapping from pagination.
        jobs = await scraper.search("python", "madrid", limit=16)
    assert len(jobs) == 16
    # First card fields are populated from the real capture.
    first = jobs[0]
    assert first.id == "dd6cc0f5b0f0cfc9"
    assert first.title == "Desarrollador Python Junior (Madrid) | Sigma AI"
    assert first.company == "Sigma Group"
    assert first.location == "Madrid, Madrid provincia"
    assert first.url == "https://es.indeed.com/viewjob?jk=dd6cc0f5b0f0cfc9"
    # `posted_at` is tz-aware UTC (the real DOM has no inline date
    # so the scraper falls back to `datetime.now(UTC)`).
    assert first.posted_at.tzinfo is not None


async def test_search_populates_description_from_below_job_snippet() -> None:
    """Indeed `_parse_cards` populates `Job.description` from `data-testid="belowJobSnippet"`.

    Spec: REQ-PARSER-INDEED-001 + T-005 wiring. The real Indeed
    SERP (observed 2026-06-02) renders the description in
    `<div data-testid="belowJobSnippet" class="...">` blocks
    inside each card. The wiring in `_parse_cards` MUST call
    `parse_indeed_description(card)` and pass the result to the
    `Job(...)` constructor. The test builds a custom HTML
    page with a single card carrying a known description and
    asserts the resulting `Job.description` matches.
    """
    html = """
    <html><body><main><ul>
      <div class="job_seen_beacon">
        <h3 class="jobTitle">
          <a class="jcs-JobTitle" data-jk="desc001">Title desc001</a>
        </h3>
        <span data-testid="company-name">Co desc001</span>
        <div data-testid="text-location">City desc001</div>
        <div data-testid="belowJobSnippet" class="css-1vlebyu eu4oa1w0">
          <ul style="list-style-type:circle;">
            <li>Estamos buscando a alguien con experiencia en Python</li>
            <li>Modalidad remota opcional</li>
          </ul>
        </div>
      </div>
    </ul></main></body></html>
    """
    page = FakePage(html)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=1)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.description is not None
    # The two `<li>` items joined with ` | `, per the parser contract.
    assert "Python" in job.description
    assert "remota opcional" in job.description
    assert " | " in job.description


async def test_search_uses_configured_domain_in_viewjob_url() -> None:
    """Each `Job.url` is `https://{domain}/viewjob?jk={id}` for the configured domain."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, domain="fr.indeed.com")
    async with scraper:
        jobs = await scraper.search("python", "paris", limit=1)
    assert jobs[0].url == "https://fr.indeed.com/viewjob?jk=dd6cc0f5b0f0cfc9"


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------


async def test_search_respects_limit() -> None:
    """A `limit=5` over 16 cards returns the first 5 jobs only.

    The real DOM (observed 2026-06-02) renders 16 cards per page;
    the v1 placeholder had 15. The first 5 ids are read from the
    real capture.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=5)
    assert len(jobs) == 5
    # First 5 ids from the real capture (in document order).
    assert [j.id for j in jobs] == [
        "dd6cc0f5b0f0cfc9",
        "7bc5f5f2d189a262",
        "b99a18679f8055e5",
        "789abcdef0123456",
        "c725861acc9df584",
    ]


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
    """When `limit > first_page_size`, page 2 is fetched with `start=10`.

    The real DOM (observed 2026-06-02) renders 16 cards on the first
    page. With `limit=26`, the scraper reads the 16 real cards on
    page 1 and 10 synthetic cards on page 2 (returned by the page
    stub's lambda).
    """
    second_page = _build_n_cards_html(10, jk_prefix=200000001)
    page = FakePage(html=lambda url: SEARCH_PAGE_HTML if "start=0" in url else second_page)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=26)

    assert len(jobs) == 26
    assert page.goto_calls == [
        "https://es.indeed.com/jobs?q=python&l=madrid&start=0",
        "https://es.indeed.com/jobs?q=python&l=madrid&start=10",
    ]
    # First 16 are from the real first page; last 10 are from the
    # synthetic second page.
    assert jobs[0].id == "dd6cc0f5b0f0cfc9"
    assert jobs[15].id == "148d08d0a96ff485"  # last card on first page
    assert jobs[16].id == "200000001"  # first card on second page
    assert jobs[25].id == "200000010"  # last card on second page


async def test_search_does_not_paginate_when_first_page_satisfies_limit() -> None:
    """When `limit <= first_page_size`, only one page is fetched.

    The real DOM has 16 cards on the first page; `limit=3` is
    well below that, so only one page is requested.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=3)
    assert page.goto_calls == ["https://es.indeed.com/jobs?q=python&l=madrid&start=0"]


async def test_search_sleeps_inter_page_delay_between_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`asyncio.sleep(inter_page_delay_seconds)` is called between pages.

    Follow-up to `fd51ea1` (the page-2 timeout bug). The first page is
    never delayed; the second and subsequent pages are each preceded
    by an `asyncio.sleep` of the configured duration. This reduces
    Cloudflare re-challenge probability when paginating.

    The test monkeypatches `asyncio.sleep` so the assertions run
    without any real wall-clock delay. A 3-page search with the
    default 1.5-second delay → exactly 2 inter-page sleeps, each
    called with `(1.5,)`.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    second_page = _build_n_cards_html(10, jk_prefix=200000001)
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "start=0" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=3,
        inter_page_delay_seconds=1.5,
    )
    async with scraper:
        await scraper.search("python", "madrid", limit=30)

    # 3 page requests → 2 inter-page sleeps (page 0 is never delayed).
    assert sleep_mock.await_count == 2
    # Both sleeps were called with the configured delay as a positional arg.
    assert sleep_mock.await_args_list[0].args == (1.5,)
    assert sleep_mock.await_args_list[1].args == (1.5,)


async def test_search_does_not_sleep_when_delay_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`inter_page_delay_seconds=0.0` disables the inter-page sleep entirely."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    second_page = _build_n_cards_html(10, jk_prefix=200000001)
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "start=0" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=3,
        inter_page_delay_seconds=0.0,
    )
    async with scraper:
        await scraper.search("python", "madrid", limit=30)

    # The throttle is also `min_interval_seconds=0.0`, so no sleeps
    # happen at all when the inter-page delay is disabled.
    assert sleep_mock.await_count == 0


async def test_search_does_not_sleep_after_final_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The inter-page sleep fires BEFORE the next page, not AFTER the last one.

    A 2-page search with `inter_page_delay_seconds=1.0` → exactly
    1 sleep (before page 1), NOT 2.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    page = FakePage(SEARCH_PAGE_HTML)  # every page returns 16 cards
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=2,
        inter_page_delay_seconds=1.0,
    )
    async with scraper:
        # `limit=20` forces 2 page requests (page 0 yields 16 < 20,
        # so the loop continues; page 1 is the LAST one because the
        # total hits 32 >= 20). The assertion below proves the sleep
        # is BETWEEN pages, not AFTER the last one — 2 page requests
        # yield exactly 1 sleep, not 2.
        await scraper.search("python", "madrid", limit=20)

    # 2 page requests → 1 inter-page sleep (before the second page).
    assert sleep_mock.await_count == 1
    assert sleep_mock.await_args_list[0].args == (1.0,)


async def test_search_stops_at_max_pages() -> None:
    """The pagination loop never exceeds `settings.indeed_max_pages`.

    Every page returns the same 16-card HTML (the real capture),
    so the loop would otherwise run forever. With `max_pages=2`
    and `limit=200`, we get exactly 2 page requests and 32 jobs
    (16 per page, capped at limit=200).
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
    assert len(jobs) == 32


async def test_search_returns_first_page_results_when_subsequent_page_times_out() -> None:
    """A timeout on page > 0 (end of results or anti-bot re-challenge) is graceful.

    REQ-I-007: The scraper MUST return what it has if a subsequent
    pagination page fails. Only a failure on the FIRST page is a real
    error (raise `IndeedTimeoutError`); pages > 0 are treated as
    "no more results" and the loop breaks gracefully. This matches the
    real Indeed behavior: the SERP for `python / madrid` has 16 cards
    total, so a second page either does not exist or is an anti-bot
    re-challenge — both of which should not blow up the search.
    """
    # First page returns the real 16-card capture; second page's
    # `wait_for_selector` raises a PlaywrightTimeoutError.
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "start=0" in url else "",
        selector_timeout=lambda url: "start=10" in url,
    )
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=20)
    # 16 jobs from page 1; loop broke on page 2 timeout (no raise).
    assert len(jobs) == 16
    assert jobs[0].id == "dd6cc0f5b0f0cfc9"
    # Exactly 2 page requests: page 1 succeeded, page 2 timed out.
    assert page.goto_calls == [
        "https://es.indeed.com/jobs?q=python&l=madrid&start=0",
        "https://es.indeed.com/jobs?q=python&l=madrid&start=10",
    ]


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
