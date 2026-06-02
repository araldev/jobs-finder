"""Unit tests for `InfoJobsPlaywrightScraper`.

Spec: REQ-J-001, REQ-J-002, REQ-J-003, REQ-J-006.
The scraper drives a real Chromium in production. Tests use minimal
fake `Page` / `Context` / `Browser` objects so the suite never
launches a browser and never contacts InfoJobs.

The scenarios required by the T-006 prompt are:
    1. Happy path returns list of `Job` (15+ cards on the placeholder
       fixture).
    2. Blocked page (Distil/Geetest challenge) -> `InfoJobsBlockedError`.
    3. Missing cards on first page (empty content) ->
       `InfoJobsParseError` (only on the first page).
    4. `wait_for_selector` timeout on page 0 -> `InfoJobsTimeoutError`.
    5. Pagination follows `page=2` when `limit > first_page_size`.
    6. Page 2 timeout returns first page's results (REQ-J-006).
    7. Inter-page pacing: monkeypatch `asyncio.sleep`, assert it's
       called with the configured delay between pages.
    8. Stealth integration: when `stealth=MagicMock()` is provided,
       `apply_stealth_async` is called once on the context; when
       `stealth=None`, not called (REQ-J-002).
    9. URL uses 1-indexed page param (`page=1` for first page,
       `page=2` for second).
    10. Inter-page delay of 0.0 skips the sleep entirely (no
        needless event-loop yield).

The test fakes mirror the Indeed `test_indeed_scraper.py` fakes so
the patterns are aligned across the two sources. Each test
constructs a `FakeBrowser` and wires it into the scraper via
`browser_factory=` so the suite never launches Chromium.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from jobs_finder.infrastructure.infojobs.exceptions import (
    InfoJobsBlockedError,
    InfoJobsParseError,
    InfoJobsTimeoutError,
)
from jobs_finder.infrastructure.infojobs.scraper import (
    InfoJobsPlaywrightScraper,
    InfoJobsScraperSettings,
)
from jobs_finder.infrastructure.infojobs.throttle import InfoJobsAsyncThrottle
from tests.fixtures.infojobs_search import BLOCKED_PAGE_HTML, SEARCH_PAGE_HTML

# Type alias for the per-call selector-timeout hook used by `FakePage`.
# Mirrors the Indeed test fake. `True` means every `wait_for_selector`
# raises; a callable receives the most-recent `goto` URL and returns
# `True` if that page should time out.
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

    async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
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
    domain: str = "www.infojobs.net",
    timeout_ms: int = 10_000,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 0.0,
) -> InfoJobsScraperSettings:
    return InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=timeout_ms,
        domain=domain,
        max_pages=max_pages,
        inter_page_delay_seconds=inter_page_delay_seconds,
    )


async def _make_scraper_with(
    page: FakePage,
    *,
    domain: str = "www.infojobs.net",
    timeout_ms: int = 10_000,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 0.0,
    stealth: Any = None,
) -> tuple[InfoJobsPlaywrightScraper, FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent.

    The throttle is configured with `min_interval_seconds=0.0` so the
    tests don't actually sleep between calls. The inter-page delay
    defaults to `0.0` for the same reason; tests that exercise the
    pacing behavior pass a non-zero value and monkeypatch
    `asyncio.sleep`.
    """
    fake_browser = FakeBrowser(page)
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = InfoJobsPlaywrightScraper(
        throttle=throttle,
        settings=_settings(
            domain=domain,
            timeout_ms=timeout_ms,
            max_pages=max_pages,
            inter_page_delay_seconds=inter_page_delay_seconds,
        ),
        browser_factory=factory,
        stealth=stealth,
    )
    return scraper, fake_browser


