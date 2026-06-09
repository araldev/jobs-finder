"""LinkedIn Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-013, REQ-024, REQ-L-007..REQ-L-010, REQ-PAG-001..PAG-003.

Lifecycle: `async with scraper:` launches a headless Chromium with a
stealth-ish user-agent and a 1280x800 viewport (or accepts an injected
`browser_factory` for tests). `await scraper.search(...)` serializes
through the injected `AsyncThrottle`, opens a new page, navigates to the
LinkedIn search URL, waits for the results selector, parses the cards via
the pure parsers, and returns a `list[Job]` sliced to `limit`.

Auto-pagination (REQ-L-007, REQ-PAG-001..PAG-003): the loop is owned
by the canonical `paginated_search` helper at
`jobs_finder.infrastructure.pagination`. The scraper contributes a
`_make_fetch_one_page(keywords, location)` closure that captures
LinkedIn's URL formula (`start=page_index*25`), `is_block_page`
check, the 2-arg `_parse_cards(soup, remaining)` (no `domain`),
and LinkedIn's silent-break semantic on page-0 zero-cards (the
closure does NOT raise a `LinkedInParseError`; the helper's
zero-cards break handles it). The loop terminates early when the
requested `limit` is reached OR when a page yields zero new cards
OR when a per-page `wait_for_selector` timeout occurs on page > 0
(end of results / anti-bot re-challenge — break gracefully). A
timeout on page 0 is a real error and propagates as
`LinkedInTimeoutError`.

Inter-page pacing (REQ-L-009, REQ-PAG-002): the helper awaits
`asyncio.sleep(inter_page_delay_seconds)` BEFORE the next page
request; page 0 is never delayed. The `> 0` guard skips the call
entirely when the delay is `0.0` (no needless event-loop yield, no
wall-clock wait). The default
`Settings.linkedin_inter_page_delay_seconds = 1.0` is sourced
from env; tests pass `0.0` to disable.

Throttle scope (REQ-L-010, REQ-PAG-002): the `AsyncThrottle` is
acquired ONCE around the whole pagination loop (per `search()`
call) by the helper so consecutive `search()` calls are paced by
`min_interval_seconds` while the page requests within a single
search happen back-to-back.

Errors:
- `playwright.async_api.TimeoutError` -> `LinkedInTimeoutError`
- Any other `PlaywrightError` during navigation -> `LinkedInBlockedError`
- `is_block_page` detects an auth-wall / verification page after the
  page is loaded -> `LinkedInBlockedError`
- A card that fails to parse -> `LinkedInParseError` (one bad card
  aborts the whole response; we never return a silent partial list).
"""

from __future__ import annotations

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

from jobs_finder.application.ports import JobSearchPort, LocationResolverPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.pagination import paginated_search

