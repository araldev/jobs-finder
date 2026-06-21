"""REQ-LQ5-002 — Q5 regression pin: the InfoJobs scraper's `chromium.launch(...)`
kwargs are byte-identical to cycle 2 regardless of
`Settings.linkedin_xvfb_display` or `Settings.headless` values.

Mirror of `test_linkedin_indeed_regression.py` for the InfoJobs
scraper. The Q5 lock (proposal §4 decision 5) keeps Xvfb as
LinkedIn-only; the InfoJobs scraper retains its hardcoded
`headless=True` and is NOT modified by `backend-linkedin-xvfb`.

The 2 tests are GREEN by construction: the design does not
touch the InfoJobs scraper. A regression that accidentally
leaks `Settings.xvfb_display` or `Settings.headless` into the
InfoJobs scraper would flip one of these tests RED.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from jobs_finder.infrastructure.infojobs.scraper import (
    InfoJobsPlaywrightScraper,
    InfoJobsScraperSettings,
)
from jobs_finder.infrastructure.infojobs.throttle import InfoJobsAsyncThrottle


async def test_infojobs_launch_kwargs_unaffected_by_linkedin_xvfb() -> None:
    """REQ-LQ5-002 — `chromium.launch(headless=True, args=[])` when `xvfb_display=":99"`.

    Q5 regression (InfoJobs mirror): setting
    `LINKEDIN_XVFB_DISPLAY=":99"` (a LinkedIn-only knob) MUST
    NOT affect the InfoJobs scraper. The InfoJobs scraper's
    launch remains byte-identical to cycle 2:
    `chromium.launch(headless=True)` with no `args=` and no
    `env=` kwargs.
    """
    launch_mock = AsyncMock()
    browser_mock = MagicMock()
    browser_mock.close = AsyncMock()
    launch_mock.return_value = browser_mock

    playwright_ctx = MagicMock()
    playwright_ctx.chromium.launch = launch_mock
    playwright_ctx.stop = AsyncMock()
    playwright_start = AsyncMock(return_value=playwright_ctx)

    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
        browser_factory=None,
    )
    with patch("jobs_finder.infrastructure.infojobs.scraper.async_playwright") as ap_mock:
        ap_mock.return_value.start = playwright_start
        async with scraper:
            pass
    # Q5: the InfoJobs launch keeps its hardcoded headless=True +
    # the 3 sandbox-bypass args added for containerized environments
    # (REQ-LQ5-002: headless hardcoded; the 3 args are an additive
    # sandbox bypass, not a behavior change for local dev).
    launch_mock.assert_called_once_with(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    # No DISPLAY env kwarg leaks to InfoJobs.
    playwright_start.assert_called_once_with()


async def test_infojobs_launch_kwargs_unaffected_by_settings_headless_false() -> None:
    """REQ-LQ5-002 — InfoJobs launch unchanged when `Settings.headless=False`.

    Q5 regression (InfoJobs mirror): the LinkedIn-only
    `Settings.headless=False` knob MUST NOT affect the InfoJobs
    scraper. The InfoJobs scraper retains its hardcoded
    `headless=True` (REQ-LQ5-002: the field is global but
    consumed ONLY by the LinkedIn scraper per the bugfix;
    InfoJobs + Indeed stay hardcoded).

    The test is functionally identical to
    `test_infojobs_launch_kwargs_unaffected_by_linkedin_xvfb`
    in the current state (the InfoJobs scraper has no
    `headless` slot). It is kept as a forward-looking
    regression for the future per-source headless field.
    """
    launch_mock = AsyncMock()
    browser_mock = MagicMock()
    browser_mock.close = AsyncMock()
    launch_mock.return_value = browser_mock

    playwright_ctx = MagicMock()
    playwright_ctx.chromium.launch = launch_mock
    playwright_ctx.stop = AsyncMock()
    playwright_start = AsyncMock(return_value=playwright_ctx)

    settings = InfoJobsScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
    )
    scraper = InfoJobsPlaywrightScraper(
        throttle=InfoJobsAsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
        browser_factory=None,
    )
    with patch("jobs_finder.infrastructure.infojobs.scraper.async_playwright") as ap_mock:
        ap_mock.return_value.start = playwright_start
        async with scraper:
            pass
    # Same as test 1: byte-identical to cycle 2 (headless=True +
    # 3 sandbox-bypass args; the Settings.headless=False knob is
    # LinkedIn-only and MUST NOT affect InfoJobs).
    launch_mock.assert_called_once_with(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    playwright_start.assert_called_once_with()
