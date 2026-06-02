"""FastAPI app factory — composition root for the presentation layer.

Spec: REQ-006, REQ-017..REQ-022, REQ-I-012, REQ-I-013, REQ-I-014.

`build_app` wires:
  - The LinkedIn use case (injected via `use_case=` for tests; default
    builds a real `LinkedInPlaywrightScraper` for production).
  - The Indeed use case (injected via `indeed_use_case=` for tests;
    default builds a real `IndeedPlaywrightScraper` for production —
    T-008 wired the default branch so `app = build_app()` exposes
    BOTH sources).
  - `RequestIdMiddleware` (REQ-020).
  - `LogOnRequestMiddleware` (T-012): emits one INFO line per request
    on `jobs_finder.access` with the bound `request_id`. Added INNER
    of `RequestIdMiddleware` so the `ContextVar` is set when it logs.
  - `CORSMiddleware` (REQ-006, T-012): open CORS in dev
    (`settings.cors_allow_origins = ["*"]`); override in production.
    Added OUTERMOST so OPTIONS preflights get a request_id too.
  - `configure_logging(settings)` (REQ-006, T-012): installs the JSON
    (or plain) formatter and the `RequestIdLogFilter` on the root
    logger BEFORE middleware/route handlers run, so any log emitted
    during request processing carries the right structure.
  - The exception handlers (`JobSearchError` -> 502, validation -> 422).
  - The routers (`/health`, `/jobs/linkedin`, `/jobs/indeed`).

The LinkedIn use case is exposed to routes via `app.state.use_case`;
the Indeed use case is exposed via `app.state.indeed_use_case`. Routes
resolve them through the `get_use_case` and `get_indeed_use_case`
dependencies. Tests pass use cases explicitly when they need to
short-circuit the default branches; otherwise the default branches
build real Playwright scrapers from `Settings` so `app = build_app()`
is the production-ready composition root.

T-008 also extends the lifespan to open BOTH default scrapers on
startup and close BOTH on shutdown. Each scraper's `__aenter__` /
`__aexit__` is independent — a test that injects a fake port for one
source does not affect the other source's lifespan behavior.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.application.usecases.search_indeed_jobs import SearchJobsUseCase
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.indeed.scraper import (
    IndeedPlaywrightScraper,
    IndeedScraperSettings,
)
from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    ScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from jobs_finder.presentation.exception_handlers import (
    register_exception_handlers,
)
from jobs_finder.presentation.logging_config import configure_logging
from jobs_finder.presentation.middleware import (
    LogOnRequestMiddleware,
    RequestIdMiddleware,
)
from jobs_finder.presentation.routes import health as health_routes
from jobs_finder.presentation.routes import indeed as indeed_routes
from jobs_finder.presentation.routes import linkedin as linkedin_routes


def build_app(
    use_case: SearchLinkedInJobsUseCase | None = None,
    *,
    indeed_use_case: SearchJobsUseCase | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Construct a configured FastAPI app with BOTH source routes wired.

    Args:
        use_case: The LinkedIn use case to expose via
            `app.state.use_case`. If `None`, a default use case is
            constructed over a `LinkedInPlaywrightScraper` with a
            default throttle. Tests always pass an explicit `use_case`.
        indeed_use_case: The Indeed use case to expose via
            `app.state.indeed_use_case`. If `None`, the `/jobs/indeed`
            route returns 500 because `app.state.indeed_use_case` is
            not set. Production callers (T-008) must pass it
            explicitly.
        settings: Optional runtime configuration. Used by the default
            branch to build the scraper and the throttle, and to wire
            CORS / logging. If `None`, the default `Settings()` is loaded.

    Returns:
        A `FastAPI` instance with a `lifespan` that opens the default
        `LinkedInPlaywrightScraper` (when the default use case is in
        effect) at startup and closes it at shutdown, plus the
        middleware, exception handlers, and routers.
    """
    effective_settings = settings if settings is not None else Settings()

    # Logging MUST be configured before any middleware or route runs
    # so that log records emitted during request processing are
    # formatted as JSON (or plain) with the request_id bound.
    configure_logging(effective_settings)

    if use_case is None:
        scraper = LinkedInPlaywrightScraper(
            throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
            settings=ScraperSettings(
                user_agent=effective_settings.user_agent,
                timeout_ms=effective_settings.request_timeout_ms,
            ),
        )
        use_case = SearchLinkedInJobsUseCase(port=scraper)

    if indeed_use_case is None:
        # T-008: the default branch now also builds the Indeed
        # scraper + use case, so `app = build_app()` wires BOTH
        # sources. The Indeed scraper uses its OWN `IndeedAsyncThrottle`
        # (per-instance lock, independent of the LinkedIn throttle)
        # and its OWN `IndeedScraperSettings` (sourced from the
        # `effective_settings.indeed_*` fields). The
        # `SearchJobsUseCase` class is the source-neutral name
        # (see T-005 deviation) — the file path
        # `search_indeed_jobs.py` provides the per-source binding.
        indeed_scraper = IndeedPlaywrightScraper(
            throttle=IndeedAsyncThrottle(
                min_interval_seconds=effective_settings.indeed_throttle_seconds,
            ),
            settings=IndeedScraperSettings(
                user_agent=effective_settings.indeed_user_agent,
                timeout_ms=effective_settings.indeed_timeout_ms,
                domain=effective_settings.indeed_domain,
                max_pages=effective_settings.indeed_max_pages,
                # Follow-up to fd51ea1: pace pagination to avoid
                # Cloudflare re-challenges on the 2nd+ request.
                inter_page_delay_seconds=effective_settings.indeed_inter_page_delay_seconds,
            ),
            # REQ-S-002: production wires `Stealth()` so the live
            # scraper evades Cloudflare's bot detection. Tests pass
            # `stealth=None` (the constructor default) and inject
            # `browser_factory` so the stealth script never runs.
            stealth=Stealth(),
        )
        indeed_use_case = SearchJobsUseCase(port=indeed_scraper)

    # The lifespan opens BOTH default scrapers. When tests inject a
    # use case wrapping a non-LinkedIn port (e.g. `FakeJobSearchPort`),
    # the lifespan is a no-op for that source so the test does not
    # need Chromium installed. The pattern mirrors the LinkedIn
    # pre-T-008 invariant: a use case wrapping a real `*PlaywrightScraper`
    # is opened on startup and closed on shutdown; a use case wrapping
    # anything else is left untouched.
    raw_linkedin_port = getattr(use_case, "_port", None)
    scraper_for_lifespan: LinkedInPlaywrightScraper | None = (
        raw_linkedin_port if isinstance(raw_linkedin_port, LinkedInPlaywrightScraper) else None
    )
    raw_indeed_port = getattr(indeed_use_case, "_port", None)
    indeed_scraper_for_lifespan: IndeedPlaywrightScraper | None = (
        raw_indeed_port if isinstance(raw_indeed_port, IndeedPlaywrightScraper) else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if scraper_for_lifespan is not None:
            # Enter the async context manager: launches Chromium and
            # sets `scraper_for_lifespan._browser`. After this returns,
            # the first request can call `port.search(...)` and use the
            # browser.
            await scraper_for_lifespan.__aenter__()
        if indeed_scraper_for_lifespan is not None:
            # Open the Indeed scraper (T-008). Independent of the
            # LinkedIn one — a failure in one source's startup
            # ordering does not affect the other. The two scrapers
            # share a process but each owns its own browser.
            await indeed_scraper_for_lifespan.__aenter__()
        try:
            yield
        finally:
            if indeed_scraper_for_lifespan is not None:
                # Close the Indeed browser and stop its Playwright driver.
                await indeed_scraper_for_lifespan.__aexit__(None, None, None)
            if scraper_for_lifespan is not None:
                # Close the LinkedIn browser and stop its Playwright driver.
                # Runs LAST so the Indeed shutdown runs FIRST; the order is
                # the reverse of startup (LIFO).
                await scraper_for_lifespan.__aexit__(None, None, None)

    app = FastAPI(title="jobs-finder", lifespan=lifespan)
    app.state.use_case = use_case
    # Expose the underlying port for diagnostics; routes use the use case.
    app.state.job_search_port = getattr(use_case, "_port", None)
    # The Indeed use case defaults to `None`; the route raises a
    # descriptive `RuntimeError` if it's missing so misconfiguration
    # surfaces in tests rather than as a 500.
    app.state.indeed_use_case = indeed_use_case
    app.state.indeed_job_search_port = (
        getattr(indeed_use_case, "_port", None) if indeed_use_case is not None else None
    )

    # Middleware — order matters. Starlette runs middlewares outermost
    # first; the LAST `add_middleware` call wraps everything else.
    # 1. `LogOnRequest` is innermost: it runs inside `RequestId` so
    #    the `ContextVar` is bound when it logs.
    # 2. `RequestId` is next: it sets the id and binds the `ContextVar`.
    # 3. `CORS` is outermost: preflights get a request_id echo too.
    app.add_middleware(LogOnRequestMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=effective_settings.cors_allow_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Exception handlers.
    register_exception_handlers(app)

    # Routers.
    app.include_router(health_routes.router)
    app.include_router(linkedin_routes.router)
    app.include_router(indeed_routes.router)

    return app
