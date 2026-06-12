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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import MappingProxyType

import httpx
import redis.asyncio as redis_async
import redis.exceptions
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright_stealth import Stealth  # type: ignore[import-untyped]

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import RateLimitPort
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
)
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
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.aggregator_filters import filter_infojobs_results
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
from jobs_finder.infrastructure.keyword_score import keyword_score
from jobs_finder.infrastructure.linkedin.auth_cookie import (
    JsonLinkedInAuthCookiesAdapter,
    MultiEnvLinkedInAuthCookiesAdapter,
)
from jobs_finder.infrastructure.linkedin.scraper import (
    LinkedInPlaywrightScraper,
    LinkedInScraperSettings,
)
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle
from jobs_finder.infrastructure.llm._factory import build_minimax_llm_client
from jobs_finder.infrastructure.llm._intent import IntentExtractor
from jobs_finder.infrastructure.llm._intent_parser import parse_intent_response
from jobs_finder.infrastructure.location.hardcoded_resolver import (
    HardcodedLocationResolver,
)
from jobs_finder.infrastructure.persistence.sqlite_job_repository import (
    SqliteJobRepository,
)
from jobs_finder.infrastructure.rate_limit._factory import build_rate_limiter
from jobs_finder.infrastructure.scheduler import BackgroundJobScheduler
from jobs_finder.presentation.exception_handlers import (
    register_exception_handlers,
)
from jobs_finder.presentation.logging_config import configure_logging
from jobs_finder.presentation.middleware import (
    ChatRateLimitMiddleware,
    LogOnRequestMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from jobs_finder.presentation.routes import aggregator as aggregator_routes
from jobs_finder.presentation.routes import chat as chat_routes
from jobs_finder.presentation.routes import health as health_routes
from jobs_finder.presentation.routes import indeed as indeed_routes
from jobs_finder.presentation.routes import infojobs as infojobs_routes
from jobs_finder.presentation.routes import linkedin as linkedin_routes

# Module-level logger for the composition root. Used by the
# LinkedIn auth-cookie startup WARNING (T-005 of
# `backend-linkedin-auth`, REQ-LA-SCR-003 — emitted ONCE at
# process start when the operator has not configured
# `LINKEDIN_LI_AT`).
_logger = logging.getLogger(__name__)


def build_app(  # noqa: PLR0915, PLR0912
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

    # T-007 (`backend-scraper-query-tuning`): construct the
    # `HardcodedLocationResolver` ALWAYS (NOT gated by
    # `chat_enabled`). The resolver is a read-only in-process
    # dict lookup; the cost is one import + one dict
    # construction per app build. The scraper reads
    # `_settings.location_resolver` in its `search()` method
    # (REQ-LOC-001) — without this injection, the scraper
    # falls back to the broken `?location=<str>` URL formula
    # (the pre-`fix-linkedin-geoid` path). The resolver is
    # also reused by the chat filter (`location_resolver`
    # arg of `FilterJobsByIntentUseCase`) and by the
    # `GET /jobs` route (`app.state.location_resolver`,
    # T-009).
    location_resolver = HardcodedLocationResolver()

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

    # T-016 (chat filter wiring): the chat filter is OFF by
    # default (Q3 — 2-stage rollout: code merged disabled, ops
    # enables in prod via `LLM_FILTER_ENABLED=true` +
    # `LLM_API_KEY=<key>`). The 3 conditions that gate the
    # chat feature:
    #   1. `llm_filter_enabled=True` (operator enables the
    #      feature flag).
    #   2. `llm_api_key is not None` (the LLM provider key is
    #      set — without it, the route would 502 on every call).
    #   3. (Implicit: the chat route is registered below in
    #      the routers section.)
    # When OFF, the chat route is NOT registered (404), the
    # chat middleware is NOT mounted, the use case is NOT
    # built, and the LLM client is NOT built. The `httpx`
    # client lifetime is managed in the lifespan's `finally`
    # block (mirror the Redis client pattern).
    chat_enabled: bool = (
        effective_settings.llm_filter_enabled and effective_settings.llm_api_key is not None
    )
    llm_http_client: httpx.AsyncClient | None = None
    if chat_enabled:
        # Build the shared httpx client (design §11 #1 —
        # connection pooling across requests). The
        # `MiniMaxLLMClient` is ctor-injected with this
        # client; on `aclose()` (in the lifespan's
        # `finally`), the client is closed. The timeout
        # comes from the LLM-specific setting (NOT the
        # per-source request timeout).
        llm_http_client = httpx.AsyncClient(timeout=effective_settings.llm_request_timeout_seconds)

    # T-005 of `backend-linkedin-stealth` — REQ-LST-COOKIE-001 + REQ-LST-SCR-001
    # startup WARNING. Emitted ONCE per `build_app()` call (process
    # start) when the operator has not configured ANY of the 4
    # `LINKEDIN_*` cookies (`li_at` + `JSESSIONID` + `bcookie` +
    # `li_gc`). The WARNING runs OUTSIDE the `if use_case is None:`
    # block so it fires even when a test injects a use case (the
    # integration test asserts the warning contract end-to-end).
    # The adapter construction stays inside the `if use_case is
    # None:` block because it only matters when we're actually
    # building the scraper.
    #
    # The v1 message was the shorter
    # `"LinkedIn scraper running without auth cookie"` prefix; the
    # T-005 message is a strict superset that covers all 4 cookies
    # (the operator may have set any of the 4 in practice; the
    # WARNING is only suppressed when AT LEAST 1 is set).
    if (
        effective_settings.linkedin_li_at is None
        and effective_settings.linkedin_jsessionid is None
        and effective_settings.linkedin_bcookie is None
        and effective_settings.linkedin_bscookie is None
        and effective_settings.linkedin_li_gc is None
    ):
        _logger.warning(
            "LinkedIn scraper running without any auth cookies; "
            "SERP will hit the Cloudflare / auth wall and return a "
            "reduced list. Set at least LINKEDIN_LI_AT (or all 5) "
            "in .env to bypass the wall."
        )

    if use_case is None:
        # T-005 of `backend-linkedin-stealth` — REQ-LST-COOKIE-001
        # + REQ-LST-SCR-001. Build the
        # `MultiEnvLinkedInAuthCookiesAdapter` from the 5
        # resolved `Settings.linkedin_*` cookie fields
        # (T-005 of `backend-linkedin-xvfb` added the 5th
        # `bscookie` field for the F-4 fold-in per
        # obs #375 §9; default `None` preserves the
        # 4-cookie path). The adapter is constructed ONCE
        # per `build_app()` call and lives in the
        # `LinkedInScraperSettings.auth_cookies` slot. The
        # v1 `auth_cookie` slot is `None` in the production
        # wire (the v1 adapter is preserved for backward
        # compat with the 35 v1 tests that construct
        # `EnvLinkedInAuthCookieAdapter` directly).
        json_adapter = JsonLinkedInAuthCookiesAdapter()
        if json_adapter.cookies() is not None:
            auth_cookies_port: (
                MultiEnvLinkedInAuthCookiesAdapter | JsonLinkedInAuthCookiesAdapter
            ) = json_adapter
        else:
            auth_cookies_port = MultiEnvLinkedInAuthCookiesAdapter(
                li_at=effective_settings.linkedin_li_at,
                jsessionid=effective_settings.linkedin_jsessionid,
                bcookie=effective_settings.linkedin_bcookie,
                bscookie=effective_settings.linkedin_bscookie,
                li_gc=effective_settings.linkedin_li_gc,
            )
        # `Stealth()` is constructed at the composition root
        # (mirrors the Indeed+InfoJobs wires below at L340 and
        # L396). The instance lives in the
        # `LinkedInScraperSettings.stealth` slot; `search()`
        # calls `await self._stealth.apply_stealth_async(ctx)`
        # AFTER `new_context()` BEFORE `add_cookies` (REQ-LST-SCR-001).
        scraper = LinkedInPlaywrightScraper(
            throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
            # REQ-L-008: `LinkedInScraperSettings` was renamed from the
            # in-module `ScraperSettings`; the two new env-driven
            # fields (`linkedin_max_pages`, `linkedin_inter_page_delay_seconds`)
            # are the pagination knobs (REQ-L-007, REQ-L-009).
            # T-007: the `location_resolver` kwarg wires the
            # resolver into the settings so the scraper's
            # `search()` can call `resolve(location)` once per
            # call (the pre-`backend-scraper-query-tuning`
            # build had no resolver; the URL builder always
            # fell back to `?location=<str>`).
            # T-004: 2 NEW slots (`auth_cookies` + `stealth`)
            # coexist with the v1 `auth_cookie` slot. The v1
            # slot is `None` in the production wire; the v1
            # adapter is preserved for the 35 v1 tests that
            # construct it directly.
            # T-001 of `backend-linkedin-xvfb` (REQ-LBUG-001,
            # obs #379 bugfix fold-in): the new `headless`
            # slot wires the previously-dead
            # `Settings.headless` env binding into the
            # `chromium.launch(headless=...)` kwarg. The
            # default `True` preserves the v1 byte-identical
            # default path.
            # T-002 of `backend-linkedin-xvfb` (REQ-LXV-001/002/003):
            # the new `xvfb_display` slot wires
            # `Settings.linkedin_xvfb_display` (the opt-in
            # Xvfb switch) into the scraper's `__aenter__`
            # 2-branch conditional. When `None` (the v1+v2
            # default), the byte-identical headless path is
            # taken. When set (e.g. `":99"`), the Xvfb
            # branch activates with `headless=False`,
            # `--no-sandbox` + `--disable-dev-shm-usage`
            # args, and the `DISPLAY` env kwarg on
            # `async_playwright().start()`.
            settings=LinkedInScraperSettings(
                user_agent=effective_settings.user_agent,
                timeout_ms=effective_settings.request_timeout_ms,
                max_pages=effective_settings.linkedin_max_pages,
                inter_page_delay_seconds=effective_settings.linkedin_inter_page_delay_seconds,
                location_resolver=location_resolver,
                auth_cookie=None,  # v1 slot kept (None in production wire)
                auth_cookies=auth_cookies_port,  # NEW (multi-cookie)
                stealth=Stealth(),  # NEW
                headless=effective_settings.headless,  # NEW (T-001 bugfix wire)
                xvfb_display=effective_settings.linkedin_xvfb_display,  # NEW (T-002 Xvfb wire)
                launch_channel=effective_settings.linkedin_launch_channel,  # NEW (experiment)
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
                # REQ-PROV-004: wire the SAME `HardcodedLocationResolver`
                # instance (L185) into `InfoJobsScraperSettings` so the
                # scraper's `search()` can call
                # `resolve_infojobs(location)` once per call. The
                # resolver is the SAME instance the LinkedIn scraper
                # receives — one resolver, two methods, one in-process
                # dict. The `is` invariant is pinned by
                # `test_resolver_shared_between_linkedin_and_infojobs`
                # in `tests/integration/test_composition.py`.
                location_resolver=location_resolver,
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
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:  # noqa: PLR0912
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
        # T-009 (background-scheduler-persistence): open the SQLite
        # repository and start the background scheduler when both
        # SCHEDULER_ENABLED and the aggregator use case are available.
        # The repo is opened AFTER the scrapers (the scheduler calls
        # the aggregator which calls the scrapers) and the scheduler
        # starts AFTER the repo is ready so the DB is available on
        # the first tick.
        if _scheduler_repo is not None and _scheduler_instance is not None:
            await _scheduler_repo.__aenter__()
            _app.state.job_repository = _scheduler_repo
            _scheduler_instance.start()
        try:
            yield
        finally:
            # T-005 (persistent-cache): close the shared Redis
            # client on shutdown. Runs FIRST so a slow `aclose()`
            # doesn't delay the LIFO scraper-shutdown order.
            if redis_client is not None:
                await redis_client.aclose()
            # T-016 (chat filter wiring): close the shared
            # `httpx.AsyncClient` (built above when chat is
            # enabled) on shutdown. The client is the one
            # passed to `build_minimax_llm_client` via the
            # `http_client` kwarg; closing it here is the
            # documented shutdown hook (the `MiniMaxLLMClient`
            # uses it but does NOT own it — `aclose()` on the
            # LLM client would be a no-op for an injected
            # client, per T-012 deviation #5).
            if llm_http_client is not None:
                await llm_http_client.aclose()
            # T-003 (rate-limiting): close the rate-limiter Redis
            # client on shutdown. The factory constructs a separate
            # client when `RATE_LIMIT_BACKEND="redis"` and the
            # caller passes no `client` (the composition root does
            # not), so the rate-limiter owns its own client. The
            # `is not redis_client` guard is defensive — a future
            # refactor that shares the client across the cache
            # and rate-limiter would otherwise double-close.
            rl_redis_client = getattr(rate_limiter, "_client", None)
            if rl_redis_client is not None and rl_redis_client is not redis_client:
                await rl_redis_client.aclose()
            # T-009 (background-scheduler-persistence): stop the
            # scheduler first (cancel the background task), then close
            # the repository. This runs BEFORE the scrapers close so
            # the shutdown order is LIFO: scrapers → repo → scheduler
            # on startup, scheduler → repo → scrapers on shutdown.
            if _scheduler_instance is not None:
                await _scheduler_instance.stop()
            if _scheduler_repo is not None:
                await _scheduler_repo.__aexit__(None, None, None)
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
    # T-009 (`backend-scraper-query-tuning`): expose the
    # `Settings` instance and the `HardcodedLocationResolver`
    # on `app.state` so the `GET /jobs` route can read them
    # without re-importing the modules. The settings is the
    # SAME instance used for the scraper + cache wiring (no
    # re-read of env vars per request). The resolver is the
    # SAME instance injected into the LinkedIn scraper (no
    # re-build per request).
    app.state.settings = effective_settings
    app.state.location_resolver = location_resolver

    # T-002 (jobs-aggregator-endpoint): the aggregator wraps the 3
    # per-source use cases and runs them in parallel via
    # `asyncio.gather` (see `application/aggregator.py`). The
    # default branch reuses the 3 use cases that the per-source
    # routes use, so the aggregator AUTOMATICALLY inherits the
    # cache-ttl behavior (REQ-C-001..REQ-C-006) without a separate
    # cache: a cache hit on LinkedIn from a prior per-source call is
    # ALSO a cache hit when the aggregator invokes LinkedIn.
    #
    # T-001 (jobs-aggregator-ranking): the default branch now also
    # reads `effective_settings.aggregator_ranking_strategy` and
    # `effective_settings.aggregator_priority_map` (both
    # env-overridable; see `infrastructure/config.py`) and forwards
    # them to the `SearchAllSourcesUseCase` constructor. The
    # `ranking_strategy` is `Literal["posted_at", "priority", "none"]`
    # — Pydantic's `Literal` validator rejects unknown values at
    # startup, so the only error path here is the Pydantic
    # `ValidationError` raised at `Settings()` construction time.
    # The `priority_map` is a `dict[str, int]` whose keys are
    # source names and whose values are priority integers (lower =
    # higher priority; sources not in the map get
    # `MISSING_SOURCE_PRIORITY = 999` at the `rank_jobs` call
    # site, not here).
    if aggregator_use_case is None:
        aggregator_use_case = SearchAllSourcesUseCase(
            linkedin_use_case=use_case,
            indeed_use_case=indeed_use_case,
            infojobs_use_case=infojobs_use_case,
            ranking_strategy=effective_settings.aggregator_ranking_strategy,
            priority_map=effective_settings.aggregator_priority_map,
            # T-008 (`backend-scraper-query-tuning`): wire the
            # 2 pure-function helpers (filter + scorer) at the
            # composition root. Without these, the ctor's
            # default `_noop_keyword_score` and `_identity_filter`
            # are used — `enable_keyword_scoring=True` would then
            # sort by `0.0` for every job (the noop), so all
            # results sort purely by `posted_at desc` regardless
            # of the query.
            filter_infojobs_results=filter_infojobs_results,
            keyword_score=keyword_score,
            # The opt-in `enable_keyword_scoring` setting. The
            # constructor default is `False` (the v1 sort
            # behavior). The setting flows through to the
            # `SearchAllSourcesUseCase.search()` method as a
            # keyword-only arg; tests can also pass it
            # programmatically.
            enable_keyword_scoring=effective_settings.enable_keyword_scoring,
        )
    app.state.aggregator_use_case = aggregator_use_case

    # ── Background scheduler + repository (REQ-ROOT-001) ──────────────────
    #
    # When `settings.scheduler_enabled` AND the aggregator use case is
    # available, build a `SqliteJobRepository` and a
    # `BackgroundJobScheduler`. The lifecycle (open → start → serve →
    # stop → close) is managed in the lifespan below.
    #
    # When disabled (`scheduler_enabled=False`, the default): both are
    # `None` and the lifespan is unchanged from prior behavior.
    _scheduler_repo: SqliteJobRepository | None = None
    _scheduler_instance: BackgroundJobScheduler | None = None
    _wire_scheduler: bool = effective_settings.scheduler_enabled and aggregator_use_case is not None

    if _wire_scheduler:
        _scheduler_repo = SqliteJobRepository(db_path=effective_settings.db_path)

        # Wrap the aggregator's search() to match the
        # Callable[[str, str], Awaitable[list[Job]]] signature.
        async def _scheduler_search_fn(keywords: str, location: str) -> list[Job]:
            result = await aggregator_use_case.search(
                keywords=keywords,
                location=location,
                limit=20,
                sources=["linkedin", "indeed", "infojobs"],
            )
            return [aj.job for aj in result.jobs]

        _scheduler_instance = BackgroundJobScheduler(
            search_fn=_scheduler_search_fn,
            repo=_scheduler_repo,
            queries=effective_settings.scheduler_queries,
            min_interval=effective_settings.scheduler_min_interval_seconds,
            max_interval=effective_settings.scheduler_max_interval_seconds,
        )

    # T-016 (chat filter wiring): build the LLM client + the
    # chat-filter use case ONLY when the chat feature is enabled
    # (the `chat_enabled` flag computed above). The factory
    # `build_minimax_llm_client` raises `ValueError` on a
    # missing key as a defense-in-depth check; the conditional
    # registration above is the primary gate.
    #
    # T-009 (`chat-filter-2stage`): the chat-filter use case now
    # accepts an `IntentExtractor` for the 2-stage LLM flow
    # (REQ-CHAT-INT-001..005). The factory builds the
    # `IntentExtractor` ONLY when
    # `effective_settings.intent_extraction_enabled` is `True`;
    # when `False`, the use case is constructed with
    # `intent_extractor=None` (the v1 single-stage backward-compat
    # path — REQ-CHAT-INT-005). The retry count
    # (`effective_settings.intent_extraction_retry`) flows into
    # the `IntentExtractor` ctor so operators can bump it
    # without code changes (REQ-LLM-SEC-002).
    chat_use_case: FilterJobsByIntentUseCase | None = None
    if chat_enabled:
        llm_client = build_minimax_llm_client(effective_settings, http_client=llm_http_client)
        intent_extractor: IntentExtractor | None = None
        if effective_settings.intent_extraction_enabled:
            intent_extractor = IntentExtractor(
                llm=llm_client,
                parser=parse_intent_response,
                max_retries=effective_settings.intent_extraction_retry,
            )
        # T-004 (`fix-linkedin-geoid`): inject the SAME
        # `HardcodedLocationResolver` (constructed at L185
        # above) into the chat-filter use case. The use case
        # calls the resolver in the 2-stage path to translate
        # `intent.location` (a free-form string) into a
        # LinkedIn `geoId` (a `int`). The resolver is a
        # in-process dict lookup (no I/O); the
        # `LOCATION_RESOLVER_ENABLED=false` kill switch is
        # OUT of scope for this change (a follow-up
        # environment variable can disable the resolver
        # without code changes; the v1 default is always-on).
        # The resolver is constructed once at composition-
        # root time and shared across the LinkedIn scraper,
        # the InfoJobs scraper, the chat filter, AND the
        # `app.state.location_resolver` (REQ-PROV-004).
        #
        # T-003 (`backend-infojobs-provinces`): the previous
        # code path had a SHADOWING BUG at this exact line
        # — `location_resolver = HardcodedLocationResolver()`
        # built a SECOND `HardcodedLocationResolver` instance
        # here, shadowing the L185 var. The chat filter then
        # received a different resolver instance than the
        # LinkedIn + InfoJobs scrapers, breaking the
        # `app.state.location_resolver is settings.location_resolver`
        # identity invariant. The bug is now FIXED: this
        # block reuses the L185 instance (the variable is
        # NOT reassigned). The fix is pinned by
        # `test_resolver_shared_between_linkedin_and_infojobs`
        # in `tests/integration/test_composition.py`.
        chat_use_case = FilterJobsByIntentUseCase(
            aggregator=aggregator_use_case,
            llm=llm_client,
            intent_extractor=intent_extractor,
            intent_extraction_enabled=effective_settings.intent_extraction_enabled,
            intent_extraction_confidence_threshold=(
                effective_settings.intent_extraction_confidence_threshold
            ),
            intent_max_results=effective_settings.intent_max_results,
            location_resolver=location_resolver,
        )
    # Expose the use case on `app.state` regardless of the
    # flag (a future caller that constructs the use case
    # externally can still find it; the route itself is
    # registered conditionally below).
    app.state.filter_use_case = chat_use_case

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
    # T-003 (rate-limiting): the limiter is built via
    # `build_rate_limiter(settings)` — the factory selects
    # `NoOpRateLimiter` (disabled), `InMemoryTokenBucket` (memory
    # backend, default), or `RedisTokenBucket` (redis backend)
    # per `RATE_LIMIT_ENABLED` / `RATE_LIMIT_BACKEND`. When
    # `rate_limit_enabled=False`, the middleware is NOT added to
    # the stack — the app's behavior is byte-identical to the
    # pre-T-002 baseline.
    rate_limiter: RateLimitPort = build_rate_limiter(effective_settings)

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
            # REQ-RL-011: `RATE_LIMIT_TRUSTED_PROXIES` is a JSON list
            # of CIDR strings parsed by `Settings` into a
            # `frozenset[IPv4Network | IPv6Network]`. Default empty
            # (security default — `X-Forwarded-For` ignored).
            trusted_proxies=effective_settings.rate_limit_trusted_proxies,
        )
    # T-016 (chat filter wiring): mount the `ChatRateLimitMiddleware`
    # AFTER the main `RateLimitMiddleware` in code (so it runs
    # OUTSIDE the main rate limit at request time — the main
    # rate limit is checked first; if it allows, the chat limit
    # is checked next) and BEFORE `RequestIdMiddleware` in code
    # (so it runs AFTER RequestId at request time — the 429
    # body reads `request.state.request_id` set by RequestId).
    # The middleware is mounted ONLY when the chat feature is
    # enabled (mirrors the chat route's conditional registration
    # — no chat route means no chat bucket).
    if chat_use_case is not None:
        app.add_middleware(
            ChatRateLimitMiddleware,
            # Reuse the same `RateLimitPort` instance the main
            # middleware uses. The `chat:` key prefix isolates
            # the chat bucket from the main bucket (the same
            # `RateLimitPort` instance, different key namespace).
            rate_limiter=rate_limiter,
            max_per_minute=effective_settings.llm_filter_rate_limit_rpm,
            trusted_proxies=effective_settings.rate_limit_trusted_proxies,
        )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=effective_settings.cors_allow_origins,
        # T-009 (chat-streaming) — REQ-CORS-001 widens
        # `allow_methods` to include `POST` so a browser
        # preflight for `POST /jobs/chat/stream` (and the
        # future JSON POST endpoints) succeeds. The
        # change is strictly additive; the v1 GET routes
        # (`/jobs`, `/jobs/linkedin`, `/jobs/indeed`,
        # `/jobs/infojobs`) are unchanged.
        allow_methods=["GET", "POST"],
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
    # T-016 (chat filter wiring): the chat route is registered
    # ONLY when the chat feature is enabled. When disabled,
    # `POST /jobs/chat` returns 404 (the safest default per
    # design §2 — operators get a clear "this feature is off"
    # signal in logs). The chat router is mounted LAST so it
    # does not shadow any per-source route.
    if chat_use_case is not None:
        app.include_router(
            chat_routes.build_chat_router(
                use_case=chat_use_case,
                max_message_chars=effective_settings.llm_max_message_chars,
            )
        )
        # T-009 (chat-streaming): the streaming sibling route
        # is also registered ONLY when the chat feature is
        # enabled (it shares the same use case as v1 chat).
        # The route forwards `sse_keepalive_seconds` from
        # `Settings` (default 15.0; `0` disables per
        # REQ-SSE-002 3rd scenario). The chat_rate_limit
        # middleware (mounted above) covers BOTH endpoints
        # with the same per-user bucket (the key prefix
        # is `chat:`).
        app.include_router(
            chat_routes.build_chat_stream_router(
                use_case=chat_use_case,
                max_message_chars=effective_settings.llm_max_message_chars,
                sse_keepalive_seconds=effective_settings.sse_keepalive_seconds,
            )
        )

    return app
