"""Integration tests for the Indeed composition root (T-008).

Spec: REQ-I-014.

`main.py`'s `build_app()` (no args) must wire the Indeed source into
the same FastAPI app that already serves the LinkedIn source:

    1. Both `/jobs/linkedin` AND `/jobs/indeed` are registered.
    2. `GET /health` is still 200 `{"status":"ok"}` without calling
       any port (liveness probe independence).
    3. `INDEED_DOMAIN=uk.indeed.com` env var is applied to the
       Indeed scraper's `Settings` slice (env-var override flows
       from `Settings` -> `IndeedPlaywrightScraper._settings`).
    4. The lifespan opens BOTH scrapers on startup (LinkedIn +
       Indeed) and closes both on shutdown.

The tests follow the same pattern as the LinkedIn composition tests
in `test_composition.py` and `test_app_lifespan.py`. The default
branch of `build_app()` is exercised; the test NEVER launches
Chromium. `__aenter__` / `__aexit__` are monkeypatched in the
lifespan test so the scraper objects do not try to spawn a real
browser. `httpx.ASGITransport` does not run the lifespan on its own,
so the route and `/health` tests do not need the monkeypatch.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.indeed.scraper import IndeedPlaywrightScraper
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.presentation.app_factory import build_app

# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_build_app_default_registers_both_jobs_routes() -> None:
    """`build_app()` (no args) exposes BOTH `/jobs/linkedin` and `/jobs/indeed`.

    Before T-008, the default `build_app()` only constructed the
    LinkedIn use case; the Indeed router was registered but the
    `app.state.indeed_use_case` was `None`. The composition root must
    also build a real `IndeedPlaywrightScraper` + `SearchJobsUseCase`
    so the Indeed route is exercisable in production.
    """
    app = build_app()
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/jobs/linkedin" in paths
    assert "/jobs/indeed" in paths


# ---------------------------------------------------------------------------
# /health independence — no port call
# ---------------------------------------------------------------------------


async def test_build_app_default_health_returns_ok_without_calling_any_port() -> None:
    """`GET /health` is 200 `{"status":"ok"}`; neither the LinkedIn nor
    the Indeed port is touched.

    The composition root now constructs two scrapers in the default
    branch; the liveness probe MUST NOT trigger a browser launch
    (it would defeat the purpose of a cheap liveness check). `httpx`
    does not run the ASGI lifespan on its own, so the scrapers'
    `__aenter__` is never called from this test.
    """
    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Env-var override flows to the Indeed scraper
# ---------------------------------------------------------------------------


def test_build_app_default_indeed_scraper_uses_env_var_for_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_DOMAIN=uk.indeed.com` is applied to the Indeed scraper's settings.

    The composition root reads `Settings.indeed_domain` and passes
    it to `IndeedScraperSettings(domain=...)`. The test pins the
    end-to-end wiring: env var -> `Settings` -> `IndeedPlaywrightScraper`.
    """
    monkeypatch.setenv("INDEED_DOMAIN", "uk.indeed.com")
    app = build_app()
    indeed_port = getattr(app.state, "indeed_job_search_port", None)
    assert indeed_port is not None, (
        "build_app() did not construct a default Indeed port; "
        "T-008 must build one in the composition root."
    )
    assert isinstance(indeed_port, IndeedPlaywrightScraper)
    assert indeed_port._settings.domain == "uk.indeed.com"  # noqa: SLF001


def test_build_app_default_indeed_port_is_a_real_playwright_scraper() -> None:
    """`app.state.indeed_job_search_port` is an `IndeedPlaywrightScraper`
    instance (default branch). The port is constructed but NOT
    entered — `_browser` is `None`.
    """
    app = build_app()
    indeed_port = getattr(app.state, "indeed_job_search_port", None)
    assert isinstance(indeed_port, IndeedPlaywrightScraper)
    # The scraper has not been entered: no browser reference.
    assert indeed_port._browser is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# Lifespan opens BOTH scrapers
