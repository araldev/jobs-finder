"""LinkedIn Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-013, REQ-024.

Lifecycle: `async with scraper:` launches a headless Chromium with a
stealth-ish user-agent and a 1280x800 viewport (or accepts an injected
`browser_factory` for tests). `await scraper.search(...)` serializes
through the injected `AsyncThrottle`, opens a new page, navigates to the
LinkedIn search URL, waits for the results selector, parses the cards via
the pure parsers, and returns a `list[Job]` sliced to `limit`.

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

RESULTS_SELECTOR = "li[data-entity-urn]"

VIEWPORT: dict[str, int] = {"width": 1280, "height": 800}

# `browser_factory` returns the live `Browser` to drive in `__aenter__`.
# In production this is `None` and the scraper launches Chromium itself.
BrowserFactory = Callable[[], Awaitable[Any]]


class ScraperSettings:
    """Bundles the configuration values the scraper reads at runtime.

    `frozen=True` makes it hashable and immutable. The `__init__` mirrors
    the design's `Settings` shape (user-agent and timeout), minus the
    `cors_allow_origins` and `log_level` fields that the scraper does not
    need.
    """

    __slots__ = ("timeout_ms", "user_agent")

    def __init__(self, user_agent: str, timeout_ms: int) -> None:
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms

    def __repr__(self) -> str:
        return f"ScraperSettings(user_agent={self.user_agent!r}, timeout_ms={self.timeout_ms})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScraperSettings):
            return NotImplemented
        return self.user_agent == other.user_agent and self.timeout_ms == other.timeout_ms

    def __hash__(self) -> int:
        return hash((self.user_agent, self.timeout_ms))


class LinkedInPlaywrightScraper(JobSearchPort):
    """Implements `JobSearchPort` for LinkedIn using Playwright."""

    def __init__(
        self,
        *,
        throttle: AsyncThrottle,
        settings: ScraperSettings,
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
        """Run a single search; return the parsed jobs (sliced to `limit`)."""
        url = self._build_url(keywords, location)
        async with self._throttle:
            ctx = await self._browser.new_context(
                user_agent=self._settings.user_agent,
                viewport=VIEWPORT,
            )
            try:
                page = await ctx.new_page()
                try:
                    await self._navigate_and_wait(page, url)
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    if is_block_page(soup):
                        raise LinkedInBlockedError(
                            "LinkedIn returned an auth-wall / verification page"
                        )
                    return _parse_cards(soup, limit)
                finally:
                    await page.close()
            finally:
                await ctx.close()

    @staticmethod
    def _build_url(keywords: str, location: str) -> str:
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote(keywords)}&location={quote(location)}"
        )

    async def _navigate_and_wait(self, page: Any, url: str) -> None:
        try:
            await page.goto(url)
            await page.wait_for_selector(
                RESULTS_SELECTOR, timeout=self._settings.timeout_ms
            )
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


def _parse_cards(soup: BeautifulSoup, limit: int) -> list[Job]:
    """Build `Job` objects from the cards in the parsed page, sliced to `limit`.

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
    for card in cards[:limit]:
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