from .exceptions import LinkedInBlockedError, LinkedInParseError, LinkedInTimeoutError
from .parsers import (
    is_block_page,
    parse_company,
    parse_description,
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

    __slots__ = (
        "inter_page_delay_seconds",
        "location_resolver",
        "max_pages",
        "timeout_ms",
        "user_agent",
    )

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int,
        max_pages: int = 10,
        inter_page_delay_seconds: float = 1.0,
        location_resolver: LocationResolverPort | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self.max_pages = max_pages
        self.inter_page_delay_seconds = inter_page_delay_seconds
        # Optional `LocationResolverPort` (added in
        # `backend-scraper-query-tuning`, REQ-LOC-002). When
        # `None` (the default), the scraper falls back to
        # `?location=<str>` for every `search()` call (the
        # legacy v1 broken-but-doesn't-500 path). When set, the
        # scraper calls `resolve(location)` ONCE per `search()`
        # and uses the returned `geoId` in the URL formula.
        self.location_resolver = location_resolver

    def __repr__(self) -> str:
        return (
            f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
            f"location_resolver={self.location_resolver!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LinkedInScraperSettings):
            return NotImplemented
        return (
            self.user_agent == other.user_agent
            and self.timeout_ms == other.timeout_ms
            and self.max_pages == other.max_pages
            and self.inter_page_delay_seconds == other.inter_page_delay_seconds
            and self.location_resolver == other.location_resolver
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.user_agent,
                self.timeout_ms,
                self.max_pages,
                self.inter_page_delay_seconds,
                self.location_resolver,
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

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        """Run a single search; paginate until `limit` is reached or `max_pages` exhausted.

        The pagination loop is owned by `paginated_search`
        (REQ-PAG-001..PAG-003). This method is the composition seam:
        it opens a fresh context + page (with the LinkedIn-specific
        `VIEWPORT` constant), then hands control to the helper with
        a LinkedIn-specific `_make_fetch_one_page` closure. The
        helper acquires the throttle (REQ-L-010 / REQ-PAG-002) ONCE
        around the whole loop and owns the limit / max_pages /
        inter-page-delay / timeout / zero-cards control flow.

        Per-page pacing (REQ-L-009) is applied INSIDE the helper:
        `await asyncio.sleep(inter_page_delay_seconds)` BEFORE
        pages 1, 2, 3, ... (page 0 is never delayed). The `> 0`
        check skips the call entirely when the delay is `0.0` (no
        event-loop yield, no wall-clock wait).

        REQ-L-007: a `wait_for_selector` timeout on page > 0
        breaks the loop gracefully and returns the first page's
        results. A timeout on page 0 raises `LinkedInTimeoutError`.

        `geo_id` resolution (REQ-LOC-001, T-001 of
        `backend-scraper-query-tuning`): when the caller does
        NOT pass `geo_id` (the default, used by the
        `LinkedInScraperSettings`-only path), the scraper
        calls `self._settings.location_resolver.resolve(location)`
        ONCE per `search()` and uses the returned int as the
        `geoId` URL parameter. The resolver is called AT MOST
        once per `search()` (not per page); the result is
        captured in the closure.
        """
        if geo_id is None and self._settings.location_resolver is not None:
            geo_id = self._settings.location_resolver.resolve(location)
        ctx = await self._browser.new_context(
            user_agent=self._settings.user_agent,
            viewport=VIEWPORT,
        )
        try:
            page = await ctx.new_page()
            try:
                return await paginated_search(
                    page=page,
                    throttle=self._throttle,
                    fetch_one_page=self._make_fetch_one_page(keywords, location, geo_id=geo_id),
                    limit=limit,
                    max_pages=self._settings.max_pages,
                    inter_page_delay_seconds=self._settings.inter_page_delay_seconds,
                    timeout_exc_type=LinkedInTimeoutError,
                )
            finally:
                await page.close()
        finally:
            await ctx.close()

    def _make_fetch_one_page(
        self,
        keywords: str,
        location: str,
        geo_id: int | None = None,
    ) -> Callable[[Any, int, int], Awaitable[list[Job]]]:
        """Build a per-page closure that captures LinkedIn-specific concerns.

        The closure passed to `paginated_search` is called once per
        page with `(page, page_index, remaining)`. It navigates the
        page, checks for an auth-wall / verification page, parses
        the cards via the 2-arg `_parse_cards(soup, remaining)`,
        and returns the per-page job list. It does NOT raise on
        page-0 zero-cards (LinkedIn's current contract is "break
        silently" per REQ-L-007; the helper's zero-cards break
        handles it).

        All LinkedIn-specific behavior that the canonical loop
        helper must NOT know about lives here:
            - URL formula: `start=page_index * 25` (LinkedIn serves
              ~25 jobs per page; page 0 starts at offset 0). When
              `geo_id is not None`, the URL uses `geoId=<n>` (NOT
              `location=`) — the `REQ-LOC-GEO-001` correction.
            - `is_block_page(soup)` check after `wait_for_selector`
              (LinkedIn auth-wall / verification page).
            - `_parse_cards(soup, remaining)` 2-arg shape (no
              `domain` arg — Indeed/InfoJobs are 3-arg).
            - NO page-0 zero-cards raise: the closure returns
              `[]` and the helper's zero-cards break returns
              `[]` to the caller. (Indeed/InfoJobs closures DO
              raise a `*ParseError` in this case.)
        """

        async def fetch_one_page(page: Any, page_index: int, remaining: int) -> list[Job]:
            url = self._build_url(keywords, location, page_index * 25, geo_id=geo_id)
            await self._navigate_and_wait(page, url)
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            if is_block_page(soup):
                raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
            return _parse_cards(soup, remaining)

        return fetch_one_page

    @staticmethod
    def _build_url(keywords: str, location: str, start: int, geo_id: int | None = None) -> str:
        """Build the LinkedIn search URL with the corrected `geoId=` formula.

        The LinkedIn-correct path (`REQ-LOC-GEO-001`):
        when `geo_id is not None`, the URL is
        `?keywords=...&geoId=<n>&start=...` (the resolver
        consumed the `location` string and the captured
        `geoId` replaced it). The fallback (`geo_id is None`)
        emits `?keywords=...&location=<str>&start=...` — the
        pre-`fix-linkedin-geoid` broken path (LinkedIn
        silently ignores the `location=` string param, but
        does not 500). The fallback is a strict improvement
        over today's 100%-broken behavior: identical
        behavior for unknown locations, correct behavior
        for known cities.

        Args:
            keywords: The user's `keywords` (URL-quoted via
                `urllib.parse.quote`).
            location: The user's free-form `location` string.
                Used only when `geo_id is None` (the fallback
                path).
            start: The per-page `start=page_index * 25` offset.
            geo_id: The captured LinkedIn `geoId` (e.g.
                `103374081` for Madrid). When `not None`,
                the URL uses `geoId=` (NOT `location=`). When
                `None`, the URL falls back to `location=`.

        Returns:
            The full LinkedIn search URL.
        """
        if geo_id is not None:
            return (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={quote(keywords)}&geoId={geo_id}&start={start}"
            )
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
                description=parse_description(card),
            )
            jobs.append(job)
        except LinkedInParseError as e:
            raise LinkedInParseError(
                "scraper: failed to build Job from card",
                details={"card_html": str(card)[:200], "cause": str(e)},
            ) from e
    return jobs
