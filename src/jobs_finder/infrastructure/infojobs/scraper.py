"""InfoJobs Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-J-001, REQ-J-002, REQ-J-003, REQ-J-006.

Lifecycle: `async with scraper:` launches a headless Chromium with a
configurable user-agent (or accepts an injected `browser_factory` for
tests). `await scraper.search(...)` serializes through the injected
`InfoJobsAsyncThrottle`, opens a new context + page, navigates to the
InfoJobs search URL with `&page=1`, waits for the results selector,
parses the cards via the pure parsers, and returns a `list[Job]`
sliced to `limit`.

Auto-pagination (REQ-J-006): after the first page is parsed, the
scraper navigates to `&page=2`, then `&page=3`, ..., up to
`settings.max_pages` total requests. The loop terminates early when
the requested `limit` is reached OR when a page yields zero new cards
OR when a `wait_for_selector` timeout occurs on page > 0 (end of
results / anti-bot re-challenge — break gracefully). A timeout on
page 0 is a real error and raises `InfoJobsTimeoutError`.

Inter-page pacing (REQ-J-003): before each page request with
`page_index > 0`, the scraper awaits `asyncio.sleep` for
`settings.inter_page_delay_seconds` seconds. The check `> 0` skips
the call entirely when the delay is `0.0` (no needless event-loop
yield, no wall-clock wait). The first page is never delayed.

Stealth (REQ-J-002): when the constructor receives a `Stealth()`
instance, `apply_stealth_async` is called on the context AFTER
`new_context` and BEFORE `new_page` (per `playwright_stealth` docs:
"Apply Stealth to Playwright Contexts"). Production wires
`Stealth()` in `app_factory.build_app()` (T-008); tests pass
`stealth=None` (the default).

Errors:
- `playwright.async_api.TimeoutError` from `wait_for_selector` on
  page 0 -> `InfoJobsTimeoutError` (the results selector never
  appeared).
- `playwright.async_api.TimeoutError` from `wait_for_selector` on
  page > 0 -> break gracefully (REQ-J-006), return what we have.
- `is_infojobs_blocked(content)` is True after the page is loaded ->
  `InfoJobsBlockedError` (Distil / Geetest challenge page).
- Zero cards on the first page ->
  `InfoJobsParseError(details={"reason": "zero_cards_on_first_page"})`.
- Any other `PlaywrightError` during navigation -> `InfoJobsBlockedError`.
- A card that fails to parse -> `InfoJobsParseError` (one bad card
  aborts the whole response; we never return a silent partial list).
"""

from __future__ import annotations

import asyncio
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

from .exceptions import InfoJobsBlockedError, InfoJobsParseError, InfoJobsTimeoutError
from .parsers import (
    is_infojobs_blocked,
    parse_infojobs_company,
    parse_infojobs_job_id,
    parse_infojobs_location,
    parse_infojobs_posted_at,
    parse_infojobs_title,
    parse_infojobs_url,
)
from .throttle import InfoJobsAsyncThrottle

# The CSS selector for a single search-results card on the InfoJobs SERP.
# Used both as the `wait_for_selector` target AND by the parsers via the
# private module constant in `parsers.py` (kept in sync). If InfoJobs
# changes the card class name in the future, both this line and the
# one in `parsers.py` need to change.
#
# The selector requires the offer-title heading (`:has(h2...)`) to
# disambiguate real offer cards from promoted ad banners, which
# also carry the `ij-OfferList-offerCardItem` class but do NOT
# have a title heading. The same filter is applied in `parsers.py`
# and in the test suite — all three stay in sync.
RESULTS_SELECTOR = ".ij-OfferList-offerCardItem:has(h2.ij-OfferCardContent-description-title)"

# `browser_factory` returns the live `Browser` to drive in `__aenter__`.
# In production this is `None` and the scraper launches Chromium itself.
# In tests the factory injects a fake `Browser` so the suite never
# launches a browser and never contacts InfoJobs.
BrowserFactory = Callable[[], Awaitable[Any]]


