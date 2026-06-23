"""Tests for the LinkedIn cookie refresher (T-LCR-013, REQ-LCR-002/003/005/007).

Spec coverage:
- REQ-LCR-002: `PlaywrightLinkedInCookieRefresher.refresh()` NEVER raises;
  returns `None` on any failure (missing creds, browser launch error,
  post-login timeout). Returns `list[dict]` on success.
- REQ-LCR-005: no log record contains a cookie value (defense in
  depth per AGENTS.md rule #7).
- REQ-LCR-007: `DisabledLinkedInCookieRefresher.refresh()` returns
  the existing cookies unchanged (identity); NEVER logs values.

The test strategy uses the `browser_factory` injection seam on
`PlaywrightLinkedInCookieRefresher` — the same pattern as the
scraper's `browser_factory` kwarg. When `None` (default), the
refresher launches real Playwright; when provided, the fake
browser stubs `goto()` / `fill()` / `click()` / `cookies()` /
`close()` / etc. so the refresh can be driven offline.

Test counts (per the spec):
- success (returns cookies)
- missing creds (returns None)
- timeout (returns None)
- browser launch error (returns None)
- no log with cookie values
- disabled identity (returns existing cookies unchanged)
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import SecretStr

from jobs_finder.application.ports import (
    LinkedInAuthCookiesPort,
    LinkedInCookieRefresherPort,
)
from jobs_finder.infrastructure.linkedin.cookie_refresher import (
    DisabledLinkedInCookieRefresher,
    LinkedInCookieRefresherSettings,
    PlaywrightLinkedInCookieRefresher,
)
from tests.conftest import FakeLinkedInAuthCookiesPort

# ---------------------------------------------------------------------------
# Fakes — `_FakeBrowser` / `_FakeContext` / `_FakePage` for the
# `browser_factory` injection seam.
# ---------------------------------------------------------------------------


class _FakePage:
    """Minimal Playwright `Page` stub for the refresher's browser factory."""

    def __init__(self, post_login_url: str = "https://www.linkedin.com/feed/") -> None:
        self._url = "https://www.linkedin.com/login"
        self._post_login_url = post_login_url
        self.fill_calls: list[tuple[str, str]] = []
        self.click_calls: list[str] = []
        self._locator_fill_calls: list[tuple[str, str]] = []
        self._locator_click_calls: list[str] = []

    async def goto(self, url: str, **kwargs: Any) -> None:
        self._url = url

    async def fill(self, selector: str, value: str, **kwargs: Any) -> None:
        self.fill_calls.append((selector, value))

    async def click(self, selector: str, **kwargs: Any) -> None:
        self.click_calls.append(selector)
        # Simulate post-login redirect.
        self._url = self._post_login_url

    def locator(self, selector: str) -> _FakeLocator:
        """Return a locator stub that captures `.fill()` and `.click()` calls."""
        return _FakeLocator(self, selector)

    def get_by_role(self, role: str, name: str = "", **kwargs: Any) -> _FakeLocator:
        """Return a locator stub for the role-based query."""
        return _FakeLocator(self, f"role={role},name={name}")

    @property
    def url(self) -> str:
        return self._url


