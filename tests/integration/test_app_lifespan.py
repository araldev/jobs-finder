"""Integration tests for the FastAPI `lifespan` of `build_app`.

Spec: REQ-013 (scraper is ready when the first request hits), REQ-006
(app starts and serves).

The composition root uses FastAPI's `lifespan` to enter the default
`LinkedInPlaywrightScraper` (launch Chromium) at app startup and close
it at shutdown. Without this, the scraper's `_browser` is `None` at
request time and the first `/jobs/linkedin` call crashes with
`AttributeError: 'NoneType' object has no attribute 'new_context'`.

We use `asgi_lifespan.LifespanManager` (the standard pattern for
exercising a FastAPI lifespan from an `httpx.AsyncClient` test) and
mock `__aenter__` / `__aexit__` so tests do NOT need Chromium
installed and do NOT contact LinkedIn. The mock simulates a successful
open by setting `self._browser` to a marker object; the test asserts
that the lifespan calls the mock.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.presentation.app_factory import build_app


class _FakeJobSearchPort:
    """Minimal stand-in used to prove the lifespan is a no-op for non-LinkedIn ports."""

    def __init__(self) -> None:
        self.search_calls = 0

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Any]:
        self.search_calls += 1
        return []


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` whose lifespan is exercised by `LifespanManager`.

    `httpx.ASGITransport` does not run the ASGI lifespan on its own;
    `LifespanManager` is the community-standard helper to do that.
    """
    async with (
        LifespanManager(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


async def test_build_app_default_lifespan_opens_default_scraper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`build_app()` (no `use_case=`) must open the default
    `LinkedInPlaywrightScraper` at lifespan startup so its `_browser`
    is set before any request reaches the route handler.

    Bug (pre-fix): the scraper was constructed but never entered as an
    async context manager, so `_browser` stayed `None` and the first
    request crashed with `AttributeError`.
    """
    enter_calls: list[LinkedInPlaywrightScraper] = []
    exit_calls: list[LinkedInPlaywrightScraper] = []

    async def fake_aenter(self: LinkedInPlaywrightScraper) -> LinkedInPlaywrightScraper:
        enter_calls.append(self)
        # Simulate the real `__aenter__` side-effect: set `_browser`.
        self._browser = object()
        return self

    async def fake_aexit(self: LinkedInPlaywrightScraper, *exc: object) -> None:
        exit_calls.append(self)
        self._browser = None

    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aenter__", fake_aenter)
    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aexit__", fake_aexit)

    # Build a fresh app (default use case). Build it AFTER the monkeypatch
    # so the constructor's references are correct.
    app = build_app()

    # LifespanManager runs the startup phase on `async with` enter and
    # the shutdown phase on exit. We just need to enter the context to
    # verify startup, and check the post-shutdown state at the end.
    async with _client_with_lifespan(app):
        # Startup assertions.
        assert len(enter_calls) == 1, (
            "Lifespan startup did not call __aenter__ on the default "
            "LinkedInPlaywrightScraper; first request would crash with "
            "AttributeError: 'NoneType' object has no attribute 'new_context'"
        )
        port = app.state.use_case._port
        assert port is enter_calls[0], (
            "Lifespan opened a different scraper instance than the one the use case holds."
        )
        assert port._browser is not None, (
            "Scraper._browser is None after lifespan startup; the route "
            "would crash on the first request."
        )

    # Shutdown assertions (after the context manager exits).
    assert len(exit_calls) == 1, (
        "Lifespan shutdown did not call __aexit__ on the default "
        "LinkedInPlaywrightScraper; the browser would leak across restarts."
    )
    assert port._browser is None, (
        "Scraper._browser should be cleared by __aexit__; a stale "
        "reference would confuse the next startup."
    )


async def test_build_app_with_explicit_use_case_lifespan_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`build_app(use_case=...)` (tests inject a `_FakeJobSearchPort`) must
    NOT call `__aenter__` on the port in the lifespan.

    Reason: tests do not have Chromium installed, and the fake port is
    not a Playwright object. The lifespan must only manage the lifecycle
    of the default `LinkedInPlaywrightScraper`.
    """
    enter_calls: list[LinkedInPlaywrightScraper] = []

    async def fake_aenter(self: LinkedInPlaywrightScraper) -> LinkedInPlaywrightScraper:
        enter_calls.append(self)
        return self

    async def fake_aexit(self: LinkedInPlaywrightScraper, *exc: object) -> None:
        return None

    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aenter__", fake_aenter)
    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aexit__", fake_aexit)

    fake_port = _FakeJobSearchPort()
    use_case = SearchLinkedInJobsUseCase(port=fake_port)
    app = build_app(use_case=use_case)

    async with _client_with_lifespan(app):
        assert len(enter_calls) == 0, (
            "Lifespan should not call __aenter__ on a non-LinkedIn port; "
            "tests inject _FakeJobSearchPort and Chromium is not available."
        )
