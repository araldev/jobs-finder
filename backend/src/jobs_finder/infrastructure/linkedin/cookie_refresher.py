"""LinkedIn cookie refresher (T-LCR-006, `linkedin-cookie-refresh` cycle 4).

Two implementations of `LinkedInCookieRefresherPort`:

1. **`PlaywrightLinkedInCookieRefresher`** — the production impl.
   Reads `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` from `os.environ`,
   launches Chromium (non-headless under Xvfb; headless for tests),
   fills `input[type="email"]` + `input[type="password"]`, clicks submit, polls the URL
   for `/feed` or `/m/` up to `timeout_seconds`. Returns
   `context.cookies()` on success, `None` on ANY failure
   (REQ-LCR-002 — never raises). Logs at WARNING level on
   failure paths (NO cookie values per REQ-LCR-005).

2. **`DisabledLinkedInCookieRefresher`** — the kill-switch target
   for `LINKEDIN_COOKIE_REFRESH_ENABLED=false`. Returns the
   adapter's existing cookies as a list of dicts (identity on
   `auth_cookies.cookies()`), or `None` when no cookies exist
   (REQ-LCR-007). NEVER logs.

Both share a `__slots__` schema for memory efficiency and to
document the no-state invariant. The `Settings` dataclass
(`LinkedInCookieRefresherSettings`) holds the 5 env-driven
knobs: `enabled`, `timeout_seconds`, `email`, `password`,
`chromium_path` (optional), `headless` (default `True`).

Spec: REQ-LCR-001, REQ-LCR-002, REQ-LCR-005, REQ-LCR-007.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from playwright.async_api import async_playwright
from pydantic import SecretStr

from jobs_finder.application.ports import LinkedInAuthCookiesPort

_logger = logging.getLogger(__name__)


class LinkedInCookieRefresherSettings:
    """The 5 env-driven knobs for the cookie refresher.

    Mirrors the slot-based pattern used by
    `LinkedInScraperSettings` (memory-efficient, immutable,
    hashable). The composition root (`app_factory.build_app()`)
    constructs this from `effective_settings` + the operator's
    `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` env vars.

    Attributes:
        enabled: Master switch — `False` ⇒ DisabledLinkedInCookieRefresher
            in the composition root (REQ-LCR-007).
        timeout_seconds: Wall-clock cap on the post-login URL
            poll (default `300.0`, matches `extract_linkedin_cookies.py`).
        email: The operator's LinkedIn email (SecretStr, log-masked).
            `None` ⇒ refresh short-circuits to `None` (REQ-LCR-002).
        password: The operator's LinkedIn password (SecretStr, log-masked).
            `None` ⇒ refresh short-circuits to `None` (REQ-LCR-002).
        chromium_path: Absolute path to a Chromium executable
            (mirrors `INFOJOBS_CHROMIUM_PATH` — used when the
            system Chromium is not at Playwright's default path).
            `None` ⇒ use Playwright's bundled Chromium.
        headless: `False` for Xvfb / visible browser (production
            default), `True` for tests (no display).
    """

    __slots__ = (
        "chromium_path",
        "email",
        "enabled",
        "headless",
        "password",
        "timeout_seconds",
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 300.0,
        email: SecretStr | None = None,
        password: SecretStr | None = None,
        chromium_path: str | None = None,
        headless: bool = False,
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.email = email
        self.password = password
        self.chromium_path = chromium_path
        self.headless = headless

    def __repr__(self) -> str:
        """Mask credentials as `<set>` / `<unset>`. NEVER log values.

        REQ-LCR-005 — the repr shows the SET/UNSET flag for
        email + password (a 1-bit side-channel acceptable per
        the spec) but NEVER the actual values.
        """
        email_repr = "<set>" if self.email is not None else "<unset>"
        password_repr = "<set>" if self.password is not None else "<unset>"
        return (
            f"LinkedInCookieRefresherSettings(enabled={self.enabled}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"email={email_repr}, password={password_repr}, "
            f"chromium_path={self.chromium_path!r}, "
            f"headless={self.headless})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LinkedInCookieRefresherSettings):
            return NotImplemented
        return (
            self.enabled == other.enabled
            and self.timeout_seconds == other.timeout_seconds
            and self.email == other.email
            and self.password == other.password
            and self.chromium_path == other.chromium_path
            and self.headless == other.headless
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.enabled,
                self.timeout_seconds,
                self.email,
                self.password,
                self.chromium_path,
                self.headless,
            )
        )


BrowserFactory = Callable[[], Awaitable[Any]]


class PlaywrightLinkedInCookieRefresher:
    """The production LinkedIn cookie refresher.

    On `refresh()`:
    1. Returns `None` immediately if `LINKEDIN_EMAIL` OR
       `LINKEDIN_PASSWORD` is missing (REQ-LCR-002 — no
       browser launch).
    2. Acquires Chromium (via the optional `browser_factory`
       injection seam — tests inject a fake browser; production
       calls `async_playwright().start()`).
    3. Navigates to `https://www.linkedin.com/login`.
    4. Fills `#username` + `#password`, clicks the submit
       button.
    5. Polls `page.url` every 1s up to `timeout_seconds`;
       success when URL contains `/feed` or `/m/`.
    6. Returns `context.cookies()` on success.
    7. On ANY exception → WARNING log (NO cookie values) →
       returns `None` (REQ-LCR-005 + REQ-LCR-002 never-raise).
    8. `finally:` block closes context + browser.

    Args:
        settings: The `LinkedInCookieRefresherSettings` ctor
            holds the operator's credentials + the timeout +
            the headless flag.
        browser_factory: Optional async callable returning a
            Playwright-like `Browser` instance. When `None`
            (default), the refresher launches real Playwright
            via `async_playwright()`. When provided (tests),
            the factory is called instead — the test owns the
            browser's lifecycle and stubs `goto()` / `fill()` /
            `click()` / `cookies()` / `close()`.
    """

    __slots__ = ("_browser_factory", "_settings")

    def __init__(
        self,
        settings: LinkedInCookieRefresherSettings,
        *,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._settings = settings
        self._browser_factory = browser_factory

    async def refresh(self) -> list[dict[str, Any]] | None:
        """Re-login with credentials; return new cookie dicts or `None`.

        REQ-LCR-002 — NEVER raises. All exceptions are caught
        and converted to `None` + WARNING log.

        Returns:
            A list of cookie dicts (Playwright
            `context.cookies()` shape: `name`, `value`,
            `domain`, `path`, `expires`, `httpOnly`,
            `secure`, `sameSite`) on success, OR `None` on
            any failure.
        """
        # REQ-LCR-002 step 1: missing creds → None (no launch).
        email_str = (
            self._settings.email.get_secret_value()
            if self._settings.email is not None
            else os.environ.get("LINKEDIN_EMAIL")
        )
        password_str = (
            self._settings.password.get_secret_value()
            if self._settings.password is not None
            else os.environ.get("LINKEDIN_PASSWORD")
        )
        if not email_str or not password_str:
            _logger.warning(
                "LinkedIn cookie refresh skipped: missing LINKEDIN_EMAIL or LINKEDIN_PASSWORD"
            )
            return None

        browser: Any = None
        context: Any = None
        try:
            # REQ-LCR-002 step 2: acquire Chromium via the
            # injection seam OR real Playwright.
            if self._browser_factory is not None:
                browser = await self._browser_factory()
            else:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=self._settings.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                        ],
                    )
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                    )
                    return await self._login_and_extract(
                        context=context, email_str=email_str, password_str=password_str
                    )
            # `browser_factory` injection seam path: the
            # caller supplies a complete `Browser` instance;
            # we create the context ourselves.
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
            )
            return await self._login_and_extract(
                context=context, email_str=email_str, password_str=password_str
            )
        except Exception as exc:
            # REQ-LCR-002 step 7: any failure → WARNING + None.
            # The log message intentionally does NOT include
            # the cookie value (REQ-LCR-005 — the
            # `exception` is the `Exception`, which may carry
            # the cookie value via the exception args; we
            # mask it via `_safe_exc_repr`).
            _logger.warning("LinkedIn cookie refresh failed: %s", _safe_exc_repr(exc))
            return None
        finally:
            # REQ-LCR-002 step 8: close context + browser
            # in reverse order (close ctx first).
            if context is not None:
                with contextlib.suppress(Exception):  # best-effort cleanup
                    await context.close()
            if browser is not None and self._browser_factory is None:
                # Only close the browser when WE launched it
                # (production path). When the caller injected
                # the browser, the caller owns its lifecycle.
                with contextlib.suppress(Exception):
                    await browser.close()

    async def _login_and_extract(
        self,
        *,
        context: Any,
        email_str: str,
        password_str: str,
    ) -> list[dict[str, Any]] | None:
        """Navigate, fill, click, poll URL, return cookies.

        Shared between the production path (after `async with
        async_playwright()`) and the injection path (after the
        caller-supplied `browser_factory()`). Returns `None`
        on timeout; `context.cookies()` on success.
        """
        page = await context.new_page()
        try:
            # REQ-LCR-002 step 3: navigate.
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            await asyncio.sleep(1)
            # REQ-LCR-002 step 4: fill credentials.
            #
            # LinkedIn's login page no longer exposes stable HTML IDs
            # (`#username` / `#password`) — they were replaced with
            # obfuscated, request-specific IDs (e.g. `«Refvd3ksopa55j6»`).
            # The stable selectors are now the `type` + `autocomplete`
            # attributes: `input[type="email"]` for the username and
            # `input[type="password"]` for the password.
            #
            # The page renders the inputs TWICE in the DOM (once visible,
            # once for accessibility/automation — both with bbox 0x0
            # vs visible). We MUST use the `:visible` filter, otherwise
            # `.first` resolves to the hidden copy and Playwright
            # times out waiting for it to become editable.
            await page.locator('input[type="email"]:visible').first.fill(email_str)
            await page.locator('input[type="password"]:visible').first.fill(password_str)
            await asyncio.sleep(0.5)
            # REQ-LCR-002 step 4: click submit. Try the
            # English "Sign in" button first, then the Spanish
            # "Iniciar sesión" (LinkedIn localizes).
            clicked = False
            for label in ("Sign in", "Iniciar sesión"):
                try:
                    btn = page.get_by_role("button", name=label, exact=True).first
                    await btn.click(timeout=5000)
                    clicked = True
                    break
                except Exception:  # noqa: BLE001
                    continue
            if not clicked:
                # Fall back to the form submit button.
                await page.click('button[type="submit"]')
            # REQ-LCR-002 step 5: poll the URL.
            poll_interval = 1.0
            max_iters = max(1, int(self._settings.timeout_seconds / poll_interval))
            for _attempt in range(max_iters):
                current_url = page.url
                if "/feed" in current_url or "/m/" in current_url:
                    # REQ-LCR-002 step 6: extract cookies.
                    cookies: list[dict[str, Any]] = await context.cookies()
                    # REQ-LCR-005: log count only, NEVER values.
                    _logger.info(
                        "LinkedIn cookie refresh succeeded; got %d cookies",
                        len(cookies),
                    )
                    return cookies
                if "checkpoint" in current_url:
                    _logger.warning(
                        "LinkedIn cookie refresh hit a checkpoint; 2FA requires manual resolution"
                    )
                    return None
                await asyncio.sleep(poll_interval)
            # Timed out without seeing `/feed` or `/m/`.
            return None
        finally:
            with contextlib.suppress(Exception):
                await page.close()


def _safe_exc_repr(exc: BaseException) -> str:
    """Format an exception for logging WITHOUT leaking cookie values.

    REQ-LCR-005 — the production `refresh()` catches all
    exceptions and logs them at WARNING. The default
    `repr(exc)` could include the cookie value if the
    exception was raised with the value as an argument (e.g.
    `raise RuntimeError(cookie_value)`). The helper extracts
    only the exception TYPE NAME, not the args, so the log
    line is value-free by construction.
    """
    return type(exc).__name__


class DisabledLinkedInCookieRefresher:
    """The kill-switch refresher (REQ-LCR-007).

    `refresh()` returns the adapter's existing cookies as a
    list of dicts (identity on `auth_cookies.cookies()`) —
    NO browser launch, NO `os.replace`, NO `cache_invalidator`,
    NO retry. The scraper treats this as "refresh succeeded
    with no change", which is the correct behavior when the
    operator has explicitly disabled the feature.

    `refresh()` returns `None` when the adapter has no cookies
    (the v1 anonymous path — there's nothing to "return").

    The class is NOT a flag inside `PlaywrightLinkedInCookieRefresher`
    so the composition root can `isinstance`-assert the
    kill-switch target and the test surface can distinguish
    the two implementations structurally.
    """

    __slots__ = ("_auth_cookies",)

    def __init__(self, auth_cookies: LinkedInAuthCookiesPort) -> None:
        self._auth_cookies = auth_cookies

    async def refresh(self) -> list[dict[str, Any]] | None:
        """Return existing cookies as a list of dicts, or `None` if none set.

        The dict shape matches Playwright's `context.cookies()`
        output so the scraper can write it back via
        `auth_cookies.set_cookies()` if it wanted (it doesn't
        — the disabled refresher is identity, so the
        adapter's existing state is the answer).
        """
        pairs = self._auth_cookies.cookies()
        if pairs is None:
            return None
        result: list[dict[str, Any]] = []
        for name, secret in pairs:
            result.append(
                {
                    "name": name,
                    "value": secret.get_secret_value(),
                    # Domain + attributes are best-effort
                    # defaults; the disabled refresher does
                    # NOT touch the file system so the
                    # original attributes from the source
                    # file/env vars are preserved (the
                    # adapter's `cookies()` returns the
                    # canonical 5 names — `JSESSIONID` is
                    # uppercase, the rest lowercase).
                    "domain": ".linkedin.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
        return result
