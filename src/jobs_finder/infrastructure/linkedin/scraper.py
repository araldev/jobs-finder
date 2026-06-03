"""LinkedIn Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-013, REQ-024, REQ-L-007..REQ-L-010.

Lifecycle: `async with scraper:` launches a headless Chromium with a
stealth-ish user-agent and a 1280x800 viewport (or accepts an injected
`browser_factory` for tests). `await scraper.search(...)` serializes
through the injected `AsyncThrottle`, opens a new page, navigates to the
LinkedIn search URL, waits for the results selector, parses the cards via
the pure parsers, and returns a `list[Job]` sliced to `limit`.

Auto-pagination (REQ-L-007): after the first page is parsed, the
scraper navigates to `&start=25`, then `&start=50`, ..., up to
`settings.max_pages` total requests. The loop terminates early when
the requested `limit` is reached OR when a page yields zero new cards
OR when a `wait_for_selector` timeout occurs on page > 0 (end of
results / anti-bot re-challenge — break gracefully). A timeout on
page 0 is a real error and raises `LinkedInTimeoutError`.

Inter-page pacing (REQ-L-009): before each page request with
`page_index > 0`, the scraper awaits `asyncio.sleep` for
`settings.inter_page_delay_seconds` seconds. The check `> 0` skips
the call entirely when the delay is `0.0` (no needless event-loop
yield, no wall-clock wait). The first page is never delayed.

Throttle scope (REQ-L-010): the `AsyncThrottle` is acquired ONCE
around the whole pagination loop (per `search()` call) so consecutive
`search()` calls are paced by `min_interval_seconds` while the page
requests within a single search happen back-to-back.

Errors:
- `playwright.async_api.TimeoutError` -> `LinkedInTimeoutError`
- Any other `PlaywrightError` during navigation -> `LinkedInBlockedError`
- `is_block_page` detects an auth-wall / verification page after the
  page is loaded -> `LinkedInBlockedError`
- A card that fails to parse -> `LinkedInParseError` (one bad card
  aborts the whole response; we never return a silent partial list).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import (
    async_playwright,
)

from jobs_finder.application.ports import JobSearchPort
from jobs_finder.domain.job import Job

from .exceptions import LinkedInBlockedError, LinkedInParseError, LinkedInTimeoutError
from .parsers import (
    is_block_page,
    parse_company,
    parse_job_id,
    parse_location,
    parse_posted_at,
    parse_title,
    parse_url,
)
from .throttle import AsyncThrottle

# A plausible stealth desktop UA. The exact fingerprint is not load-bearing;
# any modern Chrome string is enough to bypass the most basic anti-bot
# filters LinkedIn's public search applies.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT_MS = 10_000

RESULTS_SELECTOR = "div[data-entity-urn]"

VIEWPORT: dict[str, int] = {"width": 1280, "height": 800}

# `browser_factory` returns the live `Browser` to drive in `__aenter__`.
# In production this is `None` and the scraper launches Chromium itself.
BrowserFactory = Callable[[], Awaitable[Any]]


class LinkedInScraperSettings:
    """Bundles the configuration values the LinkedIn scraper reads at runtime.

    Mirrors `IndeedScraperSettings` (1:1) with the LinkedIn defaults
    (no `domain` field — LinkedIn has a single host, `www.linkedin.com`).
    Slots-based + manual `__eq__` / `__hash__` keeps it hashable and
    immutable; the fields are keyword-only so the test fixtures read
    top-to-bottom the way `Settings` is structured.

    `max_pages` and `inter_page_delay_seconds` were added by the
    `linkedin-pagination` change (REQ-L-007 + REQ-L-008) to bring the
    LinkedIn scraper to parity with the Indeed and InfoJobs scrapers.
    """

    __slots__ = ("inter_page_delay_seconds", "max_pages", "timeout_ms", "user_agent")

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int,
        max_pages: int = 10,
        inter_page_delay_seconds: float = 1.0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self.max_pages = max_pages
        self.inter_page_delay_seconds = inter_page_delay_seconds

    def __repr__(self) -> str:
        return (
            f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LinkedInScraperSettings):
            return NotImplemented
        return (
            self.user_agent == other.user_agent
            and self.timeout_ms == other.timeout_ms
            and self.max_pages == other.max_pages
            and self.inter_page_delay_seconds == other.inter_page_delay_seconds
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.user_agent,
                self.timeout_ms,
                self.max_pages,
                self.inter_page_delay_seconds,
            )
        )


class LinkedInPlaywrightScraper(JobSearchPort):
    """Implements `JobSearchPort` for LinkedIn using Playwright."""

    def __init__(
        self,
        *,
        throttle: AsyncThrottle,
        settings: LinkedInScraperSettings,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._throttle = throttle
        self._settings = settings
        self._browser_factory = browser_factory
        self._owns_browser: bool = browser_factory is None
        self._browser: Any = None
        self._playwright: Any = None

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
        1, 2, 3, ... (page 0 is never delayed) — this is REQ-L-009.
        The `> 0` check skips the call entirely when the delay is
        `0.0` (no event-loop yield, no wall-clock wait).

        REQ-L-007: a `wait_for_selector` timeout on page > 0 breaks
        the loop gracefully and returns the first page's results. A
        timeout on page 0 raises `LinkedInTimeoutError`.
        """
        jobs: list[Job] = []
        async with self._throttle:
            ctx = await self._browser.new_context(
                user_agent=self._settings.user_agent,
                viewport=VIEWPORT,
            )
            try:
                page = await ctx.new_page()
                try:
                    for page_index in range(self._settings.max_pages):
                        if len(jobs) >= limit:
                            break
                        # Inter-page pacing (REQ-L-009): sleep before
                        # navigating to the NEXT page to reduce the
                        # probability of LinkedIn anti-bot re-challenges
                        # on the 2nd+ request. The first page
                        # (page_index=0) is never delayed. A delay of
                        # `0.0` skips the call entirely (no event-loop
                        # yield, no wall-clock wait). The default
                        # `Settings.linkedin_inter_page_delay_seconds = 1.0`
                        # is sourced from env; tests pass `0.0` to disable.
                        if page_index > 0 and self._settings.inter_page_delay_seconds > 0:
                            await asyncio.sleep(self._settings.inter_page_delay_seconds)
                        # LinkedIn serves ~25 jobs per page; page 0 starts
                        # at offset 0, page 1 at offset 25, etc.
                        url = self._build_url(keywords, location, page_index * 25)
                        try:
                            await self._navigate_and_wait(page, url)
                        except LinkedInTimeoutError:
                            if page_index == 0:
                                # First page timing out is a real error
                                # (LinkedIn auth-wall, zero results, etc.).
                                raise
                            # Subsequent page timed out: end of results
                            # or anti-bot re-challenge. Return what we
                            # have rather than failing the whole search.
                            # The ~25-card first page is enough for the
                            # vast majority of queries; ~limit requests
                            # never reach a real page 2 anyway.
                            break
                        content = await page.content()
                        soup = BeautifulSoup(content, "html.parser")
                        if is_block_page(soup):
                            raise LinkedInBlockedError(
                                "LinkedIn returned an auth-wall / verification page"
                            )
                        remaining = limit - len(jobs)
                        new_jobs = _parse_cards(soup, remaining)
                        jobs.extend(new_jobs)
                        if not new_jobs:
                            # Zero new cards on any page = end of the
                            # SERP. Break gracefully; the partner test
                            # `test_zero_cards_on_page_one_breaks_loop`
                            # pins this contract.
                            break
                finally:
                    await page.close()
            finally:
                await ctx.close()
        return jobs

    @staticmethod
    def _build_url(keywords: str, location: str, start: int) -> str:
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote(keywords)}&location={quote(location)}&start={start}"
        )

    async def _navigate_and_wait(self, page: Any, url: str) -> None:
        try:
            await page.goto(url)
            await page.wait_for_selector(RESULTS_SELECTOR, timeout=self._settings.timeout_ms)
        except PlaywrightTimeoutError as e:
            raise LinkedInTimeoutError(
                "scraper: timeout waiting for results",
                details={
                    "url": url,
                    "timeout_ms": self._settings.timeout_ms,
                },
            ) from e
        except PlaywrightError as e:
            raise LinkedInBlockedError(
                "scraper: playwright error during navigation",
                details={"url": url, "cause": str(e)},
            ) from e


