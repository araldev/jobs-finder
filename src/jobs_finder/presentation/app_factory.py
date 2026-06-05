"""FastAPI app factory — composition root for the presentation layer.

Spec: REQ-006, REQ-017..REQ-022, REQ-I-012, REQ-I-013, REQ-I-014,
REQ-A-001..REQ-A-006 (aggregator).

`build_app` wires:
  - The LinkedIn use case (injected via `use_case=` for tests; default
    builds a real `LinkedInPlaywrightScraper` for production).
  - The Indeed use case (injected via `indeed_use_case=` for tests;
    default builds a real `IndeedPlaywrightScraper` for production —
    T-008 wired the default branch so `app = build_app()` exposes
    BOTH sources).
  - The InfoJobs use case (injected via `infojobs_use_case=` for tests;
    default builds a real `InfoJobsPlaywrightScraper` for production —
    T-008 wired the default branch so `app = build_app()` exposes
    ALL THREE sources).
  - The aggregator use case (injected via `aggregator_use_case=` for
    tests; default builds a `SearchAllSourcesUseCase` that wraps
    the 3 per-source use cases — T-002 of the jobs-aggregator-endpoint
    change wires this).
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
  - The routers (`/health`, `/jobs/linkedin`, `/jobs/indeed`,
    `/jobs/infojobs`, `/jobs`).

The LinkedIn use case is exposed to routes via `app.state.use_case`;
the Indeed use case is exposed via `app.state.indeed_use_case`;
the InfoJobs use case is exposed via `app.state.infojobs_use_case`;
the aggregator use case is exposed via `app.state.aggregator_use_case`.
Routes resolve them through their `get_*_use_case` dependencies.
Tests pass use cases explicitly when they need to short-circuit
the default branches; otherwise the default branches build real
Playwright scrapers from `Settings` so `app = build_app()` is the
production-ready composition root.

T-008 also extends the lifespan to open ALL THREE default scrapers
on startup and close them on shutdown. Each scraper's `__aenter__` /
`__aexit__` is independent — a test that injects a fake port for one
source does not affect the other sources' lifespan behavior.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import MappingProxyType

import redis.asyncio as redis_async
import redis.exceptions
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import NoOpRateLimiter, RateLimitPort
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.application.usecases.search_indeed_jobs import (
    RawSearchJobsUseCase as RawIndeedJobsUseCase,
)
from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    RawSearchJobsUseCase as RawInfoJobsJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_linkedin_jobs import (
    RawLinkedInJobsUseCase,
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.cache._factory import build_cache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.indeed.scraper import (
    IndeedPlaywrightScraper,
    IndeedScraperSettings,
)
from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle
from jobs_finder.infrastructure.infojobs.scraper import (
    InfoJobsPlaywrightScraper,
    InfoJobsScraperSettings,
)
from jobs_finder.infrastructure.infojobs.throttle import InfoJobsAsyncThrottle
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    LinkedInScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.presentation.exception_handlers import (
    register_exception_handlers,
)
from jobs_finder.presentation.logging_config import configure_logging
from jobs_finder.presentation.middleware import (
    LogOnRequestMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from jobs_finder.presentation.routes import aggregator as aggregator_routes
from jobs_finder.presentation.routes import health as health_routes
from jobs_finder.presentation.routes import indeed as indeed_routes
from jobs_finder.presentation.routes import infojobs as infojobs_routes
from jobs_finder.presentation.routes import linkedin as linkedin_routes


def build_app(  # noqa: PLR0915
    use_case: SearchLinkedInJobsUseCase | None = None,
    *,
    indeed_use_case: IndeedSearchJobsUseCase | None = None,
    infojobs_use_case: InfoJobsSearchJobsUseCase | None = None,
    aggregator_use_case: SearchAllSourcesUseCase | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Construct a configured FastAPI app with ALL THREE source routes AND
    the aggregator route wired.

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
        infojobs_use_case: The InfoJobs use case to expose via
            `app.state.infojobs_use_case`. If `None`, the
            `/jobs/infojobs` route returns 500 because
            `app.state.infojobs_use_case` is not set. Production
            callers (T-008) must pass it explicitly.
        aggregator_use_case: The aggregator use case to expose via
            `app.state.aggregator_use_case`. If `None`, the default
            branch builds a `SearchAllSourcesUseCase` from the 3
            per-source use cases. Tests pass an explicit
            `aggregator_use_case` to inject a custom orchestrator.
        settings: Optional runtime configuration. Used by the default
            branch to build the scraper and the throttle, and to wire
            CORS / logging. If `None`, the default `Settings()` is loaded.

    Returns:
        A `FastAPI` instance with a `lifespan` that opens the default
        scrapers (when the default use cases are in effect) at
        startup and closes them at shutdown, plus the middleware,
        exception handlers, and routers (including the aggregator).
    """
    effective_settings = settings if settings is not None else Settings()

    # Logging MUST be configured before any middleware or route runs
    # so that log records emitted during request processing are
    # formatted as JSON (or plain) with the request_id bound.
    configure_logging(effective_settings)

    # T-005 (persistent-cache): when `cache_backend == "redis"`,
    # build a SINGLE shared `redis.asyncio.Redis` client here.
    # The 3 `build_cache(...)` calls below all receive this same
    # client (single connection pool, 3 logical caches). The
    # lifespan block further below pings it on startup (fail-fast
    # on `ConnectionError`) and closes it on shutdown.
    # When `cache_backend == "memory"` (default), this stays `None`
    # and the 3 caches are independent `InMemoryTTLCache`s.
    redis_client: redis_async.Redis | None = None
    if effective_settings.cache_backend == "redis":
        redis_client = redis_async.from_url(  # type: ignore[no-untyped-call]
            effective_settings.cache_redis_url,
            db=effective_settings.cache_redis_db,
        )

    if use_case is None:
        scraper = LinkedInPlaywrightScraper(
            throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
            # REQ-L-008: `LinkedInScraperSettings` was renamed from the
            # in-module `ScraperSettings`; the two new env-driven
            # fields (`linkedin_max_pages`, `linkedin_inter_page_delay_seconds`)
            # are the pagination knobs (REQ-L-007, REQ-L-009).
            settings=LinkedInScraperSettings(
                user_agent=effective_settings.user_agent,
                timeout_ms=effective_settings.request_timeout_ms,
                max_pages=effective_settings.linkedin_max_pages,
                inter_page_delay_seconds=effective_settings.linkedin_inter_page_delay_seconds,
            ),
        )
        raw_use_case = RawLinkedInJobsUseCase(port=scraper)
        # T-003: wrap the raw use case in a `CachedJobSearchUseCase`
        # so repeated identical queries within the TTL window return
        # the cached `list[Job]` without invoking the Playwright
        # scraper. The wrapper exposes `search(...)` which the route
        # calls (REQ-C-003 — the route sets the `X-Cache: HIT|MISS`
        # response header from the wrapper's `SearchResult.cache_status`).
        # T-005 (persistent-cache): the cache is now built via the
        # `build_cache` factory so it selects `InMemoryTTLCache` or
        # `RedisCache` per `settings.cache_backend`. The shared
        # `redis_client` is passed in for the Redis branch.
        linkedin_cache = build_cache(effective_settings, source="linkedin", client=redis_client)
        use_case = CachedJobSearchUseCase(
            port=raw_use_case,
            cache=linkedin_cache,
            source="linkedin",
        )

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
        raw_indeed_use_case = RawIndeedJobsUseCase(port=indeed_scraper)
        # T-004 (cache-ttl): wrap the raw Indeed use case in its
        # OWN `CachedJobSearchUseCase` so the Indeed cache is
        # independent of the LinkedIn + InfoJobs caches (REQ-C-005
        # — per-source isolation). T-005 (persistent-cache): the
        # cache is built via `build_cache` so the same factory
        # selects the backend.
        indeed_cache = build_cache(effective_settings, source="indeed", client=redis_client)
        indeed_use_case = IndeedSearchJobsUseCase(
            port=raw_indeed_use_case,
            cache=indeed_cache,
            source="indeed",
        )

    if infojobs_use_case is None:
        # T-007: the default branch builds the InfoJobs scraper +
        # use case. The InfoJobs scraper uses its OWN
        # `InfoJobsAsyncThrottle` (per-instance lock, independent of
        # the LinkedIn + Indeed throttles) and its OWN
        # `InfoJobsScraperSettings` (sourced from the
        # `effective_settings.infojobs_*` fields). The
        # `SearchJobsUseCase` class is the source-neutral name
        # (REQ-J-004) — the file path
        # `search_infojobs_jobs.py` provides the per-source binding.
        infojobs_scraper = InfoJobsPlaywrightScraper(
            throttle=InfoJobsAsyncThrottle(
                min_interval_seconds=effective_settings.infojobs_throttle_seconds,
            ),
            settings=InfoJobsScraperSettings(
                user_agent=effective_settings.infojobs_user_agent,
                timeout_ms=effective_settings.infojobs_timeout_ms,
                domain=effective_settings.infojobs_domain,
                max_pages=effective_settings.infojobs_max_pages,
                # REQ-J-003: inter-page pacing is part of v1 (unlike
                # the Indeed v1 which added it later).
                inter_page_delay_seconds=effective_settings.infojobs_inter_page_delay_seconds,
            ),
            # REQ-J-002: production wires `Stealth()` from T-007
            # onward (unlike the Indeed v1 which deferred stealth to
            # a follow-up change). The InfoJobs anti-bot surface
            # (Distil + Geetest) is stricter than Cloudflare, so
            # stealth is required from day 1. Tests pass
            # `stealth=None` (the constructor default) and inject
            # `browser_factory` so the stealth script never runs.
            stealth=Stealth(),
        )
        raw_infojobs_use_case = RawInfoJobsJobsUseCase(port=infojobs_scraper)
        # T-004 (cache-ttl): wrap the raw InfoJobs use case in its
        # OWN `CachedJobSearchUseCase` so the InfoJobs cache is
        # independent of the LinkedIn + Indeed caches (REQ-C-005
        # — per-source isolation). T-005 (persistent-cache): the
        # cache is built via `build_cache` so the same factory
        # selects the backend.
        infojobs_cache = build_cache(effective_settings, source="infojobs", client=redis_client)
        infojobs_use_case = InfoJobsSearchJobsUseCase(
            port=raw_infojobs_use_case,
            cache=infojobs_cache,
            source="infojobs",
        )

    # The lifespan opens ALL THREE default scrapers. When tests
    # inject a use case wrapping a non-`*PlaywrightScraper` port
    # (e.g. `FakeJobSearchPort`), the lifespan is a no-op for that
    # source so the test does not need Chromium installed. The
    # pattern mirrors the LinkedIn pre-T-008 invariant: a use case
    # wrapping a real `*PlaywrightScraper` is opened on startup and
    # closed on shutdown; a use case wrapping anything else is left
    # untouched.
    #
    # T-003 (cache-ttl): the LinkedIn use case is now a
    # `CachedJobSearchUseCase` whose `_port` is the raw use case
    # (`RawLinkedInJobsUseCase`), not the scraper. The lifespan
    # helper unwraps one level: a cached wrapper around a raw
    # use case around a scraper means we follow `.port._port` to
    # reach the scraper. A directly-injected use case (no cache
    # wrapper) has `.port` as the scraper.
    def _unwrap_to_port(candidate: object) -> object | None:
        """Walk one level through a `CachedJobSearchUseCase` to find the inner port.

        Returns the scraper (or any other port) the lifespan should
        open. `None` if the candidate is not a use case at all.
        """
        inner = getattr(candidate, "_port", None)
        if inner is None:
            return None
        # Cached wrapper -> raw use case -> scraper.
        deeper = getattr(inner, "_port", None)
        if deeper is not None:
            return deeper  # type: ignore[no-any-return]
        # Raw use case (or direct port) -> the port itself.
        return inner  # type: ignore[no-any-return]

    raw_linkedin_port = _unwrap_to_port(use_case)
    scraper_for_lifespan: LinkedInPlaywrightScraper | None = (
        raw_linkedin_port if isinstance(raw_linkedin_port, LinkedInPlaywrightScraper) else None
    )
    raw_indeed_port = _unwrap_to_port(indeed_use_case)
    indeed_scraper_for_lifespan: IndeedPlaywrightScraper | None = (
        raw_indeed_port if isinstance(raw_indeed_port, IndeedPlaywrightScraper) else None
    )
    raw_infojobs_port = _unwrap_to_port(infojobs_use_case)
    infojobs_scraper_for_lifespan: InfoJobsPlaywrightScraper | None = (
        raw_infojobs_port if isinstance(raw_infojobs_port, InfoJobsPlaywrightScraper) else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # T-005 (persistent-cache): ping Redis on startup when the
        # backend is `redis`. The ping is fail-fast: a
        # `redis.exceptions.RedisError` (e.g. `ConnectionError`
        # "Connection refused") is re-raised as a `RuntimeError`
        # with a descriptive message so misconfiguration surfaces
        # in container logs at boot, not on the first user request.
        # The 3 `build_cache(...)` calls above already created the
        # 3 `RedisCache` instances; this ping is the connection
        # smoke test.
        if redis_client is not None:
            try:
                await redis_client.ping()
            except redis.exceptions.RedisError as cause:
                raise RuntimeError(
                    f"Redis cache backend selected but cannot connect to "
                    f"{effective_settings.cache_redis_url}: {cause}"
                ) from cause
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
        if infojobs_scraper_for_lifespan is not None:
            # Open the InfoJobs scraper (T-007). Independent of the
            # LinkedIn + Indeed ones — a failure in one source's
            # startup ordering does not affect the other. The three
            # scrapers share a process but each owns its own
            # browser.
            await infojobs_scraper_for_lifespan.__aenter__()
        try:
            yield
        finally:
            # T-005 (persistent-cache): close the shared Redis
            # client on shutdown. Runs FIRST so a slow `aclose()`
            # doesn't delay the LIFO scraper-shutdown order.
            if redis_client is not None:
                await redis_client.aclose()
            if infojobs_scraper_for_lifespan is not None:
                # Close the InfoJobs browser and stop its Playwright
                # driver. Runs FIRST so the InfoJobs shutdown is the
                # first to fire; the order is the reverse of startup
                # (LIFO).
                await infojobs_scraper_for_lifespan.__aexit__(None, None, None)
            if indeed_scraper_for_lifespan is not None:
                # Close the Indeed browser and stop its Playwright driver.
                await indeed_scraper_for_lifespan.__aexit__(None, None, None)
            if scraper_for_lifespan is not None:
                # Close the LinkedIn browser and stop its Playwright driver.
                # Runs LAST so the LinkedIn shutdown is the last to fire.
                await scraper_for_lifespan.__aexit__(None, None, None)

    app = FastAPI(title="jobs-finder", lifespan=lifespan)
    app.state.use_case = use_case
    # Expose the underlying port for diagnostics; routes use the use case.
    # T-003 (cache-ttl): unwrap the cached wrapper if present so
    # `app.state.job_search_port` still points at the scraper (or
    # any other port) for diagnostics, not at the raw use case.
    app.state.job_search_port = _unwrap_to_port(use_case)
    # The Indeed use case defaults to `None`; the route raises a
    # descriptive `RuntimeError` if it's missing so misconfiguration
    # surfaces in tests rather than as a 500.
    app.state.indeed_use_case = indeed_use_case
    app.state.indeed_job_search_port = (
        _unwrap_to_port(indeed_use_case) if indeed_use_case is not None else None
    )
    # The InfoJobs use case defaults to `None`; the route raises a
    # descriptive `RuntimeError` if it's missing so misconfiguration
    # surfaces in tests rather than as a 500.
    app.state.infojobs_use_case = infojobs_use_case
    app.state.infojobs_job_search_port = (
        _unwrap_to_port(infojobs_use_case) if infojobs_use_case is not None else None
    )

    # T-002 (jobs-aggregator-endpoint): the aggregator wraps the 3
    # per-source use cases and runs them in parallel via
    # `asyncio.gather` (see `application/aggregator.py`). The
    # default branch reuses the 3 use cases that the per-source
    # routes use, so the aggregator AUTOMATICALLY inherits the
    # cache-ttl behavior (REQ-C-001..REQ-C-006) without a separate
    # cache: a cache hit on LinkedIn from a prior per-source call is
    # ALSO a cache hit when the aggregator invokes LinkedIn.
    if aggregator_use_case is None:
        aggregator_use_case = SearchAllSourcesUseCase(
            linkedin_use_case=use_case,
            indeed_use_case=indeed_use_case,
            infojobs_use_case=infojobs_use_case,
        )
    app.state.aggregator_use_case = aggregator_use_case

    # Middleware — order matters. Starlette runs middlewares outermost
    # first; the LAST `add_middleware` call wraps everything else.
    # 1. `LogOnRequest` is innermost: it runs inside `RequestId` so
    #    the `ContextVar` is bound when it logs.
    # 2. `RateLimit` is next: it runs AFTER `RequestId` in execution
    #    order (because it's added BEFORE `RequestId` in nesting
    #    order) so the 429 body can read `request.state.request_id`.
    # 3. `RequestId` is next: it sets the id and binds the `ContextVar`.
    # 4. `CORS` is outermost: preflights get a request_id echo too.
    #
    # T-002 (rate-limiting): build the limiter directly (no factory
    # yet — the factory lands in T-003 with the optional Redis
    # backend). When `rate_limit_enabled=False`, the middleware is
    # NOT added to the stack — the app's behavior is byte-identical
    # to the pre-T-002 baseline.
    rate_limiter: RateLimitPort
    if effective_settings.rate_limit_enabled:
        rate_limiter = InMemoryTokenBucket(
            capacity=effective_settings.rate_limit_requests,
            window_seconds=effective_settings.rate_limit_window_seconds,
        )
    else:
        rate_limiter = NoOpRateLimiter(
            capacity=effective_settings.rate_limit_requests,
        )

    # Effective exempt set = `settings.rate_limit_exempt_paths` ∪
    # `EXEMPT_UNCONDITIONAL` ∪ FastAPI docs surface. The unconditional
    # set is checked in the middleware itself; the other two are
    # forwarded as kwargs.
    effective_exempt_paths: frozenset[str] = frozenset(
        set(effective_settings.rate_limit_exempt_paths) | {"/docs", "/openapi.json", "/redoc"}
    )

    # Per-route cost map. `MappingProxyType` makes the map immutable
    # at runtime (REQ-RL-006 scenario 4).
    cost_map: MappingProxyType[str, int] = MappingProxyType(
        {
            "/jobs": effective_settings.rate_limit_aggregator_path_cost,
            "/jobs/linkedin": effective_settings.rate_limit_per_source_path_cost,
            "/jobs/indeed": effective_settings.rate_limit_per_source_path_cost,
            "/jobs/infojobs": effective_settings.rate_limit_per_source_path_cost,
        }
    )

    app.add_middleware(LogOnRequestMiddleware)
    if effective_settings.rate_limit_enabled:
        # Added BEFORE `RequestId` in nesting order so it runs AFTER
        # `RequestId` in execution order — the 429 body reads
        # `request.state.request_id` which `RequestId` sets on entry.
        app.add_middleware(
            RateLimitMiddleware,
            limiter=rate_limiter,
            exempt_paths=effective_exempt_paths,
            cost_map=cost_map,
            capacity=effective_settings.rate_limit_requests,
        )
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
    app.include_router(infojobs_routes.router)
    # T-002 (jobs-aggregator-endpoint): the new top-level
    # `GET /jobs` aggregator. Mounted LAST so its `/{source}`-less
    # path is not shadowed by the per-source routers.
    app.include_router(aggregator_routes.router)

    return app
