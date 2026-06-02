"""FastAPI app factory — composition root for the presentation layer.

Spec: REQ-006, REQ-017..REQ-022.

`build_app` wires:
  - The use case (injected via `use_case=` for tests; default builds a
    real `LinkedInPlaywrightScraper` for production).
  - `RequestIdMiddleware` (REQ-020).
  - The exception handlers (`JobSearchError` -> 502, validation -> 422).
  - The routers (`/health`, `/jobs/linkedin`).

The use case is exposed to routes via `app.state.use_case`; routes
resolve it through the `get_use_case` dependency defined in
`presentation/routes/linkedin.py`. Tests always pass `use_case=...`
explicitly; the default branch exists for the production `uvicorn`
entry point (`main.py`, T-009).
"""

from __future__ import annotations

from fastapi import FastAPI

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    ScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from jobs_finder.presentation.exception_handlers import (
    register_exception_handlers,
)
from jobs_finder.presentation.middleware import RequestIdMiddleware
from jobs_finder.presentation.routes import health as health_routes
from jobs_finder.presentation.routes import linkedin as linkedin_routes


def build_app(
    use_case: SearchLinkedInJobsUseCase | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    """Construct a configured FastAPI app.

    Args:
        use_case: The use case to expose via `app.state.use_case`. If
            `None`, a default use case is constructed over a
            `LinkedInPlaywrightScraper` with a default throttle. Tests
            always pass an explicit `use_case`.
        settings: Optional runtime configuration. Used by the default
            branch to build the scraper and the throttle. If `None`,
            the default `Settings()` is loaded.

    Returns:
        A `FastAPI` instance with middleware, exception handlers, and
        routers installed.
    """
    if use_case is None:
        effective_settings = settings if settings is not None else Settings()
        scraper = LinkedInPlaywrightScraper(
            throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
            settings=ScraperSettings(
                user_agent=effective_settings.user_agent,
                timeout_ms=effective_settings.request_timeout_ms,
            ),
        )
        use_case = SearchLinkedInJobsUseCase(port=scraper)

    app = FastAPI(title="jobs-finder")
    app.state.use_case = use_case
    # Expose the underlying port for diagnostics; routes use the use case.
    app.state.job_search_port = getattr(use_case, "_port", None)

    # Middleware (outermost first).
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers.
    register_exception_handlers(app)

    # Routers.
    app.include_router(health_routes.router)
    app.include_router(linkedin_routes.router)

    return app
