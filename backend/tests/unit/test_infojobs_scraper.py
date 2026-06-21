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

import logging
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
from jobs_finder.infrastructure.location.hardcoded_resolver import (
    HardcodedLocationResolver,
)
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
    """Build a search-results page with `n` cards starting at `<id_prefix>001`.

    Used to construct a custom second page in the pagination test.
    The card shape mirrors the real InfoJobs SERP DOM (T-010 real
    capture, 2026-06-02): the id is in the media-link's `href` as
    `https://www.infojobs.net/{slug}/em-{id}` (Pattern A — the
    canonical pattern for non-promoted cards).
    """
    cards: list[str] = []
    for i in range(1, n + 1):
        job_id = f"{id_prefix}{i:03d}"
        cards.append(
            f"""
      <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
        <div class="sui-AtomCard-Wrapper">
          <div class="sui-AtomCard">
            <div class="ij-OfferCard">
              <div class="ij-OfferCardContent">
                <div class="ij-OfferCardContent-media">
                  <a class="ij-OfferCardContent-media-link" href="https://www.infojobs.net/acme/em-{job_id}">
                    <img alt="Acme" />
                  </a>
                </div>
                <div class="ij-OfferCardContent-description">
                  <div class="ij-OfferCardContent-description-head">
                    <h2 class="ij-OfferCardContent-description-title">Title {job_id}</h2>
                  </div>
                  <div class="ij-OfferCardContent-description-subtitle">
                    <a class="ij-OfferCardContent-description-subtitle-link">Co {job_id}</a>
                  </div>
                  <ul class="ij-OfferCardContent-description-list">
                    <li class="ij-OfferCardContent-description-list-item">City {job_id}</li>
                    <li class="ij-OfferCardContent-description-list-item">
                      <span data-testid="sincedate-tag">Hoy</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </li>"""
        )
    return "<html><body><main><ul>" + "".join(cards) + "</ul></main></body></html>"


# ---------------------------------------------------------------------------
# Navigation target (REQ-J-001)
# ---------------------------------------------------------------------------


async def test_search_navigates_to_infojobs_ofertas_trabajo() -> None:
    """The URL is `https://{domain}/ofertas-trabajo?keyword={kw}&l={loc}&page=1` (1-indexed)."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=10` keeps the test on a single page so the assertion
        # isolates the URL contract from the pagination contract.
        await scraper.search(keywords="python", location="madrid", limit=5)
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1"
    ]


async def test_search_uses_one_indexed_page_param_on_first_page() -> None:
    """The first page uses `page=1` (NOT `page=0`); pagination is 1-indexed."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=5)
    assert "page=1" in page.goto_calls[0]
    assert "page=0" not in page.goto_calls[0]


async def test_search_waits_for_results_selector_with_configured_timeout() -> None:
    """`wait_for_selector` is called with the configured `timeout_ms`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, timeout_ms=12_345)
    async with scraper:
        await scraper.search("python", "madrid", limit=5)
    assert page.wait_calls == [
        (
            ".ij-OfferList-offerCardItem:has(h2.ij-OfferCardContent-description-title)",
            12_345,
        )
    ]


async def test_search_creates_browser_context_with_user_agent() -> None:
    """`new_context` is called with the configured user-agent."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=5)
    assert len(fake_browser.new_context_calls) == 1
    assert fake_browser.new_context_calls[0]["user_agent"] == "test-agent/1.0"


# ---------------------------------------------------------------------------
# Happy path (REQ-J-001)
# ---------------------------------------------------------------------------


