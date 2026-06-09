"""Integration tests for the composition root (`main.py`).

Spec: REQ-005, REQ-006.
- `from jobs_finder.main import app` returns a `FastAPI` instance.
- `app.title == "jobs-finder"`.
- `load_settings()` returns a `Settings` with the documented defaults.
- Importing `main` does NOT launch a real Playwright browser (it only
  constructs a `LinkedInPlaywrightScraper`, which is lazy — the browser
  is launched only when `async with scraper:` is entered).
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI

from jobs_finder.infrastructure.config import Settings, load_settings
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.infrastructure.location.hardcoded_resolver import (
    HardcodedLocationResolver,
)
from jobs_finder.main import app
from jobs_finder.presentation.app_factory import build_app
from jobs_finder.presentation.middleware import RequestIdMiddleware

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------


def test_app_is_a_fastapi_instance() -> None:
    """`from jobs_finder.main import app` returns a `FastAPI` instance."""
    assert isinstance(app, FastAPI)


def test_app_title_is_jobs_finder() -> None:
    """The composition root's app title is the project name."""
    assert app.title == "jobs-finder"


def test_app_has_jobs_linkedin_route() -> None:
    """The composition root exposes `/jobs/linkedin`."""
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/jobs/linkedin" in paths


def test_app_has_health_route() -> None:
    """The composition root exposes `/health`."""
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/health" in paths


def test_app_has_request_id_middleware() -> None:
    """The composition root installs `RequestIdMiddleware`."""
    # `m.cls` is typed as a generic factory in Starlette, but at runtime
    # it IS the class. Cast to a plain `type` so mypy strict accepts
    # the identity comparison.
    middleware_classes = [cast("type", m.cls) for m in app.user_middleware]
    assert RequestIdMiddleware in middleware_classes


# ---------------------------------------------------------------------------
# Settings (load_settings)
# ---------------------------------------------------------------------------


def test_load_settings_returns_a_settings_instance() -> None:
    """`load_settings()` returns a `Settings` instance."""
    settings = load_settings()
    assert isinstance(settings, Settings)


def test_load_settings_defaults_match_documentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults are exactly what the design documents.

    Env vars are explicitly cleared in this test so the assertions pin the
    class-level defaults, not whatever happens to be set in the runner's
    environment.
    """
    for env_name in (
        "LINKEDIN_THROTTLE_SECONDS",
        "LINKEDIN_USER_AGENT",
        "LINKEDIN_HEADLESS",
        "LINKEDIN_REQUEST_TIMEOUT_MS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = load_settings()

    assert settings.throttle_seconds == 3.0
    assert settings.headless is True
    assert settings.request_timeout_ms == 10_000
    # The user agent is a non-empty modern Chrome fingerprint.
    assert isinstance(settings.user_agent, str)
    assert len(settings.user_agent) > 0
    assert "Mozilla" in settings.user_agent


def test_load_settings_env_overrides_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting `LINKEDIN_*` env vars overrides the documented defaults.

    This proves the env wiring is live: the class is a `BaseSettings` and
    not a frozen dataclass.
    """
    monkeypatch.setenv("LINKEDIN_THROTTLE_SECONDS", "7.5")
    monkeypatch.setenv("LINKEDIN_HEADLESS", "false")
    monkeypatch.setenv("LINKEDIN_REQUEST_TIMEOUT_MS", "30000")

    settings = load_settings()

    assert settings.throttle_seconds == 7.5
    assert settings.headless is False
    assert settings.request_timeout_ms == 30_000


# ---------------------------------------------------------------------------
# No real Playwright browser is launched at import time
# ---------------------------------------------------------------------------


def test_importing_main_does_not_launch_a_browser() -> None:
    """Importing `main` (and therefore `app`) does NOT launch Chromium.

    The default branch of `build_app()` constructs a `LinkedInPlaywrightScraper`
    instance, but the scraper is lazy: the browser is only launched inside
    `async with scraper:`. This test asserts the scraper object exists but
    has no live browser reference — so no Chromium process was spawned.
    """
    port = getattr(app.state, "job_search_port", None)
    assert port is not None
    assert isinstance(port, LinkedInPlaywrightScraper)
    # The scraper has not been entered: no browser reference.
    assert port._browser is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# `HardcodedLocationResolver` injection (REQ-LOC-002, T-007)
#
# The composition root (`app_factory.build_app()`) MUST
# instantiate a `HardcodedLocationResolver` and inject it
# into the `LinkedInScraperSettings` (which the
# `LinkedInPlaywrightScraper` reads in its constructor). The
# resolver is built ALWAYS — not gated by `chat_enabled` —
# so the `GET /jobs` route can resolve `location` to
# `geoId` for the LinkedIn scraper regardless of the chat
# feature's on/off state.
# ---------------------------------------------------------------------------


def test_linkedin_scraper_has_resolver() -> None:
    """`build_app()` constructs a `LinkedInPlaywrightScraper` with a `location_resolver`.

    The `HardcodedLocationResolver` is built at composition-
    root time and passed to `LinkedInScraperSettings` via
    the `location_resolver` kwarg. The scraper's
    `_settings.location_resolver` MUST be a non-`None`
    `HardcodedLocationResolver` instance.
    """
    built_app = build_app()
    port = getattr(built_app.state, "job_search_port", None)
    assert port is not None
    assert isinstance(port, LinkedInPlaywrightScraper)
    # The `LinkedInScraperSettings` carries the resolver.
    assert port._settings.location_resolver is not None  # noqa: SLF001
    assert isinstance(
        port._settings.location_resolver,  # noqa: SLF001
        HardcodedLocationResolver,
    )


def test_resolver_built_when_chat_disabled() -> None:
    """The resolver is built even when `chat_enabled=False`.

    The resolver is built in the `build_app()` default
    branch BEFORE the chat-specific code path; it is NOT
    gated by `chat_enabled`. This pins the spec invariant
    "`HardcodedLocationResolver` se construye SIEMPRE" (REQ-
    LOC-002 scenario 3).
    """
    # No `LLM_API_KEY` in the env → `chat_enabled=False`.
    built_app = build_app()
    port = getattr(built_app.state, "job_search_port", None)
    assert port is not None
    assert isinstance(port, LinkedInPlaywrightScraper)
    # The resolver is present regardless of the chat state.
    assert port._settings.location_resolver is not None  # noqa: SLF001
    assert isinstance(
        port._settings.location_resolver,  # noqa: SLF001
        HardcodedLocationResolver,
    )
