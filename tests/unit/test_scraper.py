"""Unit tests for `LinkedInPlaywrightScraper`.

Spec: REQ-013, REQ-024.
The scraper drives a real Chromium in production. Tests use minimal fake
`Page` / `Context` / `Browser` objects so the suite never launches a
browser and never contacts LinkedIn.
"""

from __future__ import annotations

import inspect
import time
from typing import Any
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from jobs_finder.infrastructure.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInTimeoutError,
)
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    LinkedInScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from tests.fixtures.linkedin_search import BLOCK_PAGE_HTML

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePage:
    """Minimal Playwright `Page` stub for scraper tests.

    `html` is the HTML returned for every `content()` call. When `pages`
    is provided, each `goto` pops the next HTML string into `self.html`;
    an exhausted `pages` queue raises a `PlaywrightTimeoutError` so the
    pagination tests can exercise the "no more pages" path without
    setting up a separate per-page selector-timeout callable.

    `selector_timeout` (bool) still works for the single-page tests —
    when True, every `wait_for_selector` raises a
    `PlaywrightTimeoutError`. It can be combined with `pages` only when
    the test wants the same timeout behavior on every page.
    """

    def __init__(
        self,
        html: str,
        *,
        selector_timeout: bool = False,
        goto_error: Exception | None = None,
        pages: list[str] | None = None,
    ) -> None:
        self.html = html
        self.selector_timeout = selector_timeout
        self.goto_error = goto_error
        self.pages: list[str] | None = pages
        self.goto_calls: list[str] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error
        if self.pages is not None:
            # Queue semantics: each `goto` consumes one HTML payload;
            # an exhausted queue simulates "no more pages" by raising
            # a PlaywrightTimeoutError that `_navigate_and_wait` will
            # convert to `LinkedInTimeoutError` (which the loop catches
            # gracefully for `page_index > 0`).
            if not self.pages:
                raise PlaywrightTimeoutError("FakePage: pages queue exhausted")
            self.html = self.pages.pop(0)

    async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.wait_calls.append((selector, timeout))
        if self.selector_timeout:
            raise PlaywrightTimeoutError(f"selector {selector!r} not found")

    async def content(self) -> str:
        return self.html

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    """Minimal Playwright `BrowserContext` stub."""

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False
        self.new_page_calls = 0

    async def new_page(self) -> FakePage:
        self.new_page_calls += 1
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
# Fixtures
# ---------------------------------------------------------------------------


def _three_card_html() -> str:
    return """
    <html><body>
      <ul>
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:3850000001">
          <a class="base-card__full-link"
             href="https://es.linkedin.com/jobs/view/senior-python-developer-at-acme-3850000001">
            <span class="sr-only">Senior Python Developer</span>
          </a>
          <h3 class="base-search-card__title">Senior Python Developer</h3>
          <h4 class="base-search-card__subtitle">Acme Corp</h4>
          <span class="job-search-card__location">Madrid, Spain</span>
          <time class="job-search-card__listdate"
                datetime="2026-05-01T00:00:00+00:00">1 day ago</time>
        </div>
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:3850000002">
          <a class="base-card__full-link"
             href="https://es.linkedin.com/jobs/view/backend-engineer-at-globex-3850000002">
            <span class="sr-only">Backend Engineer</span>
          </a>
          <h3 class="base-search-card__title">Backend Engineer</h3>
          <h4 class="base-search-card__subtitle">Globex Inc</h4>
          <span class="job-search-card__location">Barcelona, Spain</span>
          <time class="job-search-card__listdate"
                datetime="2026-05-02T00:00:00+00:00">2 days ago</time>
        </div>
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:3850000003">
          <a class="base-card__full-link"
             href="https://es.linkedin.com/jobs/view/data-scientist-at-initech-3850000003">
            <span class="sr-only">Data Scientist</span>
          </a>
          <h3 class="base-search-card__title">Data Scientist</h3>
          <h4 class="base-search-card__subtitle">Initech</h4>
          <span class="job-search-card__location">Valencia, Spain</span>
          <time class="job-search-card__listdate"
                datetime="2026-05-03T00:00:00+00:00">3 days ago</time>
        </div>
      </ul>
    </body></html>
    """