async def test_search_returns_one_job_per_card_on_placeholder_fixture() -> None:
    """The T-010 real-capture fixture has 5 real offer cards and each
    yields a `Job` with the 6 spec fields populated.

    The real DOM (observed 2026-06-02 against `?q=python&l=madrid`)
    embeds 5 real offer cards (after filtering out the promoted ad
    banners which also carry the `ij-OfferList-offerCardItem` class
    but lack a title heading). The other 5 li elements in the
    capture are promoted ad banners, not real offers.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        # `limit=5` matches the real-capture first-page size so the
        # test stays on a single page and the assertion isolates
        # field-mapping from pagination. The default `page.content()`
        # returns `SEARCH_PAGE_HTML` for every navigation, so a
        # higher `limit` would paginate and double-count.
        jobs = await scraper.search("python", "madrid", limit=5)
    assert len(jobs) == 5
    # First card fields are populated from the real-capture fixture.
    first = jobs[0]
    assert first.id == "i98495453525856678980690018195550513554"
    assert first.title == "Camarero/a, Ayudante Camarero/a - Hotel Es Figueral Nou 4* Sup"
    assert first.company == "NYBAU HOTELS & RESTAURANTS"
    assert first.location == "Montuïri"
    assert (
        first.url
        == "https://www.infojobs.net/ofertas-trabajo/oferta-i98495453525856678980690018195550513554"
    )
    # `posted_at` is tz-aware UTC (the real DOM has no inline
    # date; the scraper falls back to `datetime.now(UTC)`).
    assert first.posted_at.tzinfo is not None


async def test_search_populates_description_from_offer_card_content() -> None:
    """InfoJobs `_parse_cards` populates `Job.description` from `p.ij-...-description-description`.

    Spec: REQ-PARSER-INFOJOBS-001 + T-005 wiring. The real
    InfoJobs SERP (observed 2026-06-02) renders the description
    in a `<p class="ij-OfferCardContent-description-description
    [--hideOnMobile]">` element inside each card. The wiring
    in `_parse_cards` MUST call `parse_infojobs_description(card)`
    and pass the result to the `Job(...)` constructor. The test
    builds a custom HTML page with a single card carrying a
    known description (with the `--hideOnMobile` modifier so
    the class-prefix match is exercised) and asserts the
    resulting `Job.description` matches.
    """
    # The class string mirrors the real-DOM shape (the
    # `--hideOnMobile` modifier is part of the real capture).
    # We factor it into a variable to keep the f-string line
    # length under the ruff `line-length=100` cap.
    desc_class = (
        "ij-OfferCardContent-description-description"
        " ij-OfferCardContent-description-description--hideOnMobile"
    )
    html = f"""
    <html><body><main><ul>
      <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
        <div class="sui-AtomCard-Wrapper">
          <div class="sui-AtomCard">
            <div class="ij-OfferCard">
              <div class="ij-OfferCardContent">
                <div class="ij-OfferCardContent-media">
                  <a class="ij-OfferCardContent-media-link"
                     href="https://www.infojobs.net/acme/em-desc001">
                    <img alt="Acme" />
                  </a>
                </div>
                <div class="ij-OfferCardContent-description">
                  <div class="ij-OfferCardContent-description-head">
                    <h2 class="ij-OfferCardContent-description-title">Title desc001</h2>
                  </div>
                  <div class="ij-OfferCardContent-description-subtitle">
                    <a class="ij-OfferCardContent-description-subtitle-link">Co desc001</a>
                  </div>
                  <ul class="ij-OfferCardContent-description-list">
                    <li class="ij-OfferCardContent-description-list-item">City desc001</li>
                  </ul>
                  <p class="{desc_class}">
                    Se busca desarrollador Python con experiencia en FastAPI
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </li>
    </ul></main></body></html>
    """
    page = FakePage(html)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=1)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.description is not None
    # The text content of the `<p>`, stripped and whitespace-collapsed.
    assert "FastAPI" in job.description
    assert "desarrollador Python" in job.description


async def test_search_uses_configured_domain_in_oferta_url() -> None:
    """Each `Job.url` is `https://{domain}/ofertas-trabajo/oferta-{id}`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, domain="br.infojobs.net")
    async with scraper:
        jobs = await scraper.search("python", "sao-paulo", limit=1)
    assert (
        jobs[0].url
        == "https://br.infojobs.net/ofertas-trabajo/oferta-i98495453525856678980690018195550513554"
    )


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------


