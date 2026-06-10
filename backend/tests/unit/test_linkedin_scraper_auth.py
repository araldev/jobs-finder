"""T-004 of `backend-linkedin-auth` — `LinkedInPlaywrightScraper.search()`
cookie injection + `is_auth_wall` integration (REQ-LA-SCR-001..006 +
REQ-LA-AWALL-005..006).

This test file is SEPARATE from `test_linkedin_scraper.py` because
the new tests need a `FakeBrowser` / `FakeContext` (driven via the
`browser_factory` kwarg + `async with scraper:` lifecycle). The
pre-existing test file drives the static `_make_fetch_one_page`
closure directly without a browser, which is the right pattern
for the URL-builder tests but is not enough to assert the
`new_context()` / `add_cookies()` / `_parse_cards()` wiring.

Spec coverage:
- REQ-LA-SCR-001: `search()` reads the cookie from the injected
  port (not from `os.environ`).
- REQ-LA-SCR-002 + REQ-LA-SCR-004: `ctx.add_cookies` is called
  with the exact 6-field shape (`name`, `value`, `domain`,
  `path`, `httpOnly`, `secure`).
- REQ-LA-SCR-003: no `add_cookies` call when `auth_cookie=None`.
- REQ-LA-SCR-005: no log record contains the cookie value.
- REQ-LA-SCR-006: `add_cookies` is called ONCE per `search()` (not
  per page); 2 calls to `search()` → 2 calls to `add_cookies`.
- REQ-LA-AWALL-005 + REQ-LA-AWALL-006: the closure emits a
  WARNING log when `is_auth_wall(soup)` is True; the scraper
  returns `[]` (no raise) on the auth-wall + 0 cards case.

The synthetic test value `"AQEAAAAQEAAA"` (12 bytes ASCII) is the
canonical NON-REAL placeholder per the `backend-linkedin-auth`
exploration (obs #353). Real `li_at` cookies are forbidden from
the repo by AGENTS.md rule #7.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pydantic import SecretStr

from jobs_finder.infrastructure.linkedin.auth_cookie import (
    EnvLinkedInAuthCookieAdapter,
)
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    LinkedInScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from tests.conftest import FakeLinkedInAuthCookiePort
from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakePage:
    """Minimal Playwright `Page` stub.

    `html` may be a `str` (returned for every navigation) or a
    callable `(url) -> str` for per-page content (used by the
    auth-wall + cards tests).
    """

    def __init__(
        self,
        html: str | Callable[[str], str] = "",
    ) -> None:
        self._html = html
        self.goto_calls: list[str] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
        return None

    async def content(self) -> str:
        if callable(self._html):
            return self._html(self.goto_calls[-1])
        return self._html

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    """Minimal Playwright `BrowserContext` stub with `add_cookies` recording."""

    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.closed = False
        self.add_cookies_calls: list[list[dict[str, Any]]] = []

    async def new_page(self) -> _FakePage:
        return self.page

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        # Playwright's `BrowserContext.add_cookies(cookies=[...])` is
        # the documented API. We record the payload verbatim so the
        # golden-shape assertion can verify it byte-for-byte.
        self.add_cookies_calls.append(cookies)

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    """Minimal Playwright `Browser` stub."""

    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.closed = False
        self.new_context_calls: list[dict[str, Any]] = []
        self.contexts: list[_FakeContext] = []

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        self.new_context_calls.append(kwargs)
        ctx = _FakeContext(self.page)
        self.contexts.append(ctx)
        return ctx

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    auth_cookie: EnvLinkedInAuthCookieAdapter | FakeLinkedInAuthCookiePort | None = None,
    max_pages: int = 1,
) -> LinkedInScraperSettings:
    return LinkedInScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
        max_pages=max_pages,
        inter_page_delay_seconds=0.0,
        auth_cookie=auth_cookie,  # type: ignore[arg-type]
    )


async def _make_scraper_with(
    page: _FakePage,
    *,
    auth_cookie: EnvLinkedInAuthCookieAdapter | FakeLinkedInAuthCookiePort | None = None,
    max_pages: int = 1,
) -> tuple[LinkedInPlaywrightScraper, _FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent.

    Mirrors the `test_indeed_scraper.py:_make_scraper_with` pattern
    (lines 145-184): the throttle is `min_interval_seconds=0.0`
    so the tests don't sleep; the inter-page delay defaults to
    `0.0` for the same reason.
    """
    fake_browser = _FakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> _FakeBrowser:
        return fake_browser

    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=_settings(auth_cookie=auth_cookie, max_pages=max_pages),
        browser_factory=factory,
    )
    return scraper, fake_browser


