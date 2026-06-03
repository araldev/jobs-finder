"""Indeed Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-I-007, REQ-I-016, REQ-PAG-001..PAG-003.

Lifecycle: `async with scraper:` launches a headless Chromium with a
configurable user-agent (or accepts an injected `browser_factory` for
tests). `await scraper.search(...)` serializes through the injected
`IndeedAsyncThrottle`, opens a new context + page, navigates to the
Indeed search URL with `start=0`, waits for the results selector,
parses the cards via the pure parsers, and returns a `list[Job]`
sliced to `limit`.

Auto-pagination (REQ-I-007, REQ-PAG-001..PAG-003): the loop is owned
by the canonical `paginated_search` helper at
`jobs_finder.infrastructure.pagination`. The scraper contributes a
`_make_fetch_one_page(keywords, location)` closure that captures
Indeed's URL formula (`start=page_index*10`), `is_indeed_blocked`
check, the 3-arg `_parse_cards(soup, remaining, domain)`, and the
page-0 zero-cards `IndeedParseError` semantic. The loop terminates
early when the requested `limit` is reached OR when a page yields
zero new cards OR when a per-page `wait_for_selector` timeout
occurs on page > 0 (end of results / anti-bot re-challenge —
break gracefully). A timeout on page 0 is a real error and
propagates as `IndeedTimeoutError`.

Inter-page pacing (REQ-I-003, REQ-PAG-002): the helper awaits
`asyncio.sleep(inter_page_delay_seconds)` BEFORE the next page
request; page 0 is never delayed. The `> 0` guard skips the call
entirely when the delay is `0.0`. The default
`Settings.indeed_inter_page_delay_seconds = 1.0` is sourced from
env; tests pass `0.0` to disable.

Stealth (REQ-S-001, REQ-S-004): when the constructor receives a
`Stealth()` instance, `apply_stealth_async` is called on the
context AFTER `new_context` and BEFORE `new_page` (per
`playwright_stealth` docs: "Apply Stealth to Playwright
Contexts"). Production wires `Stealth()` in
`app_factory.build_app()`; tests pass `stealth=None` (the default).

Throttle (REQ-I-008, REQ-PAG-002): the `IndeedAsyncThrottle` is
acquired ONCE around the whole pagination loop (per `search()`
call) by the helper so consecutive `search()` calls are paced by
`min_interval_seconds` while the page requests within a single
search happen back-to-back.

Errors:
- `playwright.async_api.TimeoutError` from `wait_for_selector` ->
  `IndeedTimeoutError` (the results selector never appeared).
- `is_indeed_blocked(content)` is True after the page is loaded ->
  `IndeedBlockedError` (Cloudflare / anti-bot challenge page).
- Zero cards on the first page ->
  `IndeedParseError(details={"reason": "zero_cards_on_first_page"})`.
- Any other `PlaywrightError` during navigation -> `IndeedBlockedError`.
- A card that fails to parse -> `IndeedParseError` (one bad card
  aborts the whole response; we never return a silent partial list).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.application.ports import JobSearchPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.pagination import paginated_search

from .exceptions import IndeedBlockedError, IndeedParseError, IndeedTimeoutError
from .parsers import (
    is_indeed_blocked,
    parse_indeed_company,
    parse_indeed_job_id,
    parse_indeed_location,
    parse_indeed_posted_at,
    parse_indeed_title,
    parse_indeed_url,
)
from .throttle import IndeedAsyncThrottle

# The CSS selector for a single search-results card on the Indeed SERP.
# Used both as the `wait_for_selector` target AND by the parsers via the
# private module constant in `parsers.py` (kept in sync). If Indeed
# changes the card class name in the future, both this line and the
# one in `parsers.py` need to change.
RESULTS_SELECTOR = "div.job_seen_beacon"

# `browser_factory` returns the live `Browser` to drive in `__aenter__`.
# In production this is `None` and the scraper launches Chromium itself.
# In tests the factory injects a fake `Browser` so the suite never
# launches a browser and never contacts Indeed.
BrowserFactory = Callable[[], Awaitable[Any]]


class IndeedScraperSettings:
    """Bundles the configuration values the Indeed scraper reads at runtime.

    Mirrors `LinkedIn.ScraperSettings` plus the two extra Indeed-specific
    fields (`domain` and `max_pages`). Slots-based + manual `__eq__` /
    `__hash__` keeps it hashable and immutable; the fields are
    keyword-only so the test fixtures read top-to-bottom the way
    `Settings` is structured.
    """

    __slots__ = ("domain", "inter_page_delay_seconds", "max_pages", "timeout_ms", "user_agent")

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int,
        domain: str = "es.indeed.com",
        max_pages: int = 10,
        inter_page_delay_seconds: float = 0.0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self.domain = domain
        self.max_pages = max_pages
        self.inter_page_delay_seconds = inter_page_delay_seconds

    def __repr__(self) -> str:
        return (
            f"IndeedScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, domain={self.domain!r}, "
            f"max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IndeedScraperSettings):
            return NotImplemented
        return (
            self.user_agent == other.user_agent
            and self.timeout_ms == other.timeout_ms
            and self.domain == other.domain
            and self.max_pages == other.max_pages
            and self.inter_page_delay_seconds == other.inter_page_delay_seconds
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.user_agent,
                self.timeout_ms,
                self.domain,
                self.max_pages,
                self.inter_page_delay_seconds,
            )
        )


class IndeedPlaywrightScraper(JobSearchPort):
    """Implements `JobSearchPort` for Indeed using Playwright."""

    def __init__(
        self,
        *,
        throttle: IndeedAsyncThrottle,
        settings: IndeedScraperSettings,
        browser_factory: BrowserFactory | None = None,
        stealth: Stealth | None = None,
    ) -> None:
        """Construct the scraper.

        Args:
            throttle: The per-source async throttle that paces
                consecutive `search()` calls.
            settings: The scraper settings (user-agent, timeout, etc.).
            browser_factory: Optional async factory returning a live
                Playwright `Browser`. When provided, the scraper
                delegates to it in `__aenter__` and does NOT close
                the browser in `__aexit__` (caller owns it). When
                `None`, the scraper launches headless Chromium and
                owns the browser for its full lifetime.
            stealth: Optional `playwright_stealth.Stealth` instance.
                When provided, the scraper calls
                `await stealth.apply_stealth_async(context)` on the
                browser context created per `search()` so the live
                Chromium evades Cloudflare's bot detection. When
                `None` (the default, used in tests), no stealth is
                applied. Production wires `Stealth()` in the
                composition root; tests pass `None` (or a mock) so
                the suite never touches the real stealth script.
        """
        self._throttle = throttle
        self._settings = settings
        self._browser_factory = browser_factory
        self._owns_browser: bool = browser_factory is None
        self._browser: Any = None
        self._playwright: Any = None
        self._stealth: Stealth | None = stealth

    async def __aenter__(self) -> Self:
        if self._browser_factory is not None:
            self._browser = await self._browser_factory()
        else:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_browser:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        """Run a single search; paginate until `limit` is reached or `max_pages` exhausted.

        The pagination loop is owned by `paginated_search` (REQ-PAG-001
        ..PAG-003). This method is the composition seam: it opens a
        fresh context + page, optionally applies stealth, then hands
        control to the helper with an Indeed-specific
        `_make_fetch_one_page` closure. The helper acquires the
        throttle (REQ-I-008 / REQ-PAG-002) ONCE around the whole loop
        and owns the limit / max_pages / inter-page-delay / timeout /
        zero-cards control flow.

        Per-page pacing would slow down a single search unacceptably;
        per-search pacing matches the LinkedIn and InfoJobs scrapers'
        contract.
        """
        ctx = await self._browser.new_context(user_agent=self._settings.user_agent)
        # Stealth MUST be applied AFTER `new_context` (per
        # `playwright_stealth` docs: "Apply Stealth to Playwright
        # Contexts") and BEFORE `new_page` so the page that follows
        # inherits the patched navigator/UA. The check is opt-in:
        # `stealth=None` (the test default) skips the call entirely,
        # so unit tests never reach the real script.
        if self._stealth is not None:
            await self._stealth.apply_stealth_async(ctx)
        try:
            page = await ctx.new_page()
            try:
                return await paginated_search(
                    page=page,
                    throttle=self._throttle,
                    fetch_one_page=self._make_fetch_one_page(keywords, location),
                    limit=limit,
                    max_pages=self._settings.max_pages,
                    inter_page_delay_seconds=self._settings.inter_page_delay_seconds,
                    timeout_exc_type=IndeedTimeoutError,
                )
            finally:
                await page.close()
        finally:
            await ctx.close()

    def _make_fetch_one_page(
        self, keywords: str, location: str
    ) -> Callable[[Any, int, int], Awaitable[list[Job]]]:
        """Build a per-page closure that captures Indeed-specific concerns.

        The closure passed to `paginated_search` is called once per
        page with `(page, page_index, remaining)`. It navigates the
        page, checks for Cloudflare blocks, parses the cards via the
        3-arg `_parse_cards(soup, remaining, domain)`, and raises
        `IndeedParseError` on page 0 when zero cards are returned.

        All Indeed-specific behavior that the canonical loop helper
        must NOT know about lives here:
            - URL formula: `start=page_index * 10` (Indeed serves
              ~10 jobs per page; page 0 starts at offset 0).
            - `is_indeed_blocked(soup)` check after `wait_for_selector`
              (Cloudflare / anti-bot challenge).
            - `_parse_cards(soup, remaining, domain)` 3-arg shape
              (LinkedIn's parser is 2-arg; InfoJobs shares the 3-arg
              shape but with a different URL formula + selector).
            - `IndeedParseError("zero_cards_on_first_page")` on
              page 0 with no cards (LinkedIn silently breaks instead;
              InfoJobs shares this raise semantic).
        """
        domain = self._settings.domain

        async def fetch_one_page(page: Any, page_index: int, remaining: int) -> list[Job]:
            url = self._build_url(keywords, location, page_index * 10)
            await self._navigate_and_wait(page, url)
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            if is_indeed_blocked(soup):
                raise IndeedBlockedError(
                    "Indeed returned a Cloudflare challenge page",
                    details={"url": url},
                )
            new_jobs = _parse_cards(soup, remaining, domain)
            if page_index == 0 and not new_jobs:
                raise IndeedParseError(
                    "scraper: zero cards on first page",
                    details={"reason": "zero_cards_on_first_page"},
                )
            return new_jobs

        return fetch_one_page

    def _build_url(self, keywords: str, location: str, start: int) -> str:
        return (
            f"https://{self._settings.domain}/jobs"
            f"?q={quote(keywords)}&l={quote(location)}&start={start}"
        )

    async def _navigate_and_wait(self, page: Any, url: str) -> None:
        try:
            await page.goto(url)
            await page.wait_for_selector(RESULTS_SELECTOR, timeout=self._settings.timeout_ms)
        except PlaywrightTimeoutError as e:
            raise IndeedTimeoutError(
                "scraper: timeout waiting for results",
                details={
                    "url": url,
                    "timeout_ms": self._settings.timeout_ms,
                },
            ) from e
        except PlaywrightError as e:
            raise IndeedBlockedError(
                "scraper: playwright error during navigation",
                details={"url": url, "cause": str(e)},
            ) from e


def _parse_cards(soup: BeautifulSoup, remaining: int, domain: str) -> list[Job]:
    """Build `Job` objects from the cards in the parsed page, capped at `remaining`.

    When a card's `posted_at` is missing or unparseable, the scraper
    falls back to `datetime.now(UTC)` (the scrape time) so we never
    return a `Job` with a missing field — `Job.posted_at` is currently
    required by the domain object. The same defensive pattern is used
    in the LinkedIn scraper.

    A card that fails to parse any other field raises `IndeedParseError`
    with the card snippet in `details`; one bad card aborts the whole
    response (we never return a silent partial list).
    """
    cards = soup.select(RESULTS_SELECTOR)
    jobs: list[Job] = []
    for card in cards[:remaining]:
        try:
            posted = parse_indeed_posted_at(card)
            job = Job(
                id=parse_indeed_job_id(card),
                title=parse_indeed_title(card),
                company=parse_indeed_company(card),
                location=parse_indeed_location(card),
                url=parse_indeed_url(card, domain=domain),
                posted_at=posted if posted is not None else datetime.now(UTC),
            )
            jobs.append(job)
        except IndeedParseError as e:
            raise IndeedParseError(
                "scraper: failed to build Job from card",
                details={"card_html": str(card)[:200], "cause": str(e)},
            ) from e
    return jobs