def _five_card_html() -> str:
    cards: list[str] = []
    for i in range(1, 6):
        cards.append(
            f"""
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:385000000{i}">
          <a class="base-card__full-link"
             href="https://es.linkedin.com/jobs/view/title-{i}-at-company-{i}-385000000{i}">
            <span class="sr-only">Title {i}</span>
          </a>
          <h3 class="base-search-card__title">Title {i}</h3>
          <h4 class="base-search-card__subtitle">Company {i}</h4>
          <span class="job-search-card__location">Madrid</span>
          <time class="job-search-card__listdate"
                datetime="2026-05-0{i}T00:00:00+00:00">{i}d ago</time>
        </div>"""
        )
    return "<html><body><ul>" + "".join(cards) + "</ul></body></html>"


def _n_card_html(n: int, *, id_start: int = 1, date_prefix: str = "2026-05-") -> str:
    """Build a search-results page with exactly `n` cards.

    `id_start` controls the leading digit of the `data-entity-urn` so
    the same id range doesn't collide between test fixtures (e.g. the
    pagination test uses 1..25 for page 0 and 26..50 for page 1).
    `date_prefix` lets the caller shift the `datetime` value (otherwise
    multiple test pages with `2026-05-01..2026-05-25` would all share
    the same date prefix, which is fine but visually noisy).
    """
    cards: list[str] = []
    for offset in range(n):
        i = id_start + offset
        # Day of month rolls past 31; the date string is just for
        # the `<time datetime="...">` attribute which the test only
        # needs to be a parseable ISO date. `i` is always non-zero.
        day = ((i - 1) % 28) + 1
        cards.append(
            f"""
        <div class="base-card base-search-card job-search-card"
             data-entity-urn="urn:li:jobPosting:385{i:07d}">
          <a class="base-card__full-link"
             href="https://es.linkedin.com/jobs/view/title-{i}-at-company-{i}-385{i:07d}">
            <span class="sr-only">Title {i}</span>
          </a>
          <h3 class="base-search-card__title">Title {i}</h3>
          <h4 class="base-search-card__subtitle">Company {i}</h4>
          <span class="job-search-card__location">Madrid</span>
          <time class="job-search-card__listdate"
                datetime="{date_prefix}{day:02d}T00:00:00+00:00">{day}d ago</time>
        </div>"""
        )
    return "<html><body><ul>" + "".join(cards) + "</ul></body></html>"


def _settings(
    *,
    timeout_ms: int = 10_000,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 0.0,
) -> LinkedInScraperSettings:
    """Build a `LinkedInScraperSettings` for tests.

    The `inter_page_delay_seconds=0.0` default is intentional: tests
    that don't care about pacing stay fast. The
    `TestInterPageDelay` class (T-001.c) explicitly passes a non-zero
    value and monkeypatches `asyncio.sleep` to assert the call.
    """
    return LinkedInScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=timeout_ms,
        max_pages=max_pages,
        inter_page_delay_seconds=inter_page_delay_seconds,
    )