# ---------------------------------------------------------------------------
# Tests — REQ-LA-SCR-001..006 (cookie injection lifecycle)
# ---------------------------------------------------------------------------


async def test_search_reads_cookie_from_injected_port_not_env(
    monkeypatch: Any,
) -> None:
    """REQ-LA-SCR-001 — `search()` reads the cookie from the injected
    port, NOT from `os.environ`. The test sets BOTH the env var
    (a non-port value that should be ignored) AND the port
    (the value the test expects to land in `add_cookies`). The
    port's value wins.
    """
    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("SYNTHETIC_FROM_PORT")),
    )
    monkeypatch.setenv("LINKEDIN_LI_AT", "REAL_ENV_VALUE")
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    # The cookie that reached `add_cookies` is the PORT's value,
    # not the env var's value.
    assert len(fake_browser.contexts) == 1
    cookies = fake_browser.contexts[0].add_cookies_calls[0]
    assert cookies[0]["value"] == "SYNTHETIC_FROM_PORT"
    assert "REAL_ENV_VALUE" not in str(cookies)


async def test_add_cookies_called_with_correct_shape() -> None:
    """REQ-LA-SCR-002 + REQ-LA-SCR-004 — exact shape match (golden assertion).

    The 6-field contract is LinkedIn's issuance contract: name +
    domain + path + httpOnly + secure. A regression that drops
    any field (e.g. `httpOnly=False`) would break the cookie's
    server-side-only + HTTPS-only semantics; a regression that
    changes `domain` to `"linkedin.com"` (no leading dot) would
    not match the subdomain the SERP uses.
    """
    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    assert len(fake_browser.contexts) == 1
    assert fake_browser.contexts[0].add_cookies_calls == [
        [
            {
                "name": "li_at",
                "value": "AQEAAAAQEAAA",
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ]
    ]


async def test_no_add_cookies_call_when_auth_cookie_none() -> None:
    """REQ-LA-SCR-003 — when `auth_cookie is None`, the v1 anonymous
    path is preserved: `add_cookies` is NEVER called."""
    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(page, auth_cookie=None)
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
    assert len(fake_browser.contexts) == 1
    assert fake_browser.contexts[0].add_cookies_calls == []


async def test_add_cookies_called_once_per_search() -> None:
    """REQ-LA-SCR-006 — `add_cookies` is called ONCE per `search()`,
    not per page. The test forces 2 pages (limit=50, max_pages=2)
    and asserts exactly 1 `add_cookies` call total.

    The page returns `SEARCH_PAGE_HTML` (3 valid cards) for every
    navigation; with `limit=50` + `max_pages=2`, the loop iterates
    2 pages (3 cards < 50, so the helper keeps going) and stops
    because `page_index == max_pages - 1`. The test asserts the
    `add_cookies` call COUNT, not the parsed jobs.
    """

    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
        max_pages=2,
    )
    async with scraper:
        await scraper.search("react", "Madrid", limit=50)
    assert len(fake_browser.contexts) == 1
    assert len(fake_browser.contexts[0].add_cookies_calls) == 1


async def test_add_cookies_called_once_per_search_for_multiple_searches() -> None:
    """REQ-LA-SCR-006 — 2 calls to `search()` → 2 calls to
    `add_cookies` (one per `new_context()` lifecycle)."""
    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, fake_browser = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )
    async with scraper:
        await scraper.search("react", "Madrid", limit=10)
        await scraper.search("python", "Barcelona", limit=10)
    assert len(fake_browser.contexts) == 2
    assert len(fake_browser.contexts[0].add_cookies_calls) == 1
    assert len(fake_browser.contexts[1].add_cookies_calls) == 1


async def test_search_does_not_log_cookie_value(
    caplog: Any,
) -> None:
    """REQ-LA-SCR-005 — no log record at any level contains the
    synthetic cookie value. The test uses `caplog` at DEBUG level
    (the most permissive level — every record is captured)."""
    page = _FakePage(SEARCH_PAGE_HTML)
    scraper, _ = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )
    with caplog.at_level(logging.DEBUG):
        async with scraper:
            await scraper.search("react", "Madrid", limit=10)
    leaked = [r for r in caplog.records if "AQEAAAAQEAAA" in r.getMessage()]
    # Also check `args` and `exc_info` (caplog captures the
    # full record — not just the formatted message).
    leaked_args = [
        r for r in caplog.records if r.args and any("AQEAAAAQEAAA" in str(a) for a in r.args)
    ]
    assert leaked == []
    assert leaked_args == []


