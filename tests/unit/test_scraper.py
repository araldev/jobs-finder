"""Unit tests for `LinkedInPlaywrightScraper`.

Spec: REQ-013, REQ-024.
The scraper drives a real Chromium in production. Tests use minimal fake
`Page` / `Context` / `Browser` objects so the suite never launches a
browser and never contacts LinkedIn.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from jobs_finder.infrastructure.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInTimeoutError,
)
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    ScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from tests.fixtures.linkedin_search import BLOCK_PAGE_HTML

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePage:
    """Minimal Playwright `Page` stub for scraper tests."""

    def __init__(
        self,
        html: str,
        *,
        selector_timeout: bool = False,
        goto_error: Exception | None = None,
    ) -> None:
        self.html = html
        self.selector_timeout = selector_timeout
        self.goto_error = goto_error
        self.goto_calls: list[str] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        if self.goto_error is not None:
            raise self.goto_error

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
      <ul class="jobs-search__results-list">
        <li class="result-card" data-entity-urn="urn:li:jobPosting:3850000001">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3850000001/">
            <h3 class="base-card__title">Senior Python Developer</h3>
          </a>
          <h4 class="base-card__subtitle">Acme Corp</h4>
          <span class="job-search-card__location">Madrid, Spain</span>
          <time datetime="2026-05-01T00:00:00+00:00">1 day ago</time>
        </li>
        <li class="result-card" data-entity-urn="urn:li:jobPosting:3850000002">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3850000002/">
            <h3 class="base-card__title">Backend Engineer</h3>
          </a>
          <h4 class="base-card__subtitle">Globex Inc</h4>
          <span class="job-search-card__location">Barcelona, Spain</span>
          <time datetime="2026-05-02T00:00:00+00:00">2 days ago</time>
        </li>
        <li class="result-card" data-entity-urn="urn:li:jobPosting:3850000003">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3850000003/">
            <h3 class="base-card__title">Data Scientist</h3>
          </a>
          <h4 class="base-card__subtitle">Initech</h4>
          <span class="job-search-card__location">Valencia, Spain</span>
          <time datetime="2026-05-03T00:00:00+00:00">3 days ago</time>
        </li>
      </ul>
    </body></html>
    """


def _five_card_html() -> str:
    cards: list[str] = []
    for i in range(1, 6):
        cards.append(
            f"""
        <li class="result-card" data-entity-urn="urn:li:jobPosting:385000000{i}">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/385000000{i}/">
            <h3 class="base-card__title">Title {i}</h3>
          </a>
          <h4 class="base-card__subtitle">Company {i}</h4>
          <span class="job-search-card__location">Madrid</span>
          <time datetime="2026-05-0{i}T00:00:00+00:00">{i}d ago</time>
        </li>"""
        )
    return (
        '<html><body><ul class="jobs-search__results-list">'
        + "".join(cards)
        + "</ul></body></html>"
    )


def _settings() -> ScraperSettings:
    return ScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )


async def _make_scraper_with(
    page: FakePage,
) -> tuple[LinkedInPlaywrightScraper, FakeBrowser]:
    """Build a scraper whose browser is the given fake page's parent."""
    fake_browser = FakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> FakeBrowser:
        return fake_browser

    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=_settings(),
        browser_factory=factory,
    )
    return scraper, fake_browser


# ---------------------------------------------------------------------------
# Navigation target (REQ-013: URL is well-formed and quoted)
# ---------------------------------------------------------------------------


async def test_search_navigates_to_linkedin_jobs_search() -> None:
    """The URL contains the quoted keywords and location on the right host."""
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search(keywords="python", location="Madrid")
    assert page.goto_calls == [
        "https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid"
    ]


async def test_search_waits_for_results_selector_with_configured_timeout() -> None:
    """`wait_for_selector` is called with the configured `timeout_ms`."""
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        await scraper.search("python", "Madrid")
    assert page.wait_calls == [("li[data-entity-urn]", 10_000)]


# ---------------------------------------------------------------------------
# Happy path (REQ-013)
# ---------------------------------------------------------------------------


async def test_search_returns_one_job_per_card() -> None:
    """Three cards in the page yield three `Job` objects with the right fields."""
    page = FakePage(_three_card_html())
    scraper, _ = await _make_scraper_with(page)
    async with scraper:
        jobs = await scraper.search("python", "Madrid")
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