async def _make_scraper_with(
    page: FakePage,
    *,
    timeout_ms: int = 10_000,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 0.0,
) -> tuple[LinkedInPlaywrightScraper, FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent.

    The throttle is configured with `min_interval_seconds=0.0` so the
    tests don't actually sleep between calls. The inter-page delay
    defaults to `0.0` for the same reason; tests that exercise the
    pacing behavior pass a non-zero value and monkeypatch
    `asyncio.sleep`.
    """
    fake_browser = FakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=_settings(
            timeout_ms=timeout_ms,
            max_pages=max_pages,
            inter_page_delay_seconds=inter_page_delay_seconds,
        ),
        browser_factory=factory,
    )
    return scraper, fake_browser


# ---------------------------------------------------------------------------
# Navigation target (REQ-013: URL is well-formed and quoted)
# ---------------------------------------------------------------------------


async def test_search_navigates_to_linkedin_jobs_search() -> None:
    """The URL contains the quoted keywords and location on the right host,
    plus the `&start=0` offset (REQ-L-007 + REQ-L-008 — the new pagination
    loop always navigates with an explicit `start=N` even on the first
    page).

    `limit=3` constrains the loop to a single page so the assertion
    isolates the URL contract from the pagination contract. The default
    `limit=20` would let the loop fetch 10 pages against the same
    HTML (3 cards per page → 30 jobs total).
    """
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search(keywords="python", location="Madrid", limit=3)
    assert page.goto_calls == [
        "https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start=0"
    ]


async def test_search_waits_for_results_selector_with_configured_timeout() -> None:
    """`wait_for_selector` is called with the configured `timeout_ms`.

    `limit=3` constrains the loop to a single page so the assertion
    isolates the wait-for-selector contract from the pagination
    contract.
    """
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page, timeout_ms=10_000)
    async with scraper:
        await scraper.search("python", "Madrid", limit=3)
    assert page.wait_calls == [("div[data-entity-urn]", 10_000)]


# ---------------------------------------------------------------------------
# Happy path (REQ-013)
# ---------------------------------------------------------------------------


async def test_search_returns_one_job_per_card() -> None:
    """Three cards in the page yield three `Job` objects with the right fields.

    `limit=3` constrains the loop to a single page so the assertion
    isolates the field-mapping contract from the pagination contract.
    """
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "Madrid", limit=3)
    assert len(jobs) == 3
    assert [j.id for j in jobs] == ["3850000001", "3850000002", "3850000003"]
    assert [j.title for j in jobs] == [
        "Senior Python Developer",
        "Backend Engineer",
        "Data Scientist",
    ]
    assert [j.company for j in jobs] == ["Acme Corp", "Globex Inc", "Initech"]
    assert [j.location for j in jobs] == [
        "Madrid, Spain",
        "Barcelona, Spain",
        "Valencia, Spain",
    ]


async def test_search_creates_browser_context_with_user_agent_and_viewport() -> None:
    """`new_context` is called with the configured user-agent and 1280x800 viewport."""
    page = FakePage(_three_card_html())
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "Madrid")
    assert len(fake_browser.new_context_calls) == 1
    kwargs = fake_browser.new_context_calls[0]
    assert kwargs["user_agent"] == "test-agent/1.0"
    assert kwargs["viewport"] == {"width": 1280, "height": 800}


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------


async def test_search_respects_limit() -> None:
    """A `limit=2` over 5 cards returns the first 2 jobs only."""
    page = FakePage(_five_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "Madrid", limit=2)
    assert len(jobs) == 2
    assert [j.id for j in jobs] == ["3850000001", "3850000002"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


async def test_search_raises_blocked_on_auth_wall() -> None:
    """An auth-wall page raises `LinkedInBlockedError`."""
    page = FakePage(BLOCK_PAGE_HTML)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(LinkedInBlockedError, match="auth-wall"):
            await scraper.search("python", "Madrid")


async def test_search_raises_timeout_when_results_never_appear() -> None:
    """A `PlaywrightTimeoutError` from `wait_for_selector` becomes `LinkedInTimeoutError`."""
    page = FakePage(_three_card_html(), selector_timeout=True)
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        with pytest.raises(LinkedInTimeoutError, match="timeout"):
            await scraper.search("python", "Madrid")


# ---------------------------------------------------------------------------
# Async context manager shape
# ---------------------------------------------------------------------------


async def test_scraper_is_an_async_context_manager() -> None:
    """`LinkedInPlaywrightScraper` is an async context manager."""
    page = FakePage(_three_card_html())
    scraper, fake_browser = await _make_scraper_with(page)
    assert hasattr(scraper, "__aenter__")
    assert hasattr(scraper, "__aexit__")
    assert inspect.iscoroutinefunction(scraper.__aenter__)
    assert inspect.iscoroutinefunction(scraper.__aexit__)
    async with scraper:
        pass
    # Injected browser must NOT be closed (we don't own it).
    assert not fake_browser.closed


async def test_owned_browser_is_closed_on_exit() -> None:
    """When no `browser_factory` is injected, the scraper closes the browser on exit.

    We can't easily verify the *real* browser is closed without launching
    Chromium, so this test passes an injected factory and asserts the
    factory's browser is NOT closed (the opposite of the injected case).
    The fact that the scraper's `__aexit__` does not crash is the second
    signal.
    """
    page = FakePage(_three_card_html())
    scraper, fake_browser = await _make_scraper_with(page)
    async with scraper:
        pass
    # Injected browser: scraper must not close it.
    assert not fake_browser.closed


# ---------------------------------------------------------------------------
# Pagination (REQ-L-007) — auto-pagination loop with start=0, 25, 50, ...
#
# The 6 scenarios below are the spec's REQ-L-007 acceptance cases. The
# `pages` queue on `FakePage` lets each `goto` return a different HTML
# payload; an exhausted queue raises `PlaywrightTimeoutError` so the
# "no more pages" path is exercised without standing up a per-page
# selector-timeout callable.
# ---------------------------------------------------------------------------


class TestPaginationLoop:
    """REQ-L-007 — auto-pagination loop with start=0, 25, 50, ... offsets."""

    async def test_first_page_offset_is_zero(self) -> None:
        """First page navigates to `&start=0` (REQ-L-007 scenario 1).

        `limit=1` forces the loop to stop after page 0 so the assertion
        isolates the first-page URL contract from the pagination
        contract. The default `limit=20` would let the loop fetch
        more pages and dilute the assertion.
        """
        page = FakePage(
            html="",
            pages=[_n_card_html(1, id_start=1, date_prefix="2026-05-")],
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            await scraper.search("python", "Madrid", limit=1)
        assert page.goto_calls == [
            "https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start=0"
        ]

    async def test_second_page_offset_is_twenty_five(self) -> None:
        """Second page navigates to `&start=25` (REQ-L-007 scenario 2).

        Page 0 yields 10 cards; `limit=30` forces the loop to fetch
        page 1. The second `goto` URL MUST contain `&start=25`.
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(10, id_start=1, date_prefix="2026-05-"),
                _n_card_html(10, id_start=26, date_prefix="2026-05-"),
            ],
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            await scraper.search("python", "Madrid", limit=30)
        assert len(page.goto_calls) >= 2
        assert page.goto_calls[0].endswith("&start=0")
        assert page.goto_calls[1].endswith("&start=25")

    async def test_limit_cap_stops_after_first_page(self) -> None:
        """`limit=2` over 25+25 returns exactly 2 jobs; the loop breaks
        after page 0 (REQ-L-007 scenario 3).

        The `len(jobs) >= limit` check at the top of the loop stops
        further page requests once the requested cap is reached.
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(25, id_start=1, date_prefix="2026-05-"),
                _n_card_html(25, id_start=26, date_prefix="2026-05-"),
            ],
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            jobs = await scraper.search("python", "Madrid", limit=2)
        assert len(jobs) == 2
        # Loop must stop after page 0 — only ONE goto.
        assert len(page.goto_calls) == 1

    async def test_zero_cards_on_page_one_breaks_loop(self) -> None:
        """Page 1 returns 0 cards → the loop breaks gracefully and returns
        page 0's results (REQ-L-007 scenario 4).

        The `if not new_jobs: break` invariant signals the end of the
        result stream without raising. The page-1 200 OK with zero
        cards is the canonical "we've drained the SERP" signal.
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(25, id_start=1, date_prefix="2026-05-"),
                "<html><body><ul></ul></body></html>",  # zero cards
            ],
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            jobs = await scraper.search("python", "Madrid", limit=50)
        assert len(jobs) == 25
        # Page 0 succeeded, page 1 returned 0 cards → loop broke. Exactly 2 gotos.
        assert len(page.goto_calls) == 2
        assert page.goto_calls[0].endswith("&start=0")
        assert page.goto_calls[1].endswith("&start=25")

    async def test_page_zero_timeout_raises(self) -> None:
        """Page 0 timeout raises `LinkedInTimeoutError` (REQ-L-007 scenario 5).

        A `wait_for_selector` timeout on the FIRST page is a real error
        (the SERP never returned results) and MUST propagate. The
        `selector_timeout=True` flag on `FakePage` triggers this path
        on every page; with a 1-page queue the test exercises page 0
        specifically.
        """
        page = FakePage(
            html="",
            pages=[_n_card_html(1, id_start=1, date_prefix="2026-05-")],
            selector_timeout=True,
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            with pytest.raises(LinkedInTimeoutError, match="timeout"):
                await scraper.search("python", "Madrid", limit=10)

    async def test_subsequent_page_timeout_breaks_gracefully(self) -> None:
        """Page 1+ timeout breaks gracefully and returns page 0's results
        (REQ-L-007 scenario 6).

        The `pages` queue is exhausted after page 0, so the second
        `goto` raises `PlaywrightTimeoutError` (the FakePage's "queue
        exhausted" signal). `_navigate_and_wait` converts that to
        `LinkedInTimeoutError`, and the loop catches it because
        `page_index > 0`. No exception propagates to the caller.
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(25, id_start=1, date_prefix="2026-05-"),
                # Intentionally no second page — the queue exhaustion
                # simulates "LinkedIn anti-bot timeout on page 2".
            ],
        )
        scraper, _ = await _make_scraper_with(page, max_pages=3)
        async with scraper:
            jobs = await scraper.search("python", "Madrid", limit=30)
        assert len(jobs) == 25
        # Page 0 succeeded, page 1 timed out → loop broke gracefully.
        assert len(page.goto_calls) == 2
        assert page.goto_calls[0].endswith("&start=0")
        assert page.goto_calls[1].endswith("&start=25")


# ---------------------------------------------------------------------------
# Inter-page pacing (REQ-L-009)
#
# The pagination loop MUST `await asyncio.sleep(inter_page_delay_seconds)`
# BEFORE navigating to `page_index > 0`. The first page is never delayed.
# A delay of `0.0` skips the call entirely (no event-loop yield, no
# wall-clock wait).
#
# Tests monkeypatch `asyncio.sleep` with an `AsyncMock` so the test
# doesn't actually sleep — the count + the awaited args are the
# assertions, not the wall-clock duration. The mock is set on the
# `asyncio` module because the production code calls
# `asyncio.sleep(...)` directly (no local alias).
# ---------------------------------------------------------------------------


class TestInterPageDelay:
    """REQ-L-009 — `asyncio.sleep(inter_page_delay_seconds)` between pages."""

    async def test_default_delay_fires_once_per_page_above_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A 3-page search with `inter_page_delay_seconds=1.0` calls
        `asyncio.sleep(1.0)` exactly 2 times (before pages 1 and 2 —
        page 0 is never delayed).

        The default LinkedIn delay of 1.0s mirrors the Indeed default
        (REQ-L-009) — enough to avoid LinkedIn anti-bot re-challenges
        on the 2nd+ request without making a single search feel slow.
        """
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        page = FakePage(
            html="",
            pages=[
                _n_card_html(15, id_start=1, date_prefix="2026-05-"),
                _n_card_html(15, id_start=26, date_prefix="2026-05-"),
                _n_card_html(15, id_start=51, date_prefix="2026-05-"),
            ],
        )
        scraper, _ = await _make_scraper_with(
            page,
            max_pages=3,
            inter_page_delay_seconds=1.0,
        )
        async with scraper:
            await scraper.search("python", "Madrid", limit=50)

        # 3 page requests → 2 inter-page sleeps (page 0 is never delayed).
        assert sleep_mock.await_count == 2
        # Both sleeps were called with the configured delay as a positional arg.
        assert sleep_mock.await_args_list[0].args == (1.0,)
        assert sleep_mock.await_args_list[1].args == (1.0,)

    async def test_zero_delay_skips_sleep_call_entirely(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`inter_page_delay_seconds=0.0` disables the inter-page sleep.

        The check `> 0` short-circuits the call to `asyncio.sleep`, so
        the event loop is not yielded unnecessarily. Tests that don't
        care about pacing can leave the default `0.0` and still pass.
        """
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        page = FakePage(
            html="",
            pages=[
                _n_card_html(15, id_start=1, date_prefix="2026-05-"),
                _n_card_html(15, id_start=26, date_prefix="2026-05-"),
                _n_card_html(15, id_start=51, date_prefix="2026-05-"),
            ],
        )
        scraper, _ = await _make_scraper_with(
            page,
            max_pages=3,
            inter_page_delay_seconds=0.0,
        )
        async with scraper:
            await scraper.search("python", "Madrid", limit=50)

        # No sleep calls at all (the throttle is also `0.0` and the
        # inter-page delay is disabled).
        assert sleep_mock.await_count == 0

    async def test_page_zero_is_never_delayed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`page_index == 0` is never preceded by an inter-page sleep.

        Even with a non-zero delay (5.0s) and a 1-page search, the
        `page_index > 0` guard ensures the very first page request
        is never delayed. The sleep fires only between pages, not
        before the first one.
        """
        sleep_mock = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", sleep_mock)

        page = FakePage(
            html="",
            pages=[_n_card_html(25, id_start=1, date_prefix="2026-05-")],
        )
        scraper, _ = await _make_scraper_with(
            page,
            max_pages=2,
            inter_page_delay_seconds=5.0,
        )
        async with scraper:
            await scraper.search("python", "Madrid", limit=10)

        # 1 goto (page 0) → 0 inter-page sleeps. The second `goto`
        # is skipped because the queue is exhausted AFTER page 0;
        # `goto_calls` records the first one only.
        assert sleep_mock.await_count == 0
        assert len(page.goto_calls) == 1


# ---------------------------------------------------------------------------
# Throttle scope (REQ-L-010)
#
# The `AsyncThrottle` is acquired ONCE per `search()` call (around the
# whole pagination loop). Consecutive `search()` calls are paced by
# `min_interval_seconds`; page requests within ONE search happen
# back-to-back. This matches the Indeed v1 contract.
# ---------------------------------------------------------------------------


class TestThrottleOncePerSearch:
    """REQ-L-010 — `AsyncThrottle` is acquired once around the whole loop."""

    async def test_throttle_acquired_exactly_once_for_two_page_search(self) -> None:
        """A 2-page search acquires the throttle lock exactly 1 time.

        The throttle's `_lock` is the same `asyncio.Lock` instance the
        scraper enters via `async with self._throttle:`. The test
        counts `acquire()` calls before and after the search to prove
        the lock was taken exactly once (not once per page).
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(10, id_start=1, date_prefix="2026-05-"),
                _n_card_html(10, id_start=26, date_prefix="2026-05-"),
            ],
        )
        scraper, _ = await _make_scraper_with(
            page,
            max_pages=2,
            inter_page_delay_seconds=0.0,
        )
        # Spy on the throttle's lock.acquire. We patch the method on
        # the lock instance itself (not on the class) so the spy
        # doesn't leak across tests.
        lock = scraper._throttle._lock
        original_acquire = lock.acquire
        acquire_calls = 0

        async def counting_acquire(*args: Any, **kwargs: Any) -> Any:
            nonlocal acquire_calls
            acquire_calls += 1
            return await original_acquire(*args, **kwargs)

        lock.acquire = counting_acquire  # type: ignore[method-assign]
        try:
            async with scraper:
                await scraper.search("python", "Madrid", limit=30)
        finally:
            lock.acquire = original_acquire  # type: ignore[method-assign]

        # 1 acquisition wraps the whole 2-page loop (not 2 acquisitions).
        assert acquire_calls == 1
        # 2 page requests inside the loop.
        assert len(page.goto_calls) == 2

    async def test_throttle_released_after_loop_completes(self) -> None:
        """The throttle's `_last_exit` is set after the search returns.

        This is the contract that lets a follow-up `search()` honor the
        `min_interval_seconds` gap (the throttle's `__aenter__` reads
        `_last_exit` and sleeps for the remainder if needed).
        """
        page = FakePage(
            html="",
            pages=[_n_card_html(1, id_start=1, date_prefix="2026-05-")],
        )
        scraper, _ = await _make_scraper_with(page, inter_page_delay_seconds=0.0)
        async with scraper:
            await scraper.search("python", "Madrid", limit=5)
        # After the search returns, `_last_exit` MUST be a float
        # (set inside `__aexit__` via `time.monotonic()`).
        assert scraper._throttle._last_exit is not None
        assert isinstance(scraper._throttle._last_exit, float)

    async def test_back_to_back_pages_inside_loop_do_not_respect_min_interval(
        self,
    ) -> None:
        """Page requests inside ONE search happen back-to-back, not
        spaced by the throttle's `min_interval_seconds`.

        With `min_interval_seconds=10.0` and `inter_page_delay_seconds=0.0`,
        a 2-page search MUST complete in well under 10 seconds (no
        per-page throttle).         The wall-clock assertion (`< 1s`) leaves
        generous headroom for CI variability; the real contract is
        "no per-page pacing" and the timing is the testable proxy.
        """
        page = FakePage(
            html="",
            pages=[
                _n_card_html(10, id_start=1, date_prefix="2026-05-"),
                _n_card_html(10, id_start=26, date_prefix="2026-05-"),
            ],
        )
        # The throttle uses `min_interval_seconds=10.0`. If the loop
        # acquired the throttle once per page, the second acquire
        # would sleep ~10s. We pass `min_interval_seconds=10.0`
        # directly to prove back-to-back pages don't trigger the
        # inter-search gap.
        fake_browser = FakeBrowser(page)
        throttle = AsyncThrottle(min_interval_seconds=10.0)

        async def factory() -> FakeBrowser:
            return fake_browser

        scraper = LinkedInPlaywrightScraper(
            throttle=throttle,
            settings=_settings(
                max_pages=2,
                inter_page_delay_seconds=0.0,
            ),
            browser_factory=factory,
        )

        start = time.monotonic()
        async with scraper:
            await scraper.search("python", "Madrid", limit=30)
        elapsed = time.monotonic() - start

        # Back-to-back pages: 2 gotos, well under 1s of wall-clock
        # time. The 10s min_interval only applies BETWEEN `search()`
        # calls, never between pages within one.
        assert len(page.goto_calls) == 2
        assert elapsed < 1.0, f"expected back-to-back pages but took {elapsed:.2f}s"