class InfoJobsScraperSettings:
    """Bundles the configuration values the InfoJobs scraper reads at runtime.

    Mirrors `IndeedScraperSettings` (1:1) with the InfoJobs defaults
    (`www.infojobs.net` as `domain`). Slots-based + manual `__eq__` /
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
        domain: str = "www.infojobs.net",
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
            f"InfoJobsScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, domain={self.domain!r}, "
            f"max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InfoJobsScraperSettings):
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


class InfoJobsPlaywrightScraper(JobSearchPort):
    """Implements `JobSearchPort` for InfoJobs using Playwright."""

    def __init__(
        self,
        *,
        throttle: InfoJobsAsyncThrottle,
        settings: InfoJobsScraperSettings,
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
                Chromium evades Distil / Geetest's bot detection.
                When `None` (the default, used in tests), no stealth
                is applied. Production wires `Stealth()` in the
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

        The throttle is acquired ONCE per `search()` (around the whole
        loop) so consecutive `search()` calls are paced by
        `min_interval_seconds`, while the page requests within a single
        search happen back-to-back (one HTTP call per page). Per-page
        pacing is then applied INSIDE the loop via
        `await asyncio.sleep(inter_page_delay_seconds)` BEFORE pages
        1, 2, 3, ... (page 0 is never delayed) — this is REQ-J-003.
        The `> 0` check skips the call entirely when the delay is
        `0.0` (no event-loop yield, no wall-clock wait).

        REQ-J-006: a `wait_for_selector` timeout on page > 0 breaks
        the loop gracefully and returns the first page's results. A
        timeout on page 0 raises `InfoJobsTimeoutError`.
        """
        jobs: list[Job] = []
        async with self._throttle:
            ctx = await self._browser.new_context(user_agent=self._settings.user_agent)
            # Stealth MUST be applied AFTER `new_context` (per
            # `playwright_stealth` docs: "Apply Stealth to Playwright
            # Contexts") and BEFORE `new_page` so the page that follows
            # inherits the patched navigator/UA. The check is
            # opt-in: `stealth=None` (the test default) skips the call
            # entirely, so unit tests never reach the real script.
            if self._stealth is not None:
                await self._stealth.apply_stealth_async(ctx)
            try:
                page = await ctx.new_page()
                try:
                    for page_index in range(self._settings.max_pages):
                        if len(jobs) >= limit:
                            break
                        # Inter-page pacing (REQ-J-003): sleep before
                        # navigating to the NEXT page to reduce the
                        # probability of Distil/Geetest re-challenges
                        # on the 2nd+ request. The first page
                        # (page_index=0) is never delayed. A delay of
                        # `0.0` skips the call entirely (no event-loop
                        # yield, no wall-clock wait). The default
                        # `Settings.infojobs_inter_page_delay_seconds = 1.5`
                        # is sourced from env; tests pass `0.0` to disable.
                        if page_index > 0 and self._settings.inter_page_delay_seconds > 0:
                            await asyncio.sleep(self._settings.inter_page_delay_seconds)
                        # InfoJobs uses 1-indexed pagination: page 1
                        # is the first page of results, page 2 is the
                        # second, etc. The internal loop is
                        # 0-indexed, so we add 1 to translate.
                        url = self._build_url(keywords, location, page_index + 1)
                        try:
                            await self._navigate_and_wait(page, url)
                        except InfoJobsTimeoutError:
                            if page_index == 0:
                                # First page timing out is a real error
                                # (Distil block, zero results, etc.).
                                raise
                            # Subsequent page timed out: end of results
                            # or anti-bot re-challenge. Return what we
                            # have rather than failing the whole search.
                            # The 15-card first page is enough for the
                            # vast majority of queries; ~limit requests
                            # never reach a real page 2 anyway.
                            break
                        content = await page.content()
                        soup = BeautifulSoup(content, "html.parser")
                        if is_infojobs_blocked(soup):
                            raise InfoJobsBlockedError(
                                "InfoJobs returned a Distil / Geetest challenge page",
                                details={"url": url},
                            )
                        remaining = limit - len(jobs)
                        new_jobs = _parse_cards(soup, remaining, self._settings.domain)
                        if page_index == 0 and not new_jobs:
                            raise InfoJobsParseError(
                                "scraper: zero cards on first page",
                                details={"reason": "zero_cards_on_first_page"},
                            )
                        jobs.extend(new_jobs)
                        if not new_jobs:
                            break
                finally:
                    await page.close()
            finally:
                await ctx.close()
        return jobs

    def _build_url(self, keywords: str, location: str, page: int) -> str:
        return (
            f"https://{self._settings.domain}/ofertas-trabajo"
            f"?q={quote(keywords)}&l={quote(location)}&page={page}"
        )

    async def _navigate_and_wait(self, page: Any, url: str) -> None:
        try:
            await page.goto(url)
            await page.wait_for_selector(RESULTS_SELECTOR, timeout=self._settings.timeout_ms)
        except PlaywrightTimeoutError as e:
            raise InfoJobsTimeoutError(
                "scraper: timeout waiting for results",
                details={
                    "url": url,
                    "timeout_ms": self._settings.timeout_ms,
                },
            ) from e
        except PlaywrightError as e:
            raise InfoJobsBlockedError(
                "scraper: playwright error during navigation",
                details={"url": url, "cause": str(e)},
            ) from e


def _parse_cards(soup: BeautifulSoup, remaining: int, domain: str) -> list[Job]:
    """Build `Job` objects from the cards in the parsed page, capped at `remaining`.

    When a card's `posted_at` is missing or unparseable, the scraper
    falls back to `datetime.now(UTC)` (the scrape time) so we never
    return a `Job` with a missing field — `Job.posted_at` is
    required by the domain object. The same defensive pattern is used
    in the LinkedIn and Indeed scrapers.

    A card that fails to parse any other field raises
    `InfoJobsParseError` with the card snippet in `details`; one bad
    card aborts the whole response (we never return a silent partial
    list).
    """
    cards = soup.select(RESULTS_SELECTOR)
    jobs: list[Job] = []
    for card in cards[:remaining]:
        try:
            posted = parse_infojobs_posted_at(card)
            job = Job(
                id=parse_infojobs_job_id(card),
                title=parse_infojobs_title(card),
                company=parse_infojobs_company(card),
                location=parse_infojobs_location(card),
                url=parse_infojobs_url(card, domain=domain),
                posted_at=posted if posted is not None else datetime.now(UTC),
            )
            jobs.append(job)
        except InfoJobsParseError as e:
            raise InfoJobsParseError(
                "scraper: failed to build Job from card",
                details={"card_html": str(card)[:200], "cause": str(e)},
            ) from e
    return jobs