def _build_n_cards_html(n: int, *, id_prefix: str) -> str:
    """Build a search-results page with `n` cards starting at `<id_prefix>000`.

    Used to construct a custom second page in the pagination test. The
    card shape mirrors the placeholder fixture (T-004): the id is in
    the title anchor's `href` as `/ofertas-trabajo/oferta-<id>`.
    """
    cards: list[str] = []
    for i in range(1, n + 1):
        job_id = f"{id_prefix}{i:03d}"
        cards.append(
            f"""
      <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
        <div class="ij-OfferCardContent">
          <div class="ij-OfferCardContent-description">
            <div class="ij-OfferCardContent-description-head">
              <a class="ij-OfferCardContent-description-title-link"
                 href="/ofertas-trabajo/oferta-{job_id}">
                <h2 class="ij-OfferCardContent-description-title">Title {job_id}</h2>
              </a>
            </div>
            <div class="ij-OfferCardContent-description-subtitle">Co {job_id}</div>
            <ul class="ij-OfferCardContent-description-list">
              <li class="ij-OfferCardContent-description-list-item">City {job_id}</li>
            </ul>
            <div class="ij-OfferCardContent-date">Hoy</div>
          </div>
        </div>
      </li>"""
        )
    return "<html><body><main><ul>" + "".join(cards) + "</ul></main></body></html>"


# ---------------------------------------------------------------------------
# Navigation target (REQ-J-001)
# ---------------------------------------------------------------------------


async def test_search_navigates_to_infojobs_ofertas_trabajo() -> None:
    """The URL is `https://{domain}/ofertas-trabajo?q={kw}&l={loc}&page=1` (1-indexed)."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=10` keeps the test on a single page so the assertion
        # isolates the URL contract from the pagination contract.
        await scraper.search(keywords="python", location="madrid", limit=10)
    assert page.goto_calls == ["https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=1"]


async def test_search_uses_one_indexed_page_param_on_first_page() -> None:
    """The first page uses `page=1` (NOT `page=0`); pagination is 1-indexed."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=10)
    assert "page=1" in page.goto_calls[0]
    assert "page=0" not in page.goto_calls[0]


async def test_search_waits_for_results_selector_with_configured_timeout() -> None:
    """`wait_for_selector` is called with the configured `timeout_ms`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, timeout_ms=12_345)
    async with scraper:
        await scraper.search("python", "madrid", limit=10)
    assert page.wait_calls == [(".ij-OfferList-offerCardItem", 12_345)]


async def test_search_creates_browser_context_with_user_agent() -> None:
    """`new_context` is called with the configured user-agent."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=10)
    assert len(fake_browser.new_context_calls) == 1
    assert fake_browser.new_context_calls[0]["user_agent"] == "test-agent/1.0"


# ---------------------------------------------------------------------------
# Happy path (REQ-J-001)
# ---------------------------------------------------------------------------


async def test_search_returns_one_job_per_card_on_placeholder_fixture() -> None:
    """The placeholder fixture has 15+ cards (per the parser test contract) and
    each yields a `Job` with the 6 spec fields populated.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=15` matches the placeholder's first-page size so the
        # test stays on a single page and the assertion isolates
        # field-mapping from pagination. The default `page.content()`
        # returns `SEARCH_PAGE_HTML` for every navigation, so a
        # higher `limit` would paginate and double-count.
        jobs = await scraper.search("python", "madrid", limit=15)
    assert len(jobs) == 15
    # First card fields are populated from the placeholder fixture.
    first = jobs[0]
    assert first.id == "abc123001"
    assert first.title == "Senior Python Developer"
    assert first.company == "InfoJobs Co 1"
    assert first.location == "Madrid, Spain"
    assert first.url == "https://www.infojobs.net/ofertas-trabajo/oferta-abc123001"
    # `posted_at` is tz-aware UTC (the placeholder uses relative
    # date strings which the parser maps to UTC `datetime`s).
    assert first.posted_at.tzinfo is not None


async def test_search_uses_configured_domain_in_oferta_url() -> None:
    """Each `Job.url` is `https://{domain}/ofertas-trabajo/oferta-{id}`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, domain="br.infojobs.net")
    async with scraper:
        jobs = await scraper.search("python", "sao-paulo", limit=1)
    assert jobs[0].url == "https://br.infojobs.net/ofertas-trabajo/oferta-abc123001"


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
    # First 5 ids from the placeholder fixture (in document order).
    assert [j.id for j in jobs] == [
        "abc123001",
        "abc123002",
        "abc123003",
        "abc123004",
        "abc123005",
    ]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


