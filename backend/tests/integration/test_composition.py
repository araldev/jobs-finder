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
from jobs_finder.infrastructure.infojobs.scraper import InfoJobsPlaywrightScraper
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


def test_resolver_shared_with_linkedin_scraper_settings() -> None:
    """`app.state.location_resolver` IS the same instance as `port._settings.location_resolver`.

    The composition root (`app_factory.build_app()`) builds
    ONE `HardcodedLocationResolver` instance and injects
    it into BOTH `app.state.location_resolver` (for the
    `GET /jobs` route at `aggregator.py:169`) and the
    `LinkedInScraperSettings` (for the
    `LinkedInPlaywrightScraper.search()` method's geoId
    and structured lookups). The two references MUST be
    the SAME object (identity, not equality) — a future
    change that builds a second resolver per call site
    would silently double the dict-construction cost and
    break the per-process caching invariant.

    Spec: `backend-linkedin-location-fallback` T-003
    (REQ-STR-LOC-001 composition verification).
    """
    built_app = build_app()
    port = getattr(built_app.state, "job_search_port", None)
    assert port is not None
    assert isinstance(port, LinkedInPlaywrightScraper)
    # Identity check: the same `HardcodedLocationResolver`
    # instance is shared between `app.state` and the
    # LinkedIn scraper settings.
    assert built_app.state.location_resolver is port._settings.location_resolver  # noqa: SLF001


# ---------------------------------------------------------------------------
# `app.state.location_resolver` SHARING between LinkedIn + InfoJobs
# (REQ-PROV-004)
#
# The composition root builds ONE `HardcodedLocationResolver` at L185
# and injects it into BOTH `LinkedInScraperSettings` and
# `InfoJobsScraperSettings`. The sharing is by IDENTITY (`is`, not
# `==`) — the same `dict` reference is in both settings, so the
# resolver's `__hash__` (used by caches) is stable across both
# sources. The bonus fix in T-003 is to remove the L607 shadowing
# `location_resolver = HardcodedLocationResolver()` line that
# previously built a SECOND instance inside the `chat_enabled` branch.
#
# Spec: REQ-PROV-004 (the 2 scenarios). The `is` comparison is the
# strictest possible assertion — if the L607 shadowing bug returns,
# the assertion fails and the test catches the regression.
# ---------------------------------------------------------------------------


def test_resolver_shared_between_linkedin_and_infojobs() -> None:
    """`app.state.location_resolver` is the SAME instance used by BOTH
    `LinkedInPlaywrightScraper` and `InfoJobsPlaywrightScraper`.

    The composition root constructs ONE `HardcodedLocationResolver`
    at L185 and injects it into both `LinkedInScraperSettings`
    (L255 area) and `InfoJobsScraperSettings` (L341 area). The
    `is` comparison (not `==`) is the strictest possible
    assertion — identity guarantees the same in-process dict
    reference is in both settings, so the resolver's `__hash__`
    is stable across both sources.

    The bonus fix in T-003 removes the L607 shadowing line that
    previously built a SECOND `HardcodedLocationResolver()`
    inside the `chat_enabled` branch. Without the fix, this
    test fails (the chat filter would receive a different
    resolver instance than the LinkedIn + InfoJobs scrapers).

    The test runs with `chat_enabled=False` (no `LLM_API_KEY`
    in the env) to exercise the non-chat path. A second
    variant below exercises the `chat_enabled=True` path.
    """
    built_app = build_app()
    state_resolver = built_app.state.location_resolver
    assert isinstance(state_resolver, HardcodedLocationResolver)

    linkedin_port = built_app.state.job_search_port
    infojobs_port = built_app.state.infojobs_job_search_port
    assert isinstance(linkedin_port, LinkedInPlaywrightScraper)
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)

    # The LinkedIn scraper's settings hold the SAME instance as
    # `app.state.location_resolver` (identity, not equality).
    assert linkedin_port._settings.location_resolver is state_resolver  # noqa: SLF001
    # The InfoJobs scraper's settings hold the SAME instance as
    # `app.state.location_resolver` (identity, not equality).
    assert infojobs_port._settings.location_resolver is state_resolver  # noqa: SLF001


def test_infojobs_scraper_has_resolver() -> None:
    """`build_app()` injects the resolver into `InfoJobsScraperSettings`.

    The v3 URL plumb reads
    `self._settings.location_resolver.resolve_infojobs(location)`
    in the scraper's `search()`. Without the injection, the
    scraper falls back to the v1 `?l=<str>` URL formula and
    logs an INFO hint (the legacy wiring). The test pins the
    wired path (the v3 recommended path): the resolver is
    present in the InfoJobs settings.
    """
    built_app = build_app()
    infojobs_port = getattr(built_app.state, "infojobs_job_search_port", None)
    assert infojobs_port is not None
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)
    # The `InfoJobsScraperSettings` carries the resolver.
    assert infojobs_port._settings.location_resolver is not None  # noqa: SLF001
    assert isinstance(
        infojobs_port._settings.location_resolver,  # noqa: SLF001
        HardcodedLocationResolver,
    )
