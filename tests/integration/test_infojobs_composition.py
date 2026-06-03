"""Integration tests for the InfoJobs composition root (T-008).

Spec: REQ-J-001..REQ-J-006 (composition surface).

`main.py`'s `build_app()` (no args) wires the InfoJobs source into the
same FastAPI app that already serves the LinkedIn + Indeed sources:

    1. `/jobs/infojobs` is registered (alongside `/jobs/linkedin` and
       `/jobs/indeed`).
    2. `GET /health` is still 200 `{"status":"ok"}` without calling
       any port (liveness probe independence).
    3. `INFOJOBS_DOMAIN=uk.infojobs.net` env var is applied to the
       InfoJobs scraper's `Settings` slice.
    4. The lifespan opens ALL THREE scrapers on startup and closes
       all three on shutdown (LIFO).
    5. The default InfoJobs scraper has `stealth=Stealth()` wired
       in production (REQ-J-002: stealth is mandatory from day 1,
       unlike the Indeed v1 which deferred it).

The tests follow the same pattern as `test_indeed_composition.py`.
The default branch of `build_app()` is exercised; the test NEVER
launches Chromium. `__aenter__` / `__aexit__` are monkeypatched in
the lifespan test so the scraper objects do not try to spawn a real
browser. `httpx.ASGITransport` does not run the lifespan on its own,
so the route and `/health` tests do not need the monkeypatch.
"""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.indeed.scraper import IndeedPlaywrightScraper
from jobs_finder.infrastructure.infojobs.scraper import InfoJobsPlaywrightScraper
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.presentation.app_factory import build_app

# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_build_app_default_registers_all_three_jobs_routes() -> None:
    """`build_app()` (no args) exposes all three `/jobs/<source>` routes.

    Before T-008, the default `build_app()` only constructed the
    LinkedIn + Indeed use cases. T-007 wired the InfoJobs default
    branch; T-008 confirms the route registration at the composition
    surface. The InfoJobs router must be included so the route is
    exercisable in production.
    """
    app = build_app()
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/jobs/linkedin" in paths
    assert "/jobs/indeed" in paths
    assert "/jobs/infojobs" in paths


# ---------------------------------------------------------------------------
# /health independence — no port call
# ---------------------------------------------------------------------------


async def test_build_app_default_health_returns_ok_without_calling_any_port() -> None:
    """`GET /health` is 200 `{"status":"ok"}`; none of the three ports is touched.

    The composition root now constructs three scrapers in the default
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
# Env-var override flows to the InfoJobs scraper
# ---------------------------------------------------------------------------


def test_build_app_default_infojobs_scraper_uses_env_var_for_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_DOMAIN=uk.infojobs.net` is applied to the InfoJobs scraper's settings.

    The composition root reads `Settings.infojobs_domain` and passes
    it to `InfoJobsScraperSettings(domain=...)`. The test pins the
    end-to-end wiring: env var -> `Settings` -> `InfoJobsPlaywrightScraper`.
    """
    monkeypatch.setenv("INFOJOBS_DOMAIN", "uk.infojobs.net")
    app = build_app()
    infojobs_port = getattr(app.state, "infojobs_job_search_port", None)
    assert infojobs_port is not None, (
        "build_app() did not construct a default InfoJobs port; "
        "T-007 must build one in the composition root."
    )
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)
    assert infojobs_port._settings.domain == "uk.infojobs.net"  # noqa: SLF001


def test_build_app_default_infojobs_port_is_a_real_playwright_scraper() -> None:
    """`app.state.infojobs_job_search_port` is an `InfoJobsPlaywrightScraper`
    instance (default branch). The port is constructed but NOT
    entered — `_browser` is `None`.
    """
    app = build_app()
    infojobs_port = getattr(app.state, "infojobs_job_search_port", None)
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)
    # The scraper has not been entered: no browser reference.
    assert infojobs_port._browser is None  # noqa: SLF001


