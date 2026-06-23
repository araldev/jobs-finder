# Test fixtures and shared configuration for the jobs-finder test suite.
#
# The conftest grows as the project grows. The T-001 batch of the
# `indeed_platform` change adds two shared fixtures here so future
# batches (T-005 onward) can consume them without redefining the same
# fake port + sample jobs in every test file:
#
#   - `sample_indeed_jobs`: 3 deterministic, source-agnostic `Job`
#     instances with Indeed-style canonical viewjob URLs.
#   - `fake_indeed_port`: an in-memory `FakeJobSearchPort` primed with
#     `sample_indeed_jobs`; structural-conformant with the
#     `JobSearchPort` Protocol (cite REQ-I-003 / REQ-I-005).
#   - `FakeJobSearchPort` class: shared by both fixtures and by any
#     future test that wants to construct a fresh port instance.
#   - `app` (T-007): a FastAPI app whose ALL THREE use cases
#     (LinkedIn + Indeed + InfoJobs) are wired to fake ports, so
#     each per-source integration test can drive its route against
#     a `FakeJobSearchPort` without launching Chromium. The LinkedIn
#     port is fresh + empty so the existing LinkedIn integration
#     tests (which define their own `app` fixture locally) are not
#     affected.
#
# The prior `linkedin-endpoint` change defined its `FakeJobSearchPort`
# and sample `Job` factories inline in each test file. The Indeed
# path starts with a conftest-level definition so the duplication
# stays bounded as more tests are added.

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from pydantic import SecretStr

# Session-scoped fixture that mocks _is_within_active_hours to return True.
# This allows scheduler tests to run regardless of actual Madrid time.
# The work-hours gate behavior is verified by TestIsWithinActiveHours boundary tests.
import jobs_finder.infrastructure.scheduler as scheduler_module
from jobs_finder.application.ports import Intent


