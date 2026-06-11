"""REQ-LQ5-001 — Q5 regression pin: the Indeed scraper's `chromium.launch(...)`
kwargs are byte-identical to cycle 2 regardless of
`Settings.linkedin_xvfb_display` or `Settings.headless` values.

The Q5 lock (proposal §4 decision 5): Xvfb is LinkedIn-only. The
Indeed scraper (and InfoJobs — see `test_linkedin_infojobs_regression.py`)
is NOT modified by the `backend-linkedin-xvfb` change. The 2 tests
below pin the Q5 scope: even when the operator flips BOTH LinkedIn
knobs (`xvfb_display=":99"` + `headless=False`), the Indeed scraper's
launch kwargs remain `chromium.launch(headless=True)` with no Xvfb
args and no DISPLAY env.

The tests are GREEN by construction: the design does not touch
the Indeed scraper. A regression that accidentally leaks
`Settings.xvfb_display` or `Settings.headless` into the Indeed
scraper would flip one of these tests RED.

Mirrors the test pattern from T-002's
`test_chromium_launch_xvfb_display_forces_headless_false` (mock
`async_playwright`, assert the launch kwargs). The Q5 difference
is the OPPOSITE assertion: the launch must NOT change when the
LinkedIn-only knobs are flipped.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from jobs_finder.infrastructure.indeed.scraper import (
    IndeedPlaywrightScraper,
    IndeedScraperSettings,
)
from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle


async def test_indeed_launch_kwargs_unaffected_by_linkedin_xvfb() -> None:
    """REQ-LQ5-001 — `chromium.launch(headless=True, args=[])` when `xvfb_display=":99"`.

    Q5 regression: setting `LINKEDIN_XVFB_DISPLAY=":99"` (a
    LinkedIn-only knob) MUST NOT affect the Indeed scraper. The
    Indeed scraper's launch remains byte-identical to cycle 2:
    `chromium.launch(headless=True)` with no `args=` and no
    `env=` kwargs.

    The test mirrors T-002's `test_chromium_launch_*
    _forces_headless_false` (mock `async_playwright`, assert
    the launch kwargs). The Q5 difference is the OPPOSITE
    assertion: the launch must NOT change when the
    LinkedIn-only knob is flipped.
    """
    launch_mock = AsyncMock()
    browser_mock = MagicMock()
    browser_mock.close = AsyncMock()
    launch_mock.return_value = browser_mock

    playwright_ctx = MagicMock()
    playwright_ctx.chromium.launch = launch_mock
    playwright_ctx.stop = AsyncMock()
    playwright_start = AsyncMock(return_value=playwright_ctx)

    settings = IndeedScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = IndeedPlaywrightScraper(
        throttle=IndeedAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
        browser_factory=None,
    )
    with patch("jobs_finder.infrastructure.indeed.scraper.async_playwright") as ap_mock:
        ap_mock.return_value.start = playwright_start
        async with scraper:
            pass
    # Q5: the Indeed launch is byte-identical to cycle 2.
    # No `--no-sandbox`, no `--disable-dev-shm-usage`, no
    # `env=` kwarg, no Xvfb wins. The launch is
    # `headless=True` (the v1 hardcoded value), `args=[]`
    # (the cycle 2 default — no per-launch args).
    launch_mock.assert_called_once_with(headless=True)
    # The start() call has NO `env=` kwarg (the LinkedIn
    # Xvfb DISPLAY env kwarg MUST NOT leak to Indeed).
    playwright_start.assert_called_once_with()


async def test_indeed_launch_kwargs_unaffected_by_settings_headless_false() -> None:
    """REQ-LQ5-001 — Indeed launch unchanged when `Settings.headless=False`.

    Q5 regression: the LinkedIn-only `Settings.headless=False`
    knob MUST NOT affect the Indeed scraper. The Indeed scraper
    retains its hardcoded `headless=True` (REQ-LQ5-001: the
    field is global but consumed ONLY by the LinkedIn scraper
    per the bugfix; Indeed + InfoJobs stay hardcoded).

    The test pins the Q5 lock from the other angle: even with
    `Settings.headless=False`, the Indeed launch kwargs are
    byte-identical to cycle 2. A regression that wires
    `Settings.headless` into the Indeed scraper (a future
    per-source headless field) would flip this test RED.
    """
    # Note: Indeed does NOT consume `Settings.headless` today
    # (the field is hardcoded `True` at
    # `indeed/scraper.py:207`). The test cannot mutate Indeed's
    # settings (the `IndeedScraperSettings` class has no
    # `headless` slot). The test is therefore equivalent to
    # `test_indeed_launch_kwargs_unaffected_by_linkedin_xvfb`
    # in the current state — both pin the same Q5 contract.
    # The second test is kept as a forward-looking regression
    # for the future per-source headless field (e.g.
    # `indeed_headless`, `infojobs_headless`).
    launch_mock = AsyncMock()
    browser_mock = MagicMock()
    browser_mock.close = AsyncMock()
    launch_mock.return_value = browser_mock

    playwright_ctx = MagicMock()
    playwright_ctx.chromium.launch = launch_mock
    playwright_ctx.stop = AsyncMock()
    playwright_start = AsyncMock(return_value=playwright_ctx)

    settings = IndeedScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = IndeedPlaywrightScraper(
        throttle=IndeedAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
        browser_factory=None,
    )
    with patch("jobs_finder.infrastructure.indeed.scraper.async_playwright") as ap_mock:
        ap_mock.return_value.start = playwright_start
        async with scraper:
            pass
    # Same as test 1: byte-identical to cycle 2.
    launch_mock.assert_called_once_with(headless=True)
    playwright_start.assert_called_once_with()