async def test_search_respects_limit() -> None:
    """A `limit=5` over 5 real cards returns the first 5 jobs only."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=5)
    assert len(jobs) == 5
    # The 5 real-capture ids in document order.
    assert [j.id for j in jobs] == [
        "i98495453525856678980690018195550513554",
        "i53515057515712074971181024164219803726",
        "ifa64e5d5c648baa02dc36400656c9f",
        "i83b836d94a4076bbd7eddf85410991",
        "i98505552525049841011146014033783404222",
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

    The T-010 real-capture fixture has 5 real offer cards on the
    first page. With `limit=10`, the scraper reads 5 real cards on
    page 1 and 5 synthetic cards on page 2 (returned by the page
    stub's lambda).
    """
    second_page = _build_n_cards_html(5, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=10)

    assert len(jobs) == 10
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=2",
    ]
    # First 5 are from the real first page; last 5 are from the
    # synthetic second page.
    assert jobs[0].id == "i98495453525856678980690018195550513554"
    assert jobs[4].id == "i98505552525049841011146014033783404222"  # last card on first page
    assert jobs[5].id == "xyz001"  # first card on second page
    assert jobs[9].id == "xyz005"  # last card on second page


async def test_search_does_not_paginate_when_first_page_satisfies_limit() -> None:
    """When `limit <= first_page_size`, only one page is fetched."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=3)
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1"
    ]


async def test_search_returns_first_page_results_when_subsequent_page_times_out() -> None:
    """A timeout on page > 0 (end of results or anti-bot re-challenge) is graceful.

    REQ-J-006: The scraper MUST return what it has if a subsequent
    pagination page fails. Only a failure on the FIRST page is a real
    error (raise `InfoJobsTimeoutError`); pages > 0 are treated as
    "no more results" and the loop breaks gracefully.
    """
    # First page returns the real-capture 5-card capture; second
    # page's `wait_for_selector` raises a PlaywrightTimeoutError.
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else "",
        selector_timeout=lambda url: "page=2" in url,
    )
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=20)
    # 5 jobs from page 1; loop broke on page 2 timeout (no raise).
    assert len(jobs) == 5
    assert jobs[0].id == "i98495453525856678980690018195550513554"
    # Exactly 2 page requests: page 1 succeeded, page 2 timed out.
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=2",
    ]


async def test_search_stops_at_max_pages() -> None:
    """The pagination loop never exceeds `settings.max_pages`."""
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page, max_pages=2)
    async with scraper:
        jobs = await scraper.search("python", "madrid", limit=200)

    assert len(page.goto_calls) == 2
    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1",
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=2",
    ]
    assert len(jobs) == 10  # 5 per page on the real-capture fixture, capped at limit=200


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


# ---------------------------------------------------------------------------
# `InfoJobsScraperSettings.location_resolver` field (REQ-PROV-003)
#
# The settings gain an optional `location_resolver: LocationResolverPort | None`
# kwarg. The default is `None` (backward-compat). The `HardcodedLocationResolver`
# (or any other Protocol-conforming resolver) can be injected to plumb
# province/country resolution into the scraper URL.
# ---------------------------------------------------------------------------


def test_infojobs_scraper_settings_default_resolver_is_none() -> None:
    """`InfoJobsScraperSettings()` (no `location_resolver` kwarg) defaults to `None`.

    Backward-compat invariant: pre-change code paths constructed
    the settings without the resolver; the v1 default is `None`,
    which makes the scraper fall back to the v1 `?l=<str>` URL
    formula (no `provinceIds/countryIds`).
    """
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    assert settings.location_resolver is None


def test_infojobs_scraper_settings_accept_resolver() -> None:
    """`InfoJobsScraperSettings(location_resolver=...)` accepts a resolver.

    The kwarg is keyword-only; the resolver is stored on the
    settings and read by the scraper's `search()` method.
    """
    resolver = HardcodedLocationResolver()
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
        location_resolver=resolver,
    )
    assert settings.location_resolver is resolver  # `is`, not `==`


def test_infojobs_scraper_settings_with_resolver_are_equal_and_hashable() -> None:
    """Two settings instances with the same resolver are `==` and share a `hash`.

    The slots-based + manual `__eq__` / `__hash__` discipline
    (REQ-LOC-002 invariant) carries over to the new field: two
    settings that differ ONLY in the resolver reference are
    `==` when the resolvers are the SAME object (identity
    comparison per the spec's "shared instance" invariant), and
    hashable so they can be used as dict keys.
    """
    resolver = HardcodedLocationResolver()
    a = InfoJobsScraperSettings(
        user_agent="ua",
        timeout_ms=10_000,
        location_resolver=resolver,
    )
    b = InfoJobsScraperSettings(
        user_agent="ua",
        timeout_ms=10_000,
        location_resolver=resolver,
    )
    assert a == b
    assert hash(a) == hash(b)
    # Sanity: the field is part of the hash (mismatched resolvers
    # yield different hashes).
    other = InfoJobsScraperSettings(
        user_agent="ua",
        timeout_ms=10_000,
        location_resolver=HardcodedLocationResolver(),
    )
    assert a != other


# ---------------------------------------------------------------------------
# `_build_url(..., infojobs_geo=...)` extension (REQ-PROV-002)
#
# The URL formula gains an `infojobs_geo` keyword-only arg. When the
# tuple is `(province_id, country_id)` (mapped location), the URL
# includes `&provinceIds=<id>&countryIds=<id>`. When the tuple is
# `(None, country_id)` (country-only), the URL includes
# `&countryIds=<id>` only. When the tuple is `(None, None)`
# (unmapped / empty / no resolver), the URL is byte-identical to
# the v1 `?q=<kw>&l=<loc>&page=<p>` (no extra params).
# ---------------------------------------------------------------------------


def test_infojobs_build_url_includes_province_and_country_ids_when_mapped() -> None:
    """`infojobs_geo=(34, 17)` (Málaga) → URL has `&provinceIds=34&countryIds=17`.

    The v3 URL formula appends the two query params AFTER the
    v1 `?q=<kw>&l=<loc>&page=<p>` triple, in this order:
    `provinceIds` first, then `countryIds`. The 1-indexed
    `page` param stays where it is (between `l=` and
    `provinceIds=`) so the URL is readable and the v1 shape
    is preserved at the start.
    """
    # `_build_url` is a pure function — it does not need the
    # browser or throttle. We build a minimal scraper
    # instance to access the method.
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    url = scraper._build_url(  # noqa: SLF001
        "python",
        "malaga",
        1,
        infojobs_geo=(34, 17),
    )
    assert (
        url
        == "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=malaga&page=1&provinceIds=34&countryIds=17"
    )


def test_infojobs_build_url_country_only_when_province_is_none() -> None:
    """`infojobs_geo=(None, 17)` (Remote) → URL has `&countryIds=17` only (no `provinceIds`).

    The country-only case is the canonical "Remote" / "España" /
    "teletrabajo" sentinel. The URL omits `provinceIds` (not
    emit it as `provinceIds=None`) so InfoJobs does not reject
    the param as malformed.
    """
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    url = scraper._build_url(  # noqa: SLF001
        "python",
        "remote",
        1,
        infojobs_geo=(None, 17),
    )
    assert (
        url
        == "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=remote&page=1&countryIds=17"
    )
    assert "provinceIds" not in url


def test_infojobs_build_url_falls_back_when_infojobs_geo_is_none() -> None:
    """`infojobs_geo=None` → URL is byte-identical to v1 (no `provinceIds/countryIds`).

    The v1 backward-compat path: when the resolver is not
    configured (legacy wiring) OR returns `(None, None)`
    (unmapped), the URL omits BOTH params. The `l=<loc>` param
    is preserved (the v1 scraper relied on it as the primary
    signal; v3 narrows but does not replace it).
    """
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    url = scraper._build_url(  # noqa: SLF001
        "python",
        "Berlin",
        1,
        infojobs_geo=None,
    )
    assert url == "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=Berlin&page=1"


def test_infojobs_build_url_falls_back_when_both_ids_are_none() -> None:
    """`infojobs_geo=(None, None)` (resolver miss) → URL omits BOTH params.

    The unmapped sentinel triggers the same fallback path as
    `infojobs_geo=None` — the scraper cannot narrow the
    region, so the URL is the v1 shape.
    """
    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    url = scraper._build_url(  # noqa: SLF001
        "python",
        "Tokyo",
        1,
        infojobs_geo=(None, None),
    )
    assert url == "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=Tokyo&page=1"


# ---------------------------------------------------------------------------
# `_make_fetch_one_page(keywords, location, infojobs_geo=...)` plumb
# ---------------------------------------------------------------------------


async def test_infojobs_make_fetch_one_page_captures_infojobs_geo() -> None:
    """The closure captures the `infojobs_geo` tuple and forwards it to `_build_url` on every page.

    A 2-page search with `infojobs_geo=(34, 17)` produces two
    URLs, each with `&provinceIds=34&countryIds=17`. The tuple
    is captured ONCE in the closure (per REQ-PROV-002 scenario
    5: the resolver is called once per `search()`, not per
    page).
    """
    second_page = _build_n_cards_html(5, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    scraper, _ = await _make_scraper_with(page)
    closure = scraper._make_fetch_one_page(  # noqa: SLF001
        "python",
        "malaga",
        infojobs_geo=(34, 17),
    )
    # Call the closure twice (simulating two pages) and assert
    # both URLs carry the province/country params.
    fake_page_obj = AsyncMock()
    fake_page_obj.goto = AsyncMock()
    fake_page_obj.wait_for_selector = AsyncMock()
    fake_page_obj.content = AsyncMock(return_value=SEARCH_PAGE_HTML)
    # The closure awaits `self._navigate_and_wait(page, url)`
    # which awaits `page.goto(url)`. The URL we assert is the
    # `page.goto` argument.
    await closure(fake_page_obj, 0, 20)
    await closure(fake_page_obj, 1, 20)
    goto_urls = [call.args[0] for call in fake_page_obj.goto.await_args_list]
    assert goto_urls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=malaga&page=1&provinceIds=34&countryIds=17",
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=malaga&page=2&provinceIds=34&countryIds=17",
    ]


# ---------------------------------------------------------------------------
# `search()` end-to-end: resolver called once, URL includes province/country
# ---------------------------------------------------------------------------


class _CountingResolver:
    """Minimal `LocationResolverPort` test double that counts `resolve_infojobs` calls.

    The composition-root invariant (REQ-PROV-002 scenario 5) is
    "the resolver is called EXACTLY once per `search()` call, not
    per page". The test double counts calls so the test can
    pin the call count.
    """

    def __init__(self, return_value: tuple[int | None, int | None]) -> None:
        self._return = return_value
        self.call_count = 0
        self.last_input: str | None = None

    def resolve(self, location: str) -> int | None:  # noqa: ARG002 — Protocol conformance
        return None  # LinkedIn path unused; satisfy Protocol.

    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
        self.call_count += 1
        self.last_input = location
        return self._return

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:  # noqa: ARG002
        # Protocol conformance (REQ-STR-LOC-001); the InfoJobs
        # scraper never calls this path, so the default `None`
        # return is correct.
        return None


async def test_infojobs_search_calls_resolver_exactly_once() -> None:
    """`search()` calls `resolve_infojobs(location)` exactly once (not per page).

    A 3-page paginated search yields `call_count == 1`. The
    tuple is captured in the closure and reused on every
    page. The resolver is read from `_settings.location_resolver`.
    """
    second_page = _build_n_cards_html(15, id_prefix="xyz")
    page = FakePage(
        html=lambda url: SEARCH_PAGE_HTML if "page=1" in url else second_page,
    )
    resolver = _CountingResolver(return_value=(34, 17))
    fake_browser = FakeBrowser(page)
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = InfoJobsPlaywrightScraper(
        throttle=throttle,
        settings=InfoJobsScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            max_pages=3,
            inter_page_delay_seconds=0.0,
            location_resolver=resolver,
        ),
        browser_factory=factory,
    )
    async with scraper:
        # `limit=40` forces 3 page requests (5 + 15 + ... >= 40).
        await scraper.search("python", "malaga", limit=40)

    assert resolver.call_count == 1
    assert resolver.last_input == "malaga"


async def test_infojobs_search_emits_province_country_in_url() -> None:
    """End-to-end: resolver returns `(34, 17)` → URL has `&provinceIds=34&countryIds=17`.

    A single-page search with the v1 `SEARCH_PAGE_HTML` fixture
    asserts the URL is the v3 narrowed shape. The test pins
    BOTH the URL contract AND that the resolver input is the
    raw `location` string the caller passed (NOT a
    pre-normalized form — the resolver normalizes internally).
    """
    page = FakePage(SEARCH_PAGE_HTML)
    resolver = _CountingResolver(return_value=(34, 17))
    fake_browser = FakeBrowser(page)
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = InfoJobsPlaywrightScraper(
        throttle=throttle,
        settings=InfoJobsScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            max_pages=10,
            inter_page_delay_seconds=0.0,
            location_resolver=resolver,
        ),
        browser_factory=factory,
    )
    async with scraper:
        await scraper.search("python", "malaga", limit=5)

    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=malaga&page=1&provinceIds=34&countryIds=17",
    ]


async def test_infojobs_search_emits_country_only_when_province_is_none() -> None:
    """`?l=remote` + resolver returns `(None, 17)` → URL has `&countryIds=17` only.

    The "Remote" / "teletrabajo" / "España" case: country is
    set, province is `None`. The URL builder omits
    `provinceIds` (NOT emit it as `provinceIds=None`) so
    InfoJobs does not reject the param.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    resolver = _CountingResolver(return_value=(None, 17))
    fake_browser = FakeBrowser(page)
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = InfoJobsPlaywrightScraper(
        throttle=throttle,
        settings=InfoJobsScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            location_resolver=resolver,
        ),
        browser_factory=factory,
    )
    async with scraper:
        await scraper.search("python", "remote", limit=5)

    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=remote&page=1&countryIds=17",
    ]