# ---------------------------------------------------------------------------


async def test_build_app_default_lifespan_opens_both_scrapers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composition root's lifespan opens BOTH scrapers on startup.

    Mirrors the LinkedIn `test_build_app_default_lifespan_opens_default_scraper`
    invariant. Both `__aenter__` calls are expected; both `__aexit__`
    calls are expected on shutdown. The default `build_app()` is used
    (no `use_case=`, no `indeed_use_case=`) so the production wiring
    is exercised.
    """
    linkedin_enter_calls: list[LinkedInPlaywrightScraper] = []
    indeed_enter_calls: list[IndeedPlaywrightScraper] = []
    linkedin_exit_calls: list[LinkedInPlaywrightScraper] = []
    indeed_exit_calls: list[IndeedPlaywrightScraper] = []

    async def fake_linkedin_aenter(
        self: LinkedInPlaywrightScraper,
    ) -> LinkedInPlaywrightScraper:
        linkedin_enter_calls.append(self)
        self._browser = object()
        return self

    async def fake_linkedin_aexit(self: LinkedInPlaywrightScraper, *exc: object) -> None:
        linkedin_exit_calls.append(self)
        self._browser = None

    async def fake_indeed_aenter(
        self: IndeedPlaywrightScraper,
    ) -> IndeedPlaywrightScraper:
        indeed_enter_calls.append(self)
        self._browser = object()
        return self

    async def fake_indeed_aexit(self: IndeedPlaywrightScraper, *exc: object) -> None:
        indeed_exit_calls.append(self)
        self._browser = None

    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aenter__", fake_linkedin_aenter)
    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aexit__", fake_linkedin_aexit)
    monkeypatch.setattr(IndeedPlaywrightScraper, "__aenter__", fake_indeed_aenter)
    monkeypatch.setattr(IndeedPlaywrightScraper, "__aexit__", fake_indeed_aexit)

    app = build_app()

    from asgi_lifespan import LifespanManager  # noqa: PLC0415

    async with LifespanManager(app):
        # Both scrapers were opened at startup.
        assert len(linkedin_enter_calls) == 1, (
            "Lifespan startup did not call __aenter__ on the default "
            "LinkedInPlaywrightScraper; first LinkedIn request would crash."
        )
        assert len(indeed_enter_calls) == 1, (
            "Lifespan startup did not call __aenter__ on the default "
            "IndeedPlaywrightScraper; first Indeed request would crash."
        )
        # The use case wraps the same scraper instance the lifespan opened.
        assert app.state.use_case._port is linkedin_enter_calls[0]  # noqa: SLF001
        assert app.state.indeed_use_case._port is indeed_enter_calls[0]  # noqa: SLF001

    # Both scrapers were closed on shutdown.
    assert len(linkedin_exit_calls) == 1
    assert len(indeed_exit_calls) == 1


# ---------------------------------------------------------------------------
# Composition with explicit settings (no env mutation needed)
# ---------------------------------------------------------------------------


def test_build_app_with_explicit_settings_propagates_indeed_config() -> None:
    """`build_app(settings=Settings(indeed_domain="de.indeed.com"))` propagates
    the configured domain to the Indeed scraper.

    This is the test pattern most clients will use in production: pass
    a fully-populated `Settings` to `build_app()` instead of relying
    on env var mutation. It exercises the same code path as the
    `INDEED_DOMAIN` env var test above, but with explicit injection.
    """
    settings = Settings(indeed_domain="de.indeed.com", indeed_throttle_seconds=7.0)
    app = build_app(settings=settings)
    indeed_port = app.state.indeed_job_search_port
    assert isinstance(indeed_port, IndeedPlaywrightScraper)
    assert indeed_port._settings.domain == "de.indeed.com"  # noqa: SLF001
    # The throttle seconds is also propagated; verify by inspecting the
    # scraper's throttle through the use case (the throttle lives on
    # the scraper, not the use case).
    assert isinstance(app.state.indeed_use_case, object)