async def test_search_raises_blocked_on_distil_or_geetest_challenge() -> None:
    """A `BLOCKED_PAGE_HTML` response raises `InfoJobsBlockedError`."""
    page = FakePage(BLOCKED_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(InfoJobsBlockedError):
            await scraper.search("python", "madrid")


async def test_search_raises_parse_error_when_first_page_has_no_cards() -> None:
    """A first page with no `li.ij-OfferList-offerCardItem` cards raises `InfoJobsParseError`."""
    empty_page = "<html><body><main><h1>No results</h1></main></body></html>"
    page = FakePage(empty_page)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(InfoJobsParseError, match="zero_cards_on_first_page"):
            await scraper.search("python", "madrid")


async def test_search_raises_timeout_when_results_never_appear() -> None:
    """A `PlaywrightTimeoutError` from `wait_for_selector` becomes `InfoJobsTimeoutError`."""
    page = FakePage(SEARCH_PAGE_HTML, selector_timeout=True)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(InfoJobsTimeoutError, match="timeout"):
            await scraper.search("python", "madrid")


# ---------------------------------------------------------------------------
# Pagination (REQ-J-006)
# ---------------------------------------------------------------------------


async def test_search_paginates_with_page_increment_when_limit_exceeds_first_page() -> None:
    """When `limit > first_page_size`, page 2 is fetched with `page=2`.

    The placeholder fixture has 15 cards on the first page. With
    `limit=20`, the scraper reads 15 cards on page 1 and 5 synthetic
    cards on page 2 (returned by the page stub's lambda).
    """
    second_page = _build_n_cards_html(5, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=20)

    assert len(jobs) == 20
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=2",
    ]
    # First 15 are from the placeholder first page; last 5 are from
    # the synthetic second page.
    assert jobs[0].id == "abc123001"
    assert jobs[14].id == "abc123015"  # last card on first page
    assert jobs[15].id == "xyz001"  # first card on second page
    assert jobs[19].id == "xyz005"  # last card on second page


async def test_search_does_not_paginate_when_first_page_satisfies_limit() -> None:
    """When `limit <= first_page_size`, only one page is fetched."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=3)
    assert page.goto_calls == ["https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=1"]


async def test_search_returns_first_page_results_when_subsequent_page_times_out() -> None:
    """A timeout on page > 0 (end of results or anti-bot re-challenge) is graceful.

    REQ-J-006: The scraper MUST return what it has if a subsequent
    pagination page fails. Only a failure on the FIRST page is a real
    error (raise `InfoJobsTimeoutError`); pages > 0 are treated as
    "no more results" and the loop breaks gracefully.
    """
    # First page returns the placeholder 15-card capture; second
    # page's `wait_for_selector` raises a PlaywrightTimeoutError.
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else "",
        selector_timeout=lambda url: "page=2" in url,
    )
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=20)
    # 15 jobs from page 1; loop broke on page 2 timeout (no raise).
    assert len(jobs) == 15
    assert jobs[0].id == "abc123001"
    # Exactly 2 page requests: page 1 succeeded, page 2 timed out.
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=2",
    ]


async def test_search_stops_at_max_pages() -> None:
    """The pagination loop never exceeds `settings.max_pages`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, max_pages=2)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=200)

    assert len(page.goto_calls) == 2
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid&page=2",
    ]
    assert len(jobs) == 30  # 15 per page, capped at limit=200