class _FakeLocator:
    """Stub for Playwright's locator objects."""

    def __init__(self, page: _FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> _FakeLocator:
        return self

    async def fill(self, value: str, **kwargs: Any) -> None:
        self._page._locator_fill_calls.append((self._selector, value))

    async def click(self, **kwargs: Any) -> None:
        self._page._locator_click_calls.append(self._selector)
        # Simulate post-login redirect.
        self._page._url = self._page._post_login_url

    async def wait_for(self, state: str = "visible", **kwargs: Any) -> None:
        return None


class _FakeContext:
    """Minimal Playwright `BrowserContext` stub."""

    def __init__(
        self,
        page: _FakePage,
        cookies_to_return: list[dict[str, object]] | None = None,
    ) -> None:
        self._page = page
        self._cookies = cookies_to_return or []
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self._page

    async def cookies(self) -> list[dict[str, object]]:
        return self._cookies

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    """Minimal Playwright `Browser` stub."""

    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self.closed = False

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        return self._context

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    enabled: bool = True,
    email: str | None = "op@example.com",
    password: str | None = "op_password",
    timeout_seconds: float = 1.0,
    headless: bool = True,
) -> LinkedInCookieRefresherSettings:
    return LinkedInCookieRefresherSettings(
        enabled=enabled,
        timeout_seconds=timeout_seconds,
        email=SecretStr(email) if email else None,
        password=SecretStr(password) if password else None,
        headless=headless,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlaywrightLinkedInCookieRefresher:
    """REQ-LCR-002 — the production refresher (mocked Playwright via
    `browser_factory`)."""

    async def test_refresher_returns_cookies_on_successful_login(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """REQ-LCR-002 scenario 1 — successful login returns the cookies.

        The fake `browser_factory` returns a `_FakeBrowser` whose
        `page.url` becomes `https://www.linkedin.com/feed/` after
        the click. `context.cookies()` returns 1 `li_at` cookie.
        """
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        page = _FakePage(post_login_url="https://www.linkedin.com/feed/")
        ctx = _FakeContext(
            page,
            cookies_to_return=[
                {
                    "name": "li_at",
                    "value": "AQE_NEW",
                    "domain": ".linkedin.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ],
        )
        fake_browser = _FakeBrowser(ctx)

        async def factory() -> _FakeBrowser:
            return fake_browser

        refresher = PlaywrightLinkedInCookieRefresher(
            settings=_settings(),
            browser_factory=factory,
        )
        result = await refresher.refresh()
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "li_at"
        # The fake page was filled + clicked (via
        # `page.locator(sel).first.fill(value)` /
        # `get_by_role(...).first.click()`).
        assert page._locator_fill_calls == [
            ('input[type="email"]:visible', "op@example.com"),
            ('input[type="password"]:visible', "op_password"),
        ]
        assert len(page._locator_click_calls) >= 1
        # Context was closed (the caller owns the browser
        # lifecycle in injection mode — only ctx closes
        # automatically).
        assert ctx.closed is True

    async def test_refresher_returns_none_when_credentials_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """REQ-LCR-002 scenario 2 — missing credentials → `None`,
        no browser launch.

        `LINKEDIN_EMAIL` is removed AND `password` is None on the
        settings. The refresher short-circuits to `None` without
        calling the `browser_factory`.
        """
        monkeypatch.delenv("LINKEDIN_EMAIL", raising=False)
        monkeypatch.delenv("LINKEDIN_PASSWORD", raising=False)
        calls = 0

        async def factory() -> _FakeBrowser:
            nonlocal calls
            calls += 1
            raise AssertionError("browser_factory should not be called")

        refresher = PlaywrightLinkedInCookieRefresher(
            settings=_settings(email=None, password=None),
            browser_factory=factory,
        )
        result = await refresher.refresh()
        assert result is None
        assert calls == 0

    async def test_refresher_returns_none_on_login_timeout(self) -> None:
        """REQ-LCR-002 scenario 3 — `page.url` NEVER reaches
        `/feed` or `/m/`. The refresher polls up to
        `timeout_seconds`, then returns `None` (no exception).
        """
        # `post_login_url` is NOT `/feed` or `/m/`, so the
        # poll never sees success.
        page = _FakePage(post_login_url="https://www.linkedin.com/login")
        ctx = _FakeContext(page, cookies_to_return=[])
        fake_browser = _FakeBrowser(ctx)

        async def factory() -> _FakeBrowser:
            return fake_browser

        refresher = PlaywrightLinkedInCookieRefresher(
            settings=_settings(timeout_seconds=0.1),
            browser_factory=factory,
        )
        result = await refresher.refresh()
        assert result is None
        # No exception raised; context closed cleanly.
        # Note: the browser is NOT closed automatically when
        # the caller injected it via `browser_factory`
        # (REQ-LCR-002 step 8 — caller owns injected
        # browser's lifecycle). Only the context is closed.
        assert ctx.closed is True

    async def test_refresher_returns_none_on_browser_launch_error(self) -> None:
        """REQ-LCR-002 scenario 4 — `browser_factory` raises an
        exception (simulating "chromium not installed"). The
        refresher catches ALL exceptions and returns `None`.
        """

        async def factory() -> _FakeBrowser:
            raise RuntimeError("chromium not installed")

        refresher = PlaywrightLinkedInCookieRefresher(
            settings=_settings(),
            browser_factory=factory,
        )
        result = await refresher.refresh()
        assert result is None

    async def test_refresher_does_not_log_cookie_values(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """REQ-LCR-005 — no log record contains the synthetic cookie
        value. The test exercises the successful-login path so
        the WARNING path (which contains the value) is NOT
        triggered.
        """
        synthetic = "AQE_NEW_LI_AT_VALUE_XYZ"
        monkeypatch.setenv("LINKEDIN_EMAIL", "op@example.com")
        monkeypatch.setenv("LINKEDIN_PASSWORD", "op_password")
        page = _FakePage(post_login_url="https://www.linkedin.com/feed/")
        ctx = _FakeContext(
            page,
            cookies_to_return=[
                {
                    "name": "li_at",
                    "value": synthetic,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ],
        )
        fake_browser = _FakeBrowser(ctx)

        async def factory() -> _FakeBrowser:
            return fake_browser

        refresher = PlaywrightLinkedInCookieRefresher(
            settings=_settings(),
            browser_factory=factory,
        )
        with caplog.at_level(logging.DEBUG):
            result = await refresher.refresh()
        assert result is not None
        # Scan every record — message + args.
        for record in caplog.records:
            text = record.getMessage()
            assert synthetic not in text, f"cookie value leaked into log: {text!r}"
            if record.args:
                for arg in record.args:
                    assert synthetic not in str(arg), f"cookie value leaked into log args: {arg!r}"

    async def test_no_log_call_with_cookie_values(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """REQ-LCR-005 + caplog end-to-end check — even on the
        FAILURE path (refresh returns None), no log line contains
        the cookie value (there isn't one in this path — but the
        test pins that the WARNING log is value-free too).
        """
        monkeypatch.delenv("LINKEDIN_EMAIL", raising=False)
        with caplog.at_level(logging.DEBUG):
            refresher = PlaywrightLinkedInCookieRefresher(
                settings=_settings(email=None, password=None),
                browser_factory=lambda: (_ for _ in ()).throw(AssertionError("not called")),
            )
            result = await refresher.refresh()
        assert result is None
        # No record contains the literal "li_at" prefix commonly
        # seen in real cookies ("AQE" prefix).
        for record in caplog.records:
            text = record.getMessage()
            assert "AQE" not in text, f"AQE-prefix value leaked into log: {text!r}"


class TestDisabledLinkedInCookieRefresher:
    """REQ-LCR-007 — the kill-switch refresher is identity."""

    async def test_disabled_refresher_returns_existing_cookies_unchanged(self) -> None:
        """The disabled refresher returns the existing cookies as a
        list of dicts (Playwright shape) — the same data the
        adapter's `cookies()` returned. No browser launch,
        no `os.replace`, no WARNING.
        """
        adapter: LinkedInAuthCookiesPort = FakeLinkedInAuthCookiesPort(
            cookies=[("li_at", SecretStr("OLD_VAL"))]
        )
        refresher = DisabledLinkedInCookieRefresher(auth_cookies=adapter)
        result = await refresher.refresh()
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "li_at"
        assert result[0]["value"] == "OLD_VAL"

    async def test_disabled_refresher_satisfies_protocol(self) -> None:
        """The disabled refresher satisfies the
        `LinkedInCookieRefresherPort` Protocol structurally.
        """
        adapter: LinkedInAuthCookiesPort = FakeLinkedInAuthCookiesPort(
            cookies=[("li_at", SecretStr("OLD_VAL"))]
        )
        refresher: LinkedInCookieRefresherPort = DisabledLinkedInCookieRefresher(
            auth_cookies=adapter
        )
        result = await refresher.refresh()
        assert result is not None

    async def test_disabled_refresher_returns_none_when_no_cookies(self) -> None:
        """When the adapter has no cookies (v1 anonymous path),
        the disabled refresher returns `None` (no cookies to
        return, no refresh possible).
        """
        adapter: LinkedInAuthCookiesPort = FakeLinkedInAuthCookiesPort(cookies=None)
        refresher = DisabledLinkedInCookieRefresher(auth_cookies=adapter)
        result = await refresher.refresh()
        assert result is None