# ---------------------------------------------------------------------------
# Tests — REQ-LA-AWALL-005..006 (closure integration)
# ---------------------------------------------------------------------------


async def test_closure_warns_on_auth_wall_zero_cards(
    caplog: Any,
) -> None:
    """REQ-LA-AWALL-005 + REQ-LA-AWALL-006 — when the SERP is an
    auth-wall variant with 0 cards, the closure emits a WARNING
    log and `search()` returns `[]` (no raise).

    The HTML used here is an auth-wall variant WITHOUT the
    hard-block signals that `is_block_page` looks for (no
    `form#login`, no sign-in/authenticate/verify title). The
    `BLOCK_PAGE_HTML` fixture used in `is_block_page` tests
    triggers the HARD-raise path (REQ-LA-AWALL-002 scenario);
    the auth-wall WARNING path is for the case where the
    page has the `body.auth-wall` class + 0 cards but is NOT
    a hard block (the operator's cookie has expired but the
    SERP renders a degraded variant instead of a true login
    page — the realistic expired-cookie case).
    """
    html = '<html><body class="auth-wall"><main><h1>Sign in to continue</h1></main></body></html>'
    page = _FakePage(html)
    scraper, _ = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )
    with caplog.at_level(logging.WARNING):
        async with scraper:
            result = await scraper.search("react", "Madrid", limit=20)
    assert result == []  # empty list, NOT an exception (REQ-LA-AWALL-006)
    matching = [
        r
        for r in caplog.records
        if "LinkedIn SERP appears auth-walled despite cookie injection" in r.getMessage()
    ]
    assert len(matching) == 1
    assert matching[0].levelno == logging.WARNING


async def test_closure_does_not_warn_when_cards_present_with_auth_wall_class(
    caplog: Any,
) -> None:
    """REQ-LA-AWALL-005 false-positive suppression — when the HTML
    has BOTH `body.auth-wall` AND cards, the closure does NOT
    warn ("cards win" rule). The page is built by prepending
    `body class="auth-wall"` to the `SEARCH_PAGE_HTML` fixture
    so the cards are valid (full LinkedIn-shaped cards, not
    empty divs that would trigger `LinkedInParseError`).
    """
    # Inject `class="auth-wall"` into the body tag of the
    # SEARCH_PAGE_HTML so the page has BOTH the auth-wall
    # class AND 3 valid cards.
    html = SEARCH_PAGE_HTML.replace("<body>", '<body class="auth-wall">', 1)
    page = _FakePage(html)
    scraper, _ = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )

    with caplog.at_level(logging.WARNING):
        async with scraper:
            result = await scraper.search("react", "Madrid", limit=20)
    # The closure did NOT emit the auth-wall WARNING ("cards
    # win" rule). The exact parsed jobs are out of scope
    # (covered by the parsers tests) — only the WARNING
    # suppression is the load-bearing assertion here.
    matching = [
        r
        for r in caplog.records
        if "LinkedIn SERP appears auth-walled despite cookie injection" in r.getMessage()
    ]
    assert matching == []
    # Sanity: the search returned without raising.
    assert result is not None


async def test_closure_returns_empty_list_on_auth_wall_no_raise() -> None:
    """REQ-LA-AWALL-006 — explicit assertion: search() on an
    auth-walled page (auth wall + 0 cards) returns `[]` (empty
    list), does NOT raise `LinkedInBlockedError` or any new
    exception type.

    The HTML is the same auth-wall variant used in
    `test_closure_warns_on_auth_wall_zero_cards` — has the
    `body.auth-wall` class + 0 cards, but does NOT match
    `is_block_page`'s hard-block signals (no `form#login`, no
    sign-in title). The closure emits the WARNING and
    `search()` returns `[]`.
    """
    html = '<html><body class="auth-wall"><main><h1>Sign in to continue</h1></main></body></html>'
    page = _FakePage(html)
    scraper, _ = await _make_scraper_with(
        page,
        auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
    )
    async with scraper:
        result = await scraper.search("react", "Madrid", limit=20)
    assert result == []