async def test_infojobs_search_falls_back_when_resolver_returns_none_none() -> None:
    """Resolver returns `(None, None)` (unmapped) → URL is v1 (no `provinceIds/countryIds`).

    The unmapped sentinel triggers the same fallback as
    `location_resolver=None` (the legacy wiring). The
    `l=<loc>` param is preserved so the v1 contract is
    not regressed for unmapped cities.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    resolver = _CountingResolver(return_value=(None, None))
    fake_browser = FakeBrowser(page)
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = InfoJobsPlaywrightScraper(
        throttle=throttle,
        settings=InfoJobsScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            location_resolver=resolver,
        ),
        browser_factory=factory,
    )
    async with scraper:
        await scraper.search("python", "Berlin", limit=5)

    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=Berlin&page=1",
    ]


async def test_infojobs_search_falls_back_when_no_resolver_configured() -> None:
    """`location_resolver=None` (legacy wiring) → URL is v1, no WARNING is logged in this path.

    The v1 backward-compat path: the scraper was constructed
    without a resolver (the pre-change wiring). The URL is
    byte-identical to the pre-change behavior. The DeprecationWarning
    is logged ONCE per process (the test asserts the URL
    shape, not the warning — the warning is a separate test
    in the next section).
    """
    page = FakePage(SEARCH_PAGE_HTML)
    # `_make_scraper_with` does not pass `location_resolver`, so
    # the settings default to `None` (the legacy wiring).
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "madrid", limit=5)

    assert page.goto_calls == [
        "https://www.infojobs.net/ofertas-trabajo?keyword=python&l=madrid&page=1",
    ]


async def test_infojobs_search_logs_warning_when_no_resolver_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Legacy wiring (`location_resolver=None`) logs a DeprecationWarning once.

    The warning guides operators to wire the resolver (the v3
    recommended path). The warning is INFO-level (not WARNING)
    so it does not pollute the WARNING-strict logs that ops
    use to spot unmapped cities.
    """
    page = FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with caplog.at_level(logging.INFO, logger="jobs_finder.infrastructure.infojobs.scraper"):
            await scraper.search("python", "madrid", limit=5)
    # At least one INFO record was emitted with the "no resolver"
    # hint. The exact text is part of the impl; the test pins
    # the BEHAVIOR (a log is emitted) without coupling to the
    # exact wording.
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("resolver" in r.getMessage().lower() for r in info_records)
