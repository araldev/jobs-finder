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

import logging
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

from jobs_finder.application.ports import (
    JobSearchPort,
    LinkedInAuthCookiePort,
    LinkedInAuthCookiesPort,
    LocationResolverPort,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.pagination import paginated_search

from .exceptions import LinkedInBlockedError, LinkedInParseError, LinkedInTimeoutError
from .parsers import (
    is_auth_wall,
    is_block_page,
    is_cloudflare_challenge,
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

# Module-level logger for the scraper. Used by the cookie
# injection (T-004, REQ-LA-SCR-005 — DEBUG line logs the cookie
# LENGTH, NEVER the value) and the auth-wall WARNING
# (REQ-LA-AWALL-005 — WARNING line emitted inside
# `_make_fetch_one_page` when `is_auth_wall(soup)` is True).
_logger = logging.getLogger(__name__)

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

    T-004 of `backend-linkedin-stealth` adds 2 NEW slots:
    - `auth_cookies`: the plural `LinkedInAuthCookiesPort` (4
      cookies: `li_at` + `JSESSIONID` + `bcookie` + `li_gc`). The
      v1 `auth_cookie` slot is KEPT for backward compat with the
      35 v1 `backend-linkedin-auth` tests that construct the v1
      `EnvLinkedInAuthCookieAdapter` directly.
    - `stealth`: the `playwright_stealth.Stealth` instance
      (mirrors `IndeedScraperSettings.stealth` precedent, per
      obs #83). The default is `None` (preserves v1 behavior;
      tests pass `stealth=None` and the live wire passes
      `Stealth()`).
    """

    __slots__ = (
        "auth_cookie",
        "auth_cookies",
        "headless",
        "inter_page_delay_seconds",
        "launch_channel",
        "location_resolver",
        "max_pages",
        "stealth",
        "timeout_ms",
        "user_agent",
        "xvfb_display",
    )

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_ms: int,
        max_pages: int = 10,
        inter_page_delay_seconds: float = 1.0,
        location_resolver: LocationResolverPort | None = None,
        auth_cookie: LinkedInAuthCookiePort | None = None,
        auth_cookies: LinkedInAuthCookiesPort | None = None,
        stealth: Any | None = None,
        headless: bool = True,
        xvfb_display: str | None = None,
        launch_channel: str | None = None,
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
        # v1 `LinkedInAuthCookiePort` (singular) — KEPT for
        # backward compat with the 35 v1 tests. When set, the
        # scraper calls `auth_cookie.cookie()` ONCE per
        # `search()` and injects the result via
        # `ctx.add_cookies([...])` between `new_context()` and
        # `paginated_search()` (REQ-LA-SCR-001..006). The
        # production wire passes `auth_cookie=None` (the v1
        # slot is empty; the v1 `EnvLinkedInAuthCookieAdapter`
        # is preserved but unused in the production wire).
        # The `__repr__` masks the value as `<set>` / `<unset>`
        # so the cookie never appears in logs.
        self.auth_cookie = auth_cookie
        # T-004 of `backend-linkedin-stealth` —
        # REQ-LST-COOKIE-001..005 + REQ-LST-SCR-001..004.
        # When set, the scraper calls
        # `auth_cookies.cookies()` ONCE per `search()` and
        # injects the multi-cookie list via
        # `ctx.add_cookies([{...} for (n, v) in cookies])`.
        # The slot is opt-in (default `None`); the closure
        # precedence is conditional on `auth_cookies is not
        # None and auth_cookies.cookies() is not None`.
        # The `__repr__` masks the value as `<set>` /
        # `<unset>` (REQ-LST-COOKIE-005).
        self.auth_cookies = auth_cookies
        # T-004 of `backend-linkedin-stealth` —
        # REQ-LST-SCR-001. The `playwright_stealth.Stealth`
        # instance. When set, `search()` calls
        # `await self._stealth.apply_stealth_async(ctx)` AFTER
        # `new_context()` BEFORE `add_cookies` (mirrors the
        # Indeed+InfoJobs precedent byte-identically). The
        # default is `None` (preserves v1 behavior).
        self.stealth = stealth
        # T-001 of `backend-linkedin-xvfb` — REQ-LBUG-001
        # (obs #379 bugfix fold-in). The v1 cycle shipped
        # `Settings.headless: bool = True` and the
        # `LINKEDIN_HEADLESS=false` env binding, but
        # `scraper.py:288` hardcoded `headless=True` so the
        # field was DECLARED but NEVER CONSUMED (a
        # "field-existence test is not a field-is-used test"
        # gap, per obs #379). The new slot holds the
        # composition-root-resolved `Settings.headless`
        # value; the scraper's `__aenter__` reads it as
        # `self._settings.headless` and passes it to
        # `chromium.launch(headless=...)`. Default `True` so
        # the v1 default path is byte-identical (the only
        # change for v1 callers is the slot's existence).
        self.headless = headless
        # T-002 of `backend-linkedin-xvfb` — REQ-LXV-001/002/003.
        # The opt-in `Settings.linkedin_xvfb_display` value
        # (sourced from the `LINKEDIN_XVFB_DISPLAY` env var).
        # When NOT `None`, the scraper's `__aenter__` enters
        # the Xvfb branch: `chromium.launch(headless=False,
        # args=["--no-sandbox", "--disable-dev-shm-usage"])`
        # and `async_playwright().start(env={"DISPLAY":
        # xvfb_display})`. When `None` (the default), the
        # v1+v2 byte-identical headless path is taken. The
        # field is `str | None` (NOT `SecretStr` because the
        # display string is not a secret — `:99` is the
        # default; no value-masking concern).
        self.xvfb_display = xvfb_display
        # Experiment: the opt-in `LINKEDIN_LAUNCH_CHANNEL` env var
        # (wired from `Settings.linkedin_launch_channel`) tells
        # Playwright to use a system browser channel (e.g. "chrome")
        # instead of the bundled Chromium. This gives LinkedIn the
        # same TLS / HTTP-2 fingerprint as the user's real browser,
        # breaking the session-fingerprint binding redirect loop.
        # When `None` (the default), no `channel=` kwarg is passed
        # to `chromium.launch(...)`, preserving the current behavior.
        self.launch_channel = launch_channel

    def __repr__(self) -> str:
        auth_cookie_repr = "<set>" if self.auth_cookie is not None else "<unset>"
        auth_cookies_repr = "<set>" if self.auth_cookies is not None else "<unset>"
        stealth_repr = "<set>" if self.stealth is not None else "<unset>"
        return (
            f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
            f"location_resolver={self.location_resolver!r}, "
            f"auth_cookie={auth_cookie_repr}, "
            f"auth_cookies={auth_cookies_repr}, "
            f"stealth={stealth_repr}, "
            f"headless={self.headless}, "
            f"xvfb_display={self.xvfb_display!r}, "
            f"launch_channel={self.launch_channel!r})"
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
            and self.auth_cookie == other.auth_cookie
            and self.auth_cookies == other.auth_cookies
            and self.stealth == other.stealth
            and self.headless == other.headless
            and self.xvfb_display == other.xvfb_display
            and self.launch_channel == other.launch_channel
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.user_agent,
                self.timeout_ms,
                self.max_pages,
                self.inter_page_delay_seconds,
                self.location_resolver,
                self.auth_cookie,
                self.auth_cookies,
                self.stealth,
                self.headless,
                self.xvfb_display,
                self.launch_channel,
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
        # T-004 of `backend-linkedin-stealth` — REQ-LST-SCR-001.
        # The `playwright_stealth.Stealth` instance. When set,
        # `search()` calls
        # `await self._stealth.apply_stealth_async(ctx)` AFTER
        # `new_context()` BEFORE `add_cookies` (mirrors the
        # Indeed+InfoJobs precedent byte-identically at
        # `indeed/scraper.py:246-247` and
        # `infojobs/scraper.py:326-327`). The default is
        # `None` (preserves v1 behavior).
        self._stealth: Any | None = settings.stealth

    async def __aenter__(self) -> Self:
        if self._browser_factory is not None:
            self._browser = await self._browser_factory()
        elif self._settings.xvfb_display is not None:
            # T-002 of `backend-linkedin-xvfb` — REQ-LXV-001/002/003.
            # The Xvfb branch: launch Chromium non-headless under
            # a virtual X display so the browser has a real
            # windowing context + real TLS / HTTP-2 SETTINGS
            # frame, evading Cloudflare 2026's headless-Chromium
            # fingerprint detection.
            #
            # Three changes from the no-Xvfb path:
            #   1. `headless=False` (Xvfb wins over
            #      `Settings.headless`; Chromium needs a real
            #      display to actually render).
            #   2. `args=["--no-sandbox", "--disable-dev-shm-usage"]`
            #      (the standard Chromium-in-Xvfb incantation for
            #      Debian / Docker).
            #   3. `env={"DISPLAY": xvfb_display}` is passed to
            #      `chromium.launch(...)` (REQ-LXV-003) so the
            #      Chromium subprocess inherits the `DISPLAY`
            #      env var and can find the X server. NOTE:
            #      the design's original `async_playwright()
            #      .start(env=...)` was incorrect — Playwright
            #      Python's `start()` takes no kwargs; the
            #      `env=` kwarg is supported on `chromium.launch()`.
            xvfb = self._settings.xvfb_display
            self._playwright = await async_playwright().start()
            # EXPERIMENT: `linkedin_launch_channel` — when set
            # (e.g. "chrome"), the `channel=` kwarg tells
            # Playwright to use the system Chrome binary instead
            # of the bundled Chromium, giving LinkedIn the same
            # TLS / HTTP-2 fingerprint as the user's real browser.
            _launch_kwargs: dict[str, Any] = {
                "headless": self._settings.headless,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
                "env": {"DISPLAY": xvfb},
            }
            if self._settings.launch_channel is not None:
                _launch_kwargs["channel"] = self._settings.launch_channel
            self._browser = await self._playwright.chromium.launch(
                **_launch_kwargs,
            )
        else:
            # No-Xvfb path (REQ-LXV-002 + REQ-LBUG-001):
            # byte-identical to the v1 + v2 (cycle 2) ship
            # when `Settings.headless` is `True` (the v1 default).
            # T-001 of `backend-linkedin-xvfb` wired
            # `self._settings.headless` (was hardcoded `True`).
            # The `args=[]` is the explicit sentinel for the
            # no-Xvfb path (the design's truth table requires
            # `args=[]` in Rows 1 + 2; a regression to no-args
            # would break the test).
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._settings.headless, args=[]
            )
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

        `structured` resolution (REQ-STR-LOC-001, T-002 of
        `backend-linkedin-location-fallback`): when the
        resolver returns `None` for `resolve()` (the city is
        NOT in the geoId dict) AND the scraper has a
        `location_resolver` configured, the scraper ALSO
        calls `resolve_structured(location)` ONCE per
        `search()` and uses the returned `(city, province,
        country)` triplet as the `?location=<city>,<province>,
        <country>` URL parameter. The resolver is called AT
        MOST once per `search()` (not per page); the result
        is captured in the closure. The URL builder's
        priority is `geoId > structured > raw` — `geo_id`
        always wins when both are available.
        """
        if self._settings.location_resolver is not None:
            if geo_id is None:
                geo_id = self._settings.location_resolver.resolve(location)
            # The structured triplet is captured only when the
            # resolver is present (legacy wiring with
            # `location_resolver=None` skips the lookup
            # entirely — the URL falls back to `?location=<raw>`).
            resolver = self._settings.location_resolver
            structured: tuple[str, str, str] | None = resolver.resolve_structured(location)
        else:
            structured = None
        ctx = await self._browser.new_context(
            user_agent=self._settings.user_agent,
            viewport=VIEWPORT,
        )
        # T-004 of `backend-linkedin-stealth` — REQ-LST-SCR-001.
        # Stealth injection. The `playwright_stealth.Stealth`
        # instance is held in `self._stealth` (set from
        # `settings.stealth` at ctor time). When set, the
        # call is `await self._stealth.apply_stealth_async(ctx)` —
        # the per-context pattern (mirrors Indeed at
        # `indeed/scraper.py:246-247` and InfoJobs at
        # `infojobs/scraper.py:326-327` byte-identically).
        # When `None` (the v1 default; tests), the call is
        # skipped (no `if`-fallthrough side-effects).
        if self._stealth is not None:
            await self._stealth.apply_stealth_async(ctx)
        # LinkedIn cookie-consent banner: inject an init script
        # that auto-dismisses the consent modal as soon as it
        # appears. This avoids the timing race between
        # `page.goto(page)` and `_dismiss_cookie_consent`.
        # AttributeError is silently caught so the method works
        # with fake context objects in tests.
        try:
            await ctx.add_init_script(
                """() => {
                    new MutationObserver((mutations, observer) => {
                        const btn = document.querySelector(
                            'button[action-type="ACCEPT"]'
                        );
                        if (btn) {
                            btn.click();
                            observer.disconnect();
                        }
                    }).observe(document.documentElement, { childList: true, subtree: true });
                }"""
            )
        except AttributeError:
            pass

        # T-004 of `backend-linkedin-stealth` — REQ-LST-SCR-002.
        # Multi-cookie injection. The v1 single-cookie
        # `auth_cookie` slot is KEPT (the 35 v1 tests construct
        # the v1 `EnvLinkedInAuthCookieAdapter` directly and
        # pass it through `LinkedInScraperSettings.auth_cookie`).
        # The new `auth_cookies` slot (plural
        # `LinkedInAuthCookiesPort`) is the production wire
        # (REQ-LST-COOKIE-001). When set, the scraper calls
        # `auth_cookies.cookies()` ONCE per `search()` and
        # injects the multi-cookie list via
        # `ctx.add_cookies([{...} for (n, v) in cookies])` with
        # the LinkedIn-shape dict (`domain=".linkedin.com"`,
        # `path="/"`, `httpOnly=True`, `secure=True`). The
        # `count=%d` DEBUG line uses the count ONLY (no
        # value leak).
        auth_cookies_port = self._settings.auth_cookies
        if auth_cookies_port is not None:
            # T-00X of `backend-linkedin-cookie-attrs` — try the full-dict
            # path first. When the port supports ``cookie_dicts()`` (the
            # ``JsonLinkedInAuthCookiesAdapter``), pass the ORIGINAL
            # attributes (domain, path, httpOnly, secure) directly to
            # ``ctx.add_cookies()``. This fixes the
            # ``ERR_TOO_MANY_REDIRECTS`` that happens when hardcoding
            # ``domain=".linkedin.com"`` for cookies that originally had
            # ``domain=".www.linkedin.com"``.
            cookie_dicts_fn = getattr(auth_cookies_port, "cookie_dicts", None)
            if cookie_dicts_fn is not None:
                dicts = cookie_dicts_fn()
                if dicts is not None:
                    await ctx.add_cookies(dicts)
                    _logger.debug("LinkedIn auth cookies injected via dicts (count=%d)", len(dicts))
                else:
                    # dicts returned None — fall through to legacy path
                    pass
            # Legacy name+value path — hardcoded attributes (v1 contract).
            # Used when the port does NOT support ``cookie_dicts()``
            # (e.g. ``MultiEnvLinkedInAuthCookiesAdapter`` in tests).
            if cookie_dicts_fn is None:
                cookies = auth_cookies_port.cookies()
                if cookies is not None:
                    await ctx.add_cookies(
                        [
                            {
                                "name": name,
                                "value": value.get_secret_value(),
                                "domain": ".linkedin.com",
                                "path": "/",
                                "httpOnly": True,
                                "secure": True,
                            }
                            for (name, value) in cookies
                        ]
                    )
                    _logger.debug("LinkedIn auth cookies injected via pairs (count=%d)", len(cookies))
        # v1 single-cookie path (KEPT byte-identical to the v1
        # `backend-linkedin-auth` cycle). When the v1 `auth_cookie`
        # slot is set (the 35 v1 tests construct
        # `EnvLinkedInAuthCookieAdapter` directly), the
        # `cookie()` call is awaited and the single cookie
        # is injected. The v1 `length=%d` DEBUG line uses the
        # length ONLY (no value leak). When the production
        # wire passes `auth_cookie=None` (it does — the
        # production wire uses `auth_cookies=` instead), this
        # block is skipped.
        v1_cookie = (
            self._settings.auth_cookie.cookie() if self._settings.auth_cookie is not None else None
        )
        if v1_cookie is not None:
            await ctx.add_cookies(
                [
                    {
                        "name": "li_at",
                        "value": v1_cookie.get_secret_value(),
                        "domain": ".linkedin.com",
                        "path": "/",
                        "httpOnly": True,
                        "secure": True,
                    }
                ]
            )
            _logger.debug(
                "LinkedIn v1 auth cookie injected (length=%d)",
                len(v1_cookie.get_secret_value()),
            )
        try:
            page = await ctx.new_page()
            try:
                return await paginated_search(
                    page=page,
                    throttle=self._throttle,
                    fetch_one_page=self._make_fetch_one_page(
                        keywords, location, geo_id=geo_id, structured=structured
                    ),
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
        structured: tuple[str, str, str] | None = None,
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
              When `geo_id is None` AND `structured is not None`,
              the URL uses `?location=<city>,<province>,<country>`
              (URL-encoded) — the `REQ-STR-LOC-001` structured
              triplet path. The priority is `geoId > structured >
              raw`.
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
            url = self._build_url(
                keywords, location, page_index * 25, geo_id=geo_id, structured=structured
            )
            await self._navigate_and_wait(page, url)
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            # T-004 of `backend-linkedin-stealth` — REQ-LST-SCR-003.
            # The closure precedence is conditional on the
            # cookie-injection path:
            #
            # - **Cookie path** (when `auth_cookies is not None and
            #   auth_cookies.cookies() is not None`, OR the v1
            #   `auth_cookie is not None`): the soft filters run
            #   FIRST (Cloudflare 302-loop is network-layer,
            #   softer than the cookie-injected auth wall), then
            #   the hard raise. Order:
            #   1. `is_cloudflare_challenge` (NEW, soft
            #      WARNING + return `_parse_cards`).
            #   2. `is_auth_wall` (v1, soft WARNING + return
            #      `_parse_cards`).
            #   3. `is_block_page` (v1, HARD raise).
            #
            # - **Anonymous path** (NEITHER `auth_cookies` nor
            #   `auth_cookie` is set, the v1 default): the
            #   closure checks `is_block_page` ONLY — the v1
            #   hard-raise behavior is preserved byte-identically
            #   (the v1 `test_search_raises_blocked_on_auth_wall`
            #   is the regression check). No soft filter runs
            #   because the operator has not opted in to the
            #   soft path.
            has_cookies = (
                self._settings.auth_cookies is not None
                and self._settings.auth_cookies.cookies() is not None
            ) or self._settings.auth_cookie is not None
            if has_cookies:
                # Cookie path: softest filter first
                # (Cloudflare 302-loop is network-layer,
                # softer than the cookie-injected auth wall).
                if is_cloudflare_challenge(soup):
                    _logger.warning(
                        "LinkedIn Cloudflare challenge detected; stealth "
                        "may be insufficient. Consider setting "
                        "LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, "
                        "LINKEDIN_LI_GC in .env, or upgrading to a "
                        "residential proxy."
                    )
                    return _parse_cards(soup, remaining)
                if is_auth_wall(soup):
                    _logger.warning(
                        "LinkedIn SERP appears auth-walled despite cookie "
                        "injection; cookie may be expired. Returning 0 "
                        "jobs from this page (degraded)."
                    )
                    return _parse_cards(soup, remaining)
                if is_block_page(soup):
                    raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
                return _parse_cards(soup, remaining)
            # Anonymous path — v1 byte-identical.
            if is_block_page(soup):
                raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
            return _parse_cards(soup, remaining)

        return fetch_one_page

    @staticmethod
    def _build_url(
        keywords: str,
        location: str,
        start: int,
        geo_id: int | None = None,
        structured: tuple[str, str, str] | None = None,
    ) -> str:
        """Build the LinkedIn search URL with the priority `geoId > structured > raw` formula.

        The 3-branch priority (REQ-STR-LOC-001, T-002 of
        `backend-linkedin-location-fallback`):

        1. **`geo_id is not None`** → `?keywords=...&geoId=<n>&start=...`
           (the LinkedIn-correct form, `REQ-LOC-GEO-001`).
        2. **`structured is not None`** →
           `?keywords=...&location=quote("<city>,<province>,<country>")&start=...`
           (URL-encoded structured triplet — LinkedIn's
           fuzzy match handles this form better than the
           raw string).
        3. **Both `None`** → `?keywords=...&location=<str>&start=...`
           (the pre-`fix-linkedin-geoid` broken-but-doesn't-500
           fallback for unknown cities).

        The `quote(s)` call (default `safe="/"`) encodes
        commas as `%2C` (the user-captured URL is
        `Antequera%2CAndaluc%C3%ADa%2CSpain` — commas ARE
        encoded, NOT preserved); tildes are encoded as
        UTF-8 multibyte (`%C3%AD` for `í`, `%C3%A1` for `á`,
        `%C3%B3` for `ó`) and spaces as `%20`.

        Args:
            keywords: The user's `keywords` (URL-quoted via
                `urllib.parse.quote`).
            location: The user's free-form `location` string.
                Used only in the legacy `location=` branch
                (when both `geo_id` and `structured` are
                `None`).
            start: The per-page `start=page_index * 25` offset.
            geo_id: The captured LinkedIn `geoId` (e.g.
                `103374081` for Madrid). When `not None`,
                the URL uses `geoId=` (highest priority).
            structured: The structured `(city, province,
                country)` triplet returned by
                `LocationResolverPort.resolve_structured()`.
                Used when `geo_id is None` but `structured is
                not None` (medium priority).

        Returns:
            The full LinkedIn search URL.
        """
        if geo_id is not None:
            return (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={quote(keywords)}&geoId={geo_id}&start={start}"
            )
        if structured is not None:
            city, province, country = structured
            triplet_raw = f"{city},{province},{country}"
            return (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={quote(keywords)}&location={quote(triplet_raw)}&start={start}"
            )
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote(keywords)}&location={quote(location)}&start={start}"
        )

    @staticmethod
    async def _dismiss_cookie_consent(page: Any) -> None:
        """Dismiss the LinkedIn cookie-consent banner if visible.

        LinkedIn shows a cookie-consent modal that creates an overlay
        covering the search results, causing ``wait_for_selector`` with
        the default ``state="visible"`` to time out. This helper runs
        via ``page.evaluate`` (raw DOM) to bypass Playwright's actionability
        checks (the overlay intercepts pointer events).

        The helper polls up to 5 times (10s total) to handle the race
        between ``page.goto`` completing and the banner being rendered
        by LinkedIn's JS. ``AttributeError`` is silently caught so the
        method works with fake pages in tests.
        """
        js = """
            (() => {
                const btn = document.querySelector(
                    'button[action-type="ACCEPT"]'
                );
                if (btn) { btn.click(); return true; }
                return false;
            })()
        """
        try:
            for _ in range(5):
                await page.wait_for_timeout(2000)
                clicked = await page.evaluate(js)
                if clicked:
                    return
        except AttributeError:
            pass

    async def _navigate_and_wait(self, page: Any, url: str) -> None:
        try:
            await page.goto(url)
            await self._dismiss_cookie_consent(page)
            await page.wait_for_selector(RESULTS_SELECTOR, state="attached", timeout=self._settings.timeout_ms)
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