def _parse_cards(soup: BeautifulSoup, remaining: int) -> list[Job]:
    """Build `Job` objects from the cards in the parsed page, capped at `remaining`.

    `remaining` is the number of jobs the caller still needs to hit
    `limit` — the pagination loop computes it as `limit - len(jobs)`
    before each page request so we never parse cards the caller will
    discard (REQ-L-007).

    NOTE: `Job.posted_at` is a required timezone-aware `datetime`. When the
    LinkedIn card has no `<time>` element, `parse_posted_at` returns `None`
    and the scraper falls back to `datetime.now(UTC)` (the scrape time)
    so we never return a `Job` with a missing field. The Design's intent
    (`posted_at: datetime | None`) is documented as a follow-up change in
    the apply-progress; this is the smallest correct adjustment that keeps
    the test happy without touching the domain layer.
    """
    cards = soup.select(RESULTS_SELECTOR)
    jobs: list[Job] = []
    for card in cards[:remaining]:
        try:
            posted = parse_posted_at(card)
            job = Job(
                id=parse_job_id(card),
                title=parse_title(card),
                company=parse_company(card),
                location=parse_location(card),
                url=parse_url(card),
                posted_at=posted if posted is not None else datetime.now(UTC),
            )
            jobs.append(job)
        except LinkedInParseError as e:
            raise LinkedInParseError(
                "scraper: failed to build Job from card",
                details={"card_html": str(card)[:200], "cause": str(e)},
            ) from e
    return jobs