@pytest.fixture
def scheduler_bypass_work_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch _is_within_active_hours to always return True.

    Use this fixture in tests that need the scheduler to run regardless
    of actual Madrid time. The boundary tests (TestIsWithinActiveHours)
    do NOT use this fixture - they test the actual hour-based logic.
    """
    monkeypatch.setattr(scheduler_module, "_is_within_active_hours", lambda: True)


from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app


class FakeLinkedInAuthCookiePort:
    """In-memory fake of `LinkedInAuthCookiePort` for tests (T-001 of
    `backend-linkedin-auth`).

    Mirrors the `EnvLinkedInAuthCookieAdapter` shape: a value-holder
    with a single `cookie()` method that returns the configured
    `SecretStr | None`. Default is `None` (the v1 anonymous-scraper
    path). Tests construct one explicitly when they need the
    adapter to return a value (e.g. the per-cookie shape assertions
    in `tests/unit/test_linkedin_scraper.py`).

    The class is defined in `conftest.py` (NOT in a per-test file)
    so future tests across the suite can import it without
    duplicating the definition. Cite REQ-LA-COOKIE-001 scenario 3
    (`test_fake_double_conforms_to_protocol`).
    """

    __slots__ = ("_cookie",)

    def __init__(self, cookie: SecretStr | None = None) -> None:
        self._cookie = cookie

    def cookie(self) -> SecretStr | None:
        return self._cookie


class FakeLinkedInAuthCookiesPort:
    """In-memory fake of `LinkedInAuthCookiesPort` (plural) for tests
    (T-001 of `backend-linkedin-stealth`).

    Mirrors the `MultiEnvLinkedInAuthCookiesAdapter` shape: a
    value-holder with a single `cookies()` method that returns
    the configured `list[tuple[str, SecretStr]] | None`. Default
    is `None` (the v1 anonymous-scraper path — `cookies()` returns
    `None` so the scraper skips `add_cookies` entirely). Tests
    construct one explicitly when they need the adapter to
    return a value (e.g. the per-cookie shape assertions in
    `tests/unit/test_linkedin_stealth.py`).

    The class is defined in `conftest.py` (NOT in a per-test
    file) so future tests across the suite can import it
    without duplicating the definition. Cite REQ-LST-COOKIE-001
    scenario 3 (`test_fake_double_conforms_to_protocol`).

    The v1 `FakeLinkedInAuthCookiePort` is byte-identical and
    satisfies the v1 `LinkedInAuthCookiePort` (singular) only;
    it does NOT satisfy the new `LinkedInAuthCookiesPort`
    (plural) — the test in
    `test_linkedin_stealth.py::TestFakeLinkedInAuthCookiesPort::test_fake_conforms_to_protocol_typecheck`
    pins the structural conformance of the new fake only.

    REQ-AC-101 (`linkedin-cookie-refresh` cycle 4): the fake
    ALSO satisfies the new `set_cookies()` method. It records
    every call in `set_cookies_calls` and overwrites
    `self._cookies` with the new pairs derived from the input
    dicts (preserving REQ-AC-102 read-after-write).
    """

    __slots__ = ("_cookies", "set_cookies_calls")

    def __init__(
        self,
        cookies: list[tuple[str, SecretStr]] | None = None,
    ) -> None:
        self._cookies = cookies
        self.set_cookies_calls: list[list[dict[str, object]]] = []

    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        return self._cookies

    async def set_cookies(self, cookies: list[dict[str, object]]) -> None:
        """REQ-AC-101 — record the call + overwrite internal state.

        The fake normalizes each cookie dict to a
        `(name, SecretStr(value))` pair in canonical order
        (REVERSED of `cookies()`'s filter rule — `set_cookies`
        stores ALL entries, even unknown names; the
        `MultiEnvLinkedInAuthCookiesAdapter.set_cookies()`
        ignores unknown names per REQ-AC-101).
        """
        self.set_cookies_calls.append(list(cookies))
        pairs: list[tuple[str, SecretStr]] = []
        for c in cookies:
            name = str(c.get("name", ""))
            value = str(c.get("value", ""))
            if name and value:
                pairs.append((name, SecretStr(value)))
        self._cookies = pairs if pairs else None


class FakeLinkedInCookieRefresherPort:
    """In-memory fake of `LinkedInCookieRefresherPort` for tests
    (T-012 of `linkedin-cookie-refresh` cycle 4).

    Mirrors the `LinkedInCookieRefresherPort` Protocol: a
    single async `refresh()` method that returns the configured
    `canned` list of dicts OR `None` on failure. The fake
    supports 3 scenarios per C-3 (spec constraint):

    1. **Success** — `canned=[{...}, ...]` returns the list.
    2. **Failure** — `canned=None` returns `None`.
    3. **Slow refresh** — `delay_seconds=2.0` awaits that
       many seconds before returning (the backoff test
       asserts that the scraper's `_last_refresh_attempt_at`
       is recorded before the await completes — needed to
       verify backoff state semantics).

    The ctor ALSO accepts an `error: Exception | None` (not
    used in spec scenarios but exposed for completeness —
    the production `PlaywrightLinkedInCookieRefresher` swallows
    ALL exceptions internally, so the scraper never sees a
    raise; this kwarg exists for future test scaffolding).

    Records every call in `calls: int` so the scraper
    integration tests can assert the refresh was invoked
    exactly once (or exactly zero times in the backoff path).

    The class is structurally compatible with
    `LinkedInCookieRefresherPort` — `async def refresh(self) ->
    list[dict[str, Any]] | None` matches the Protocol's
    signature exactly (mypy --strict enforces this at
    type-check time).
    """

    __slots__ = ("_canned", "_delay_seconds", "_error", "calls")

    def __init__(
        self,
        canned: list[dict[str, object]] | None = None,
        *,
        delay_seconds: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        # `canned=None` is the failure sentinel; `canned=[]`
        # is "success but zero cookies" (a degenerate case the
        # spec does NOT pin — tests should use `canned=[{...}]`
        # for success scenarios).
        self._canned = canned
        self._delay_seconds = delay_seconds
        self._error = error
        self.calls: int = 0

    async def refresh(self) -> list[dict[str, object]] | None:
        """Return `canned` (or raise `error` / sleep then return)."""
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._delay_seconds > 0:
            import asyncio

            await asyncio.sleep(self._delay_seconds)
        if self._canned is None:
            return None
        # Return a copy so the caller cannot mutate the fake's
        # canned state via the returned list.
        return [dict(c) for c in self._canned]  # noqa: E501


def _build_cached_linkedin_use_case(
    port: FakeJobSearchPort,
) -> CachedJobSearchUseCase:
    """Wrap a LinkedIn `FakeJobSearchPort` in a fresh cached wrapper.

    The `cache-ttl` change replaces the raw `SearchLinkedInJobsUseCase`
    with a `CachedJobSearchUseCase` wrapper. Tests that build the
    app via `build_app(use_case=...)` need a cached wrapper; this
    helper constructs one with a fresh `InMemoryTTLCache` (no
    shared state across tests).
    """
    return SearchLinkedInJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort` for tests.

    Records every call so tests can assert the route/use case forwarded
    the input correctly. Can be primed (or mutated) to raise an
    exception on the next call. Cite REQ-I-005.

    The `geo_id` kwarg is part of the `JobSearchPort` Protocol
    signature since the `fix-linkedin-geoid` change (the
    cache wrapper forwards it to the port; Indeed + InfoJobs
    ports ignore it). The 3-tuple `calls` shape is preserved
    for backward compat with the pre-WU3 test surface (the
    `geo_id` is accepted but NOT recorded; the new
    `_FakeJobSearchPortWithGeoId` in
    `test_cached_job_search_use_case.py` records 4-tuples).

    NOTE: a structurally-identical `FakeJobSearchPort` is defined
    inline in `tests/integration/test_api.py` (the LinkedIn
    integration test). Keeping the duplication is intentional: the
    LinkedIn file pre-dates the conftest fixture and refactoring it
    is out of scope for the `indeed_platform` change. When a future
    change consolidates the integration tests, the two definitions
    should collapse into the one in this module.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        # The pre-WU3 fake records 3-tuples; the `geo_id` is
        # accepted as a kwarg (so the cache wrapper's call
        # works) but NOT recorded (so the existing 3-tuple
        # assertions still pass).
        del geo_id
        self.calls.append((keywords, location, limit))
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _make_indeed_sample_jobs() -> list[Job]:
    """Build 3 deterministic, Indeed-style `Job` instances.

    The ids are 9-digit numbers mirroring Indeed's `data-jk` shape.
    Each URL is the canonical `https://es.indeed.com/viewjob?jk=<id>`
    form (not a SERP `/rc/clk` or `vjk=`-pinned URL). `posted_at` is
    tz-aware UTC to satisfy the `Job.__post_init__` invariant.
    """
    return [
        Job(
            id="100000001",
            title="Indeed Title 1",
            company="Indeed Co 1",
            location="Madrid, Spain",
            url="https://es.indeed.com/viewjob?jk=100000001",
            posted_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="indeed",
        ),
        Job(
            id="100000002",
            title="Indeed Title 2",
            company="Indeed Co 2",
            location="Barcelona, Spain",
            url="https://es.indeed.com/viewjob?jk=100000002",
            posted_at=datetime(2026, 5, 2, tzinfo=UTC),
            source="indeed",
        ),
        Job(
            id="100000003",
            title="Indeed Title 3",
            company="Indeed Co 3",
            location="Valencia, Spain",
            url="https://es.indeed.com/viewjob?jk=100000003",
            posted_at=datetime(2026, 5, 3, tzinfo=UTC),
            source="indeed",
        ),
    ]


@pytest.fixture
def sample_indeed_jobs() -> list[Job]:
    """3 deterministic, source-agnostic `Job` instances shaped for Indeed tests.

    Each job has the canonical `https://es.indeed.com/viewjob?jk=<id>`
    URL. The 3 jobs have unique ids, titles, companies, and locations so
    tests that assert field-by-field can identify which one they're
    looking at.
    """
    return _make_indeed_sample_jobs()


@pytest.fixture
def fake_indeed_port(sample_indeed_jobs: list[Job]) -> FakeJobSearchPort:
    """An in-memory `FakeJobSearchPort` primed with `sample_indeed_jobs`.

    Returns a fresh port per test. The port records every call so tests
    can assert the route/use case forwarded the input correctly.
    """
    return FakeJobSearchPort(jobs=sample_indeed_jobs)


@pytest.fixture
def app(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """A FastAPI app whose ALL THREE use cases are wired to fake ports.

    The LinkedIn use case is wrapped around a fresh
    `FakeJobSearchPort` with NO jobs so the LinkedIn route works but
    returns an empty list. The Indeed use case is wrapped around
    `fake_indeed_port` (3 sample Indeed jobs). The InfoJobs use case
    is wrapped around `fake_infojobs_port` (3 sample InfoJobs jobs
    with the canonical `/ofertas-trabajo/oferta-{id}` URL format).
    The existing LinkedIn integration tests
    (`tests/integration/test_api.py`, etc.) define their own local
    `app` fixture and so are NOT affected by this conftest fixture.

    The fixture exists to give the per-source integration tests
    (`test_indeed_api.py`, `test_infojobs_api.py`) a single `app` to
    drive, with all routes available for the `/health`-independence
    and per-source cross-check tests.
    """
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(
        port=fake_indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=fake_infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
    )


# ---------------------------------------------------------------------------
# InfoJobs fixtures (added in T-001 of `infojobs_platform`).
#
# The fixtures mirror the Indeed pattern: a helper that builds 3
# deterministic `Job` instances, a `sample_infojobs_jobs` fixture that
# returns the helper's output, and a `fake_infojobs_port` fixture that
# wraps a `FakeJobSearchPort` primed with the sample jobs. The
# `FakeJobSearchPort` class itself is reused from above — InfoJobs
# doesn't need its own class because the port is source-agnostic
# (REQ-I-003 / REQ-I-005 analog).
# ---------------------------------------------------------------------------


def _make_infojobs_sample_jobs() -> list[Job]:
    """Build 3 deterministic, InfoJobs-style `Job` instances.

    The ids are 7-character alphanumeric slugs (matching the parser's
    `/oferta-<id>` href format — see
    `jobs_finder.infrastructure.infojobs.parsers.parse_infojobs_job_id`).
    Each URL is the canonical
    `https://www.infojobs.net/ofertas-trabajo/oferta-<id>` form
    (REQ-J-001). `posted_at` is tz-aware UTC to satisfy the
    `Job.__post_init__` invariant.
    """
    return [
        Job(
            id="abc123def",
            title="InfoJobs Title 1",
            company="InfoJobs Co 1",
            location="Madrid, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-abc123def",
            posted_at=datetime(2026, 5, 1, tzinfo=UTC),
            source="infojobs",
        ),
        Job(
            id="def456ghi",
            title="InfoJobs Title 2",
            company="InfoJobs Co 2",
            location="Barcelona, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-def456ghi",
            posted_at=datetime(2026, 5, 2, tzinfo=UTC),
            source="infojobs",
        ),
        Job(
            id="ghi789jkl",
            title="InfoJobs Title 3",
            company="InfoJobs Co 3",
            location="Valencia, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-ghi789jkl",
            posted_at=datetime(2026, 5, 3, tzinfo=UTC),
            source="infojobs",
        ),
    ]


@pytest.fixture
def sample_infojobs_jobs() -> list[Job]:
    """3 deterministic, source-agnostic `Job` instances shaped for InfoJobs tests.

    Each job has the canonical
    `https://www.infojobs.net/ofertas-trabajo/oferta-<id>` URL
    (REQ-J-001). The 3 jobs have unique ids, titles, companies, and
    locations so tests that assert field-by-field can identify which
    one they're looking at.
    """
    return _make_infojobs_sample_jobs()


@pytest.fixture
def fake_infojobs_port(sample_infojobs_jobs: list[Job]) -> FakeJobSearchPort:
    """An in-memory `FakeJobSearchPort` primed with `sample_infojobs_jobs`.

    Returns a fresh port per test. The port records every call so tests
    can assert the route/use case forwarded the input correctly.

    Note: the `FakeJobSearchPort` class is the same one used by the
    `fake_indeed_port` fixture (added in T-001 of `indeed_platform`).
    InfoJobs reuses it because the port is source-agnostic.
    """
    return FakeJobSearchPort(jobs=sample_infojobs_jobs)


# ---------------------------------------------------------------------------
# Rate-limit fixtures (added in T-002 of `rate-limiting`).
#
# `settings_with_rate_limit`: a `Settings` instance with
# `rate_limit_requests=2` (so a 429 is reachable in-test) and
# `rate_limit_window_seconds=60.0` (so `Retry-After` is a meaningful
# integer). All other rate-limit fields use the spec defaults.
#
# `app_with_rate_limit`: a FastAPI app whose ALL THREE use cases are
# wired to fake ports AND whose `RateLimitMiddleware` is wired
# (via the `settings=...` injection). Used by the per-route rate
# limit tests in `tests/integration/test_rate_limit_headers.py` and
# `tests/integration/test_rate_limit_exempt.py`.
#
# The fixture exposes the LinkedIn fake port on `app.state.job_search_port`
# (the unwrapped scraper / fake port) so the 429 short-circuit test
# can assert the port was NOT called after a 429.
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_with_rate_limit() -> Settings:
    """A `Settings` with `rate_limit_requests=2` (so 429 is reachable in-test)."""
    return Settings(
        rate_limit_requests=2,
        rate_limit_window_seconds=60.0,
    )


@pytest.fixture
def app_with_rate_limit(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
    settings_with_rate_limit: Settings,
) -> FastAPI:
    """A FastAPI app with the rate limiter wired (`rate_limit_requests=2`).

    All 3 use cases are wired to fresh `FakeJobSearchPort` instances
    (the LinkedIn port is fresh + empty, the Indeed + InfoJobs ports
    are primed with the conftest's sample jobs). The rate-limit
    middleware is wired via the `settings_with_rate_limit` injection
    so a 429 is reachable on the 3rd call to any non-exempt route.
    """
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(
        port=fake_indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=fake_infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings_with_rate_limit,
    )


@pytest.fixture
def settings_with_rate_limit_concurrent() -> Settings:
    """A `Settings` with `rate_limit_requests=3` (so 7 of 10 concurrent are denied)."""
    return Settings(
        rate_limit_requests=3,
        rate_limit_window_seconds=60.0,
    )


@pytest.fixture
def app_with_rate_limit_concurrent(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
    settings_with_rate_limit_concurrent: Settings,
) -> FastAPI:
    """A FastAPI app with the rate limiter wired (`rate_limit_requests=3`).

    The concurrency test fires 10 concurrent `GET /jobs/linkedin`
    against a `capacity=3` bucket. Exactly 3 must return 200 and
    7 must return 429 (the per-key `asyncio.Lock` serializes the
    read-modify-write so no double-spend occurs).
    """
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(
        port=fake_indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=fake_infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings_with_rate_limit_concurrent,
    )


@pytest.fixture
def app_with_redis_rate_limit_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """A FastAPI app whose rate-limiter Redis points at a refused port.

    REQ-RL-003 fail-open + REQ-RL-009 no-lifespan-ping: the
    rate-limiter Redis is OPTIONAL. `RATE_LIMIT_REDIS_URL` is
    pointed at port 1 (reserved, never listening). The lifespan
    starts successfully (NO ping on the rate-limit Redis — that's
    the asymmetric contract with the cache's fail-fast ping). A
    subsequent request returns 200 + WARNING logged.
    """
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://localhost:1/0")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60.0")
    settings = Settings()

    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(
        port=fake_indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=fake_infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# FakeIntentExtractor (T-006 of `chat-filter-2stage`).
#
# `FakeIntentExtractor` is the canonical test double for the
# stage-1 intent extraction. PR2's T-008 wires the real
# `IntentExtractor` into the use case; the use case accepts an
# `IntentExtractorPort` Protocol (defined in
# `application/ports.py` in PR2). For PR1 we ship the test
# double only; the Protocol is added in PR2.
#
# The class has:
#   - `calls: list[str]` — records every `message` passed to
#     `extract()` (so tests can assert the use case forwarded
#     the user message correctly).
#   - `canned: Intent` — the Intent returned by every `extract()`
#     call. Defaults to `Intent(confidence=0.95)` (a "happy path"
#     high-confidence intent).
#   - `error: Exception | None` — when set, `extract()` raises
#     the injected exception. Used by the retry-exhaustion tests
#     in `test_intent_extractor.py` and (in PR2) the
#     stage-1-parse-failure scenarios.
#
# The method signature `async def extract(*, message: str) -> Intent`
# matches the real `IntentExtractor` so the test double is
# drop-in compatible (a future `IntentExtractorPort` Protocol
# can be added in PR2 and the FakeIntentExtractor will conform
# structurally — no test code changes).
# ---------------------------------------------------------------------------


class FakeIntentExtractor:
    """In-memory fake of `IntentExtractor` for tests.

    Mirrors the `FakeLLMClient` pattern in
    `tests/integration/test_chat_endpoint.py` (the canonical
    test double for `LLMClientPort`). The class is structurally
    compatible with the future `IntentExtractorPort` Protocol
    (planned for PR2 in `application/ports.py`); for PR1 the
    real `IntentExtractor` class is in
    `infrastructure/llm/_intent.py` and the use case is NOT
    yet refactored to depend on the Protocol.

    The class is a value-holder: it has no parsing logic, no
    LLM dependency, no module-level state. Every `extract()` call
    either returns `self.canned` (the default) or raises
    `self.error` (when set). Tests construct one with a custom
    `canned` Intent to drive the use case's stage-2 / fallback
    decision.

    Args:
        canned: The `Intent` returned by every `extract()` call.
            Defaults to `Intent(confidence=0.95)` — a high-
            confidence intent that triggers the 2-stage path
            in the use case (REQ-CHAT-INT-004).
        error: When set, `extract()` raises this exception on
            every call. Used to test the stage-1 parse failure
            path (the use case catches `LLMResponseParseError`
            and falls back to v1 — REQ-CHAT-INT-004).
    """

    def __init__(
        self,
        canned: Intent | None = None,
        error: Exception | None = None,
    ) -> None:
        self.canned: Intent = canned if canned is not None else Intent(confidence=0.95)
        self.error: Exception | None = error
        # Records every `message` argument. Tests assert the use
        # case forwarded the right string (e.g. the NFC-normalized
        # user message).
        self.calls: list[str] = []

    async def extract(self, *, message: str) -> Intent:
        """Return `canned` (or raise `error`) and record the call."""
        self.calls.append(message)
        if self.error is not None:
            raise self.error
        return self.canned