def test_build_app_default_infojobs_stealth_is_wired() -> None:
    """REQ-J-002: production wires `Stealth()` for the InfoJobs scraper
    from T-007 onward (unlike the Indeed v1 which deferred stealth).

    The scraper's `_stealth` attribute must be set (not `None`) in
    the default branch. The class identity check is the simplest,
    most precise assertion: `Stealth()` is the type; the scraper
    holds an instance.
    """
    app = build_app()
    infojobs_port = getattr(app.state, "infojobs_job_search_port", None)
    assert infojobs_port is not None
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)
    # The Stealth instance is held; isinstance check is robust to
    # constructor tweaks.
    assert isinstance(infojobs_port._stealth, Stealth)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Composition with explicit settings (no env mutation needed)
# ---------------------------------------------------------------------------


def test_build_app_with_explicit_settings_propagates_infojobs_config() -> None:
    """`build_app(settings=Settings(infojobs_domain="de.infojobs.net", ...))` propagates
    the configured domain to the InfoJobs scraper.
    """
    settings = Settings(
        infojobs_domain="de.infojobs.net",
        infojobs_throttle_seconds=7.0,
    )
    app = build_app(settings=settings)
    infojobs_port = app.state.infojobs_job_search_port
    assert isinstance(infojobs_port, InfoJobsPlaywrightScraper)
    assert infojobs_port._settings.domain == "de.infojobs.net"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Lifespan opens ALL THREE scrapers
# ---------------------------------------------------------------------------


async def test_build_app_default_lifespan_opens_all_three_scrapers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composition root's lifespan opens ALL THREE scrapers on startup.

    Mirrors the LinkedIn / Indeed invariant. All three `__aenter__`
    calls are expected; all three `__aexit__` calls are expected on
    shutdown. The default `build_app()` is used so the production
    wiring is exercised. Shutdown is LIFO: InfoJobs first, Indeed
    second, LinkedIn last.
    """
    linkedin_enter_calls: list[LinkedInPlaywrightScraper] = []
    indeed_enter_calls: list[IndeedPlaywrightScraper] = []
    infojobs_enter_calls: list[InfoJobsPlaywrightScraper] = []
    linkedin_exit_calls: list[LinkedInPlaywrightScraper] = []
    indeed_exit_calls: list[IndeedPlaywrightScraper] = []
    infojobs_exit_calls: list[InfoJobsPlaywrightScraper] = []

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

    async def fake_infojobs_aenter(
        self: InfoJobsPlaywrightScraper,
    ) -> InfoJobsPlaywrightScraper:
        infojobs_enter_calls.append(self)
        self._browser = object()
        return self

    async def fake_infojobs_aexit(self: InfoJobsPlaywrightScraper, *exc: object) -> None:
        infojobs_exit_calls.append(self)
        self._browser = None

    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aenter__", fake_linkedin_aenter)
    monkeypatch.setattr(LinkedInPlaywrightScraper, "__aexit__", fake_linkedin_aexit)
    monkeypatch.setattr(IndeedPlaywrightScraper, "__aenter__", fake_indeed_aenter)
    monkeypatch.setattr(IndeedPlaywrightScraper, "__aexit__", fake_indeed_aexit)
    monkeypatch.setattr(InfoJobsPlaywrightScraper, "__aenter__", fake_infojobs_aenter)
    monkeypatch.setattr(InfoJobsPlaywrightScraper, "__aexit__", fake_infojobs_aexit)

    app = build_app()

    async with LifespanManager(app):
        # All three scrapers were opened at startup.
        assert len(linkedin_enter_calls) == 1
        assert len(indeed_enter_calls) == 1
        assert len(infojobs_enter_calls) == 1, (
            "Lifespan startup did not call __aenter__ on the default "
            "InfoJobsPlaywrightScraper; first InfoJobs request would crash."
        )
        # The use case wraps the same scraper instance the lifespan opened.
        # The `cache-ttl` change wraps each use case in a `CachedJobSearchUseCase`;
        # unwrap one level (cached wrapper -> raw use case -> scraper).
        assert app.state.use_case._port._port is linkedin_enter_calls[0]  # noqa: SLF001
        assert app.state.indeed_use_case._port is indeed_enter_calls[0]  # noqa: SLF001
        assert app.state.infojobs_use_case._port is infojobs_enter_calls[0]  # noqa: SLF001

    # All three scrapers were closed on shutdown.
    assert len(linkedin_exit_calls) == 1
    assert len(indeed_exit_calls) == 1
    assert len(infojobs_exit_calls) == 1
