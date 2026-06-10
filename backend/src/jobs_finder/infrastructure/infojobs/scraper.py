"""InfoJobs Playwright scraper — the live adapter behind `JobSearchPort`.

Spec: REQ-J-001, REQ-J-002, REQ-J-003, REQ-J-006, REQ-PAG-001..PAG-003.

Lifecycle: `async with scraper:` launches a headless Chromium with a
configurable user-agent (or accepts an injected `browser_factory` for
tests). `await scraper.search(...)` serializes through the injected
`InfoJobsAsyncThrottle`, opens a new context + page, navigates to the
InfoJobs search URL with `&page=1`, waits for the results selector,
parses the cards via the pure parsers, and returns a `list[Job]`
sliced to `limit`.

Auto-pagination (REQ-J-006, REQ-PAG-001..PAG-003): the loop is owned
by the canonical `paginated_search` helper at
`jobs_finder.infrastructure.pagination`. The scraper contributes a
`_make_fetch_one_page(keywords, location)` closure that captures
InfoJobs's URL formula (`page=page_index+1`, 1-indexed),
`is_infojobs_blocked` check, the 3-arg `_parse_cards(soup,
remaining, domain)`, and the page-0 zero-cards
`InfoJobsParseError` semantic. The loop terminates early when the
requested `limit` is reached OR when a page yields zero new cards
OR when a per-page `wait_for_selector` timeout occurs on page > 0
(end of results / anti-bot re-challenge — break gracefully). A
timeout on page 0 is a real error and propagates as
`InfoJobsTimeoutError`.

Inter-page pacing (REQ-J-003, REQ-PAG-002): the helper awaits
`asyncio.sleep(inter_page_delay_seconds)` BEFORE the next page
request; page 0 is never delayed. The `> 0` guard skips the call
entirely when the delay is `0.0` (no needless event-loop yield, no
wall-clock wait).

Stealth (REQ-J-002): when the constructor receives a `Stealth()`
instance, `apply_stealth_async` is called on the context AFTER
`new_context` and BEFORE `new_page` (per `playwright_stealth` docs:
"Apply Stealth to Playwright Contexts"). Production wires
`Stealth()` in `app_factory.build_app()`; tests pass
`stealth=None` (the default).

Throttle (REQ-J-005, REQ-PAG-002): the `InfoJobsAsyncThrottle` is
acquired ONCE around the whole pagination loop (per `search()`
call) by the helper so consecutive `search()` calls are paced by
`min_interval_seconds` while the page requests within a single
search happen back-to-back.

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

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.application.ports import JobSearchPort, LocationResolverPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.pagination import paginated_search

from .exceptions import InfoJobsBlockedError, InfoJobsParseError, InfoJobsTimeoutError
from .parsers import (
    is_infojobs_blocked,
    parse_infojobs_company,
    parse_infojobs_description,
    parse_infojobs_job_id,
    parse_infojobs_location,
    parse_infojobs_posted_at,
    parse_infojobs_title,
    parse_infojobs_url,
)
from .throttle import InfoJobsAsyncThrottle

# Module-level logger for the `InfoJobsPlaywrightScraper`. The
# `search()` method uses it to emit the one-time INFO hint
# when the scraper is constructed without a `location_resolver`
# (the legacy wiring — REQ-PROV-002 backward-compat path).
_logger = logging.getLogger(__name__)


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

    Spec: REQ-PROV-003 — the `location_resolver` field is the
    seam for the v3 URL plumb. The default is `None` (the v1
    backward-compat path: the scraper uses the v1 `?l=<str>`
    URL formula and never adds `provinceIds/countryIds`).
    Wired in `app_factory.build_app()` to the SAME
    `HardcodedLocationResolver` instance that the LinkedIn
    scraper uses — one resolver, two methods.
    """

    __slots__ = (
        "domain",
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
        domain: str = "www.infojobs.net",
        max_pages: int = 10,
        inter_page_delay_seconds: float = 0.0,
        location_resolver: LocationResolverPort | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self.domain = domain
        self.max_pages = max_pages
        self.inter_page_delay_seconds = inter_page_delay_seconds
        self.location_resolver = location_resolver

    def __repr__(self) -> str:
        return (
            f"InfoJobsScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, domain={self.domain!r}, "
            f"max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
            f"location_resolver={'<set>' if self.location_resolver is not None else 'None'})"
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
            and self.location_resolver is other.location_resolver
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.user_agent,
                self.timeout_ms,
                self.domain,
                self.max_pages,
                self.inter_page_delay_seconds,
                self.location_resolver,
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

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,  # noqa: ARG002 — JobSearchPort compat; unused for InfoJobs
        *,
        infojobs_geo: tuple[int | None, int | None] | None = None,
    ) -> list[Job]:
        """Run a single search; paginate until `limit` is reached or `max_pages` exhausted.

        The pagination loop is owned by `paginated_search`
        (REQ-PAG-001..PAG-003). This method is the composition seam:
        it opens a fresh context + page, optionally applies stealth,
        then hands control to the helper with an InfoJobs-specific
        `_make_fetch_one_page` closure. The helper acquires the
        throttle (REQ-J-005 / REQ-PAG-002) ONCE around the whole
        loop and owns the limit / max_pages / inter-page-delay /
        timeout / zero-cards control flow.

        Per-page pacing (REQ-J-003) is applied INSIDE the helper:
        `await asyncio.sleep(inter_page_delay_seconds)` BEFORE
        pages 1, 2, 3, ... (page 0 is never delayed). The `> 0`
        check skips the call entirely when the delay is `0.0` (no
        event-loop yield, no wall-clock wait).

        REQ-J-006: a `wait_for_selector` timeout on page > 0
        breaks the loop gracefully and returns the first page's
        results. A timeout on page 0 raises `InfoJobsTimeoutError`.

        Spec: REQ-PROV-002 — the v3 URL plumb. The `infojobs_geo`
        keyword-only arg is the resolved `(province_id, country_id)`
        tuple. When `None` (the default), the scraper resolves the
        tuple ONCE per `search()` by calling
        `self._settings.location_resolver.resolve_infojobs(location)`
        IF the resolver is configured. When the resolver is also
        `None` (the legacy wiring), the scraper logs an INFO
        message guiding operators to wire the resolver and falls
        back to the v1 `?l=<str>` URL formula. The `infojobs_geo`
        tuple is captured by the closure built below and reused
        on every page (REQ-PROV-002 scenario 5: "resolver called
        exactly once per `search()`, not per page").
        """
        # Resolve the (province_id, country_id) tuple ONCE per
        # `search()` (not per page). The closure captures the
        # result and reuses it on every page. The resolver is
        # only called when the caller did NOT pass an explicit
        # `infojobs_geo` kwarg (tests that bypass the resolver
        # can inject the tuple directly).
        if infojobs_geo is None:
            resolver = self._settings.location_resolver
            if resolver is not None:
                infojobs_geo = resolver.resolve_infojobs(location)
            else:
                # Legacy wiring: the resolver is not configured.
                # Log a one-time INFO hint so operators can wire
                # the resolver (the v3 recommended path). The
                # URL falls back to the v1 shape (no
                # `provinceIds/countryIds`).
                _logger.info(
                    "InfoJobsPlaywrightScraper: no location_resolver configured; "
                    "URLs fall back to ?l=<str> (v1). Wire a HardcodedLocationResolver "
                    "via InfoJobsScraperSettings(location_resolver=...) for the v3 "
                    "narrowed URL shape.",
                )

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
                    fetch_one_page=self._make_fetch_one_page(
                        keywords,
                        location,
                        infojobs_geo=infojobs_geo,
                    ),
                    limit=limit,
                    max_pages=self._settings.max_pages,
                    inter_page_delay_seconds=self._settings.inter_page_delay_seconds,
                    timeout_exc_type=InfoJobsTimeoutError,
                )
            finally:
                await page.close()
        finally:
            await ctx.close()

    def _make_fetch_one_page(
        self,
        keywords: str,
        location: str,
        *,
        infojobs_geo: tuple[int | None, int | None] | None = None,
    ) -> Callable[[Any, int, int], Awaitable[list[Job]]]:
        """Build a per-page closure that captures InfoJobs-specific concerns.

        The closure passed to `paginated_search` is called once per
        page with `(page, page_index, remaining)`. It navigates the
        page, checks for Distil / Geetest blocks, parses the cards
        via the 3-arg `_parse_cards(soup, remaining, domain)`, and
        raises `InfoJobsParseError` on page 0 when zero cards are
        returned.

        All InfoJobs-specific behavior that the canonical loop
        helper must NOT know about lives here:
            - URL formula: `page=page_index + 1` (InfoJobs uses
              1-indexed pagination; the internal loop is 0-indexed
              so we add 1 to translate).
            - `is_infojobs_blocked(soup)` check after
              `wait_for_selector` (Distil / Geetest challenge).
            - `_parse_cards(soup, remaining, domain)` 3-arg shape
              (LinkedIn's parser is 2-arg; Indeed shares the 3-arg
              shape but with a different URL formula + blocked-check).
            - `InfoJobsParseError("zero_cards_on_first_page")` on
              page 0 with no cards (LinkedIn silently breaks
              instead).
            - The `infojobs_geo` tuple is captured in the closure
              and forwarded to `_build_url` on every page. The
              tuple is resolved ONCE in `search()` and captured
              here — the closure does NOT call the resolver
              (REQ-PROV-002 scenario 5).
        """
        domain = self._settings.domain

        async def fetch_one_page(page: Any, page_index: int, remaining: int) -> list[Job]:
            url = self._build_url(keywords, location, page_index + 1, infojobs_geo=infojobs_geo)
            await self._navigate_and_wait(page, url)
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            if is_infojobs_blocked(soup):
                raise InfoJobsBlockedError(
                    "InfoJobs returned a Distil / Geetest challenge page",
                    details={"url": url},
                )
            new_jobs = _parse_cards(soup, remaining, domain)
            if page_index == 0 and not new_jobs:
                raise InfoJobsParseError(
                    "scraper: zero cards on first page",
                    details={"reason": "zero_cards_on_first_page"},
                )
            return new_jobs

        return fetch_one_page

    def _build_url(
        self,
        keywords: str,
        location: str,
        page: int,
        *,
        infojobs_geo: tuple[int | None, int | None] | None = None,
    ) -> str:
        """Build the InfoJobs search URL, optionally narrowed by province/country.

        The v1 URL formula is `?q=<kw>&l=<loc>&page=<p>`. The
        v3 formula extends it with `&provinceIds=<id>&countryIds=<id>`
        when the `infojobs_geo` tuple carries one or both
        IDs (REQ-PROV-002):

            - `infojobs_geo=(province_id, country_id)` →
              `&provinceIds=<p>&countryIds=<c>` (canonical
              "specific city" case).
            - `infojobs_geo=(None, country_id)` → `&countryIds=<c>`
              only (the "Remote" / "España" / "teletrabajo"
              country-only sentinel).
            - `infojobs_geo=None` OR `(None, None)` → v1 shape
              (no extra params; the unmapped / legacy fallback).

        The order of appended params is: `provinceIds` first,
        then `countryIds`, so the URL is stable and
        human-readable. The 1-indexed `page` param stays
        between `l=` and `provinceIds=` (the v1 shape at
        the start of the URL is preserved).
        """
        base = (
            f"https://{self._settings.domain}/ofertas-trabajo"
            f"?q={quote(keywords)}&l={quote(location)}&page={page}"
        )
        # Fallback: no resolver configured OR resolver returned
        # `(None, None)`. The unmapped sentinel is the
        # canonical "I cannot narrow this region" signal — the
        # scraper preserves the v1 `l=<loc>` shape and lets
        # InfoJobs do whatever it does today.
        if infojobs_geo is None or (infojobs_geo[0] is None and infojobs_geo[1] is None):
            return base
        province_id, country_id = infojobs_geo
        params: list[str] = []
        if province_id is not None:
            params.append(f"provinceIds={province_id}")
        if country_id is not None:
            params.append(f"countryIds={country_id}")
        return base + "&" + "&".join(params)

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
                description=parse_infojobs_description(card),
            )
            jobs.append(job)
        except InfoJobsParseError as e:
            raise InfoJobsParseError(
                "scraper: failed to build Job from card",
                details={"card_html": str(card)[:200], "cause": str(e)},
            ) from e
    return jobs