# ---------------------------------------------------------------------------
# Inter-page pacing (REQ-J-003)
# ---------------------------------------------------------------------------


async def test_search_sleeps_inter_page_delay_between_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`asyncio.sleep(inter_page_delay_seconds)` is called between pages.

    The first page is never delayed; the second and subsequent pages
    are each preceded by an `asyncio.sleep` of the configured
    duration. A 3-page search with the default 1.5-second delay →
    exactly 2 inter-page sleeps, each called with `(1.5,)`.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    second_page = _build_n_cards_html(15, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=3,
        inter_page_delay_seconds=1.5,
    )
    async with scraper:
        await scraper.search("python", "madrid", limit=50)

    # 3 page requests → 2 inter-page sleeps (page 0 is never delayed).
    assert sleep_mock.await_count == 2
    # Both sleeps were called with the configured delay as a positional arg.
    assert sleep_mock.await_args_list[0].args == (1.5,)
    assert sleep_mock.await_args_list[1].args == (1.5,)


async def test_search_does_not_sleep_when_delay_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`inter_page_delay_seconds=0.0` disables the inter-page sleep entirely.

    The check `> 0` short-circuits the call to `asyncio.sleep`, so the
    event loop is not yielded unnecessarily. Tests that don't care
    about pacing can leave the default `0.0` and still pass.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    second_page = _build_n_cards_html(15, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=3,
        inter_page_delay_seconds=0.0,
    )
    async with scraper:
        await scraper.search("python", "madrid", limit=50)

    # No sleep calls at all (the throttle is also `0.0` and the
    # inter-page delay is disabled).
    assert sleep_mock.await_count == 0


async def test_search_does_not_sleep_after_final_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The inter-page sleep fires BEFORE the next page, not AFTER the last one.

    A 2-page search with `inter_page_delay_seconds=1.0` → exactly
    1 sleep (before page 2), NOT 2.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    page = FakePage(SEARCH_PAGE_HTML)  # every page returns 15 cards
    scraper, _ = await _make_scraper_with(
        page,
        max_pages=2,
        inter_page_delay_seconds=1.0,
    )
    async with scraper:
        # `limit=20` forces 2 page requests (page 0 yields 15 < 20,
        # so the loop continues; page 1 is the LAST one because the
        # total hits 30 >= 20).
        await scraper.search("python", "madrid", limit=20)

    # 2 page requests → 1 inter-page sleep (before the second page).
    assert sleep_mock.await_count == 1
    assert sleep_mock.await_args_list[0].args == (1.0,)


# ---------------------------------------------------------------------------
# Async context manager shape
# ---------------------------------------------------------------------------


async def test_scraper_is_an_async_context_manager() -> None:
    """`InfoJobsPlaywrightScraper` is an async context manager.

    The injected browser must NOT be closed on `__aexit__` (we don't
    own it). This is the same invariant the Indeed test pins.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        pass
    assert not fake_browser.closed


# ---------------------------------------------------------------------------
# Stealth integration (REQ-J-002)
# ---------------------------------------------------------------------------


class TestStealthIntegration:
    """`playwright-stealth`'s `Stealth().apply_stealth_async` is wired into
    `search()` so the live scraper can bypass Distil/Geetest bot
    detection.

    REQ-J-002: stealth is opt-in via the `stealth=` constructor
    parameter. The InfoJobs v1 wires `Stealth()` in production
    (because Distil + Geetest is stricter than Cloudflare), but the
    scraper constructor accepts `stealth=None` for tests.
    """

    async def test_stealth_is_applied_when_provided(self) -> None:
        """`stealth.apply_stealth_async` is awaited once with the created context."""
        page = FakePage(SEARCH_PAGE_HTML)
        stealth = MagicMock()
        stealth.apply_stealth_async = AsyncMock()
        scraper, _ = await _make_scraper_with(page, stealth=stealth)
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
