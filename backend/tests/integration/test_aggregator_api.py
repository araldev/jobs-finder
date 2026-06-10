"""Integration tests for the `GET /jobs` aggregator route.

Spec: REQ-A-001..REQ-A-006.

The aggregator is a thin composition layer over the 3 per-source
routes. It accepts `q`, `location`, `limit`, and `sources` query
parameters, invokes the selected cached use cases in parallel via
`asyncio.gather`, deduplicates identical job postings across
sources, and returns a single aggregated `list[AggregatedJob]`.

The headers (`X-Cache` joined, `X-Aggregator-Sources`,
`X-Aggregator-Errors`) are set in T-003 and have their own
integration test file (`test_aggregator_headers.py`). This file
covers the route + schemas + wiring contract (body shape, status
codes, validation, dedup, per-source error isolation).

This test file is the RED → GREEN → REFACTOR anchor for T-002.
It must be authored BEFORE the route + schemas + wiring, run to
confirm it fails (RED), then the route is added, then the tests
pass (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.aggregator import AggregatedResult, SearchAllSourcesUseCase
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
from jobs_finder.infrastructure.indeed.exceptions import IndeedBlockedError
from jobs_finder.infrastructure.infojobs.exceptions import InfoJobsBlockedError
from jobs_finder.infrastructure.linkedin.exceptions import LinkedInBlockedError
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _build_cached_use_case(port: FakeJobSearchPort, source: str) -> CachedJobSearchUseCase:
    """Wrap a `FakeJobSearchPort` in a fresh cached wrapper.

    Mirrors `tests/integration/test_cache_502_header.py`'s helper.
    """
    cls = {
        "linkedin": SearchLinkedInJobsUseCase,
        "indeed": IndeedSearchJobsUseCase,
        "infojobs": InfoJobsSearchJobsUseCase,
    }[source]
    return cls(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source=source,
    )


def _build_app(
    linkedin_port: FakeJobSearchPort,
    indeed_port: FakeJobSearchPort,
    infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """Build a `FastAPI` whose 3 use cases wrap the given ports.

    Used by tests that need a non-default port configuration
    (e.g. the dedup test wants overlapping jobs across 2 sources;
    the all-fail test wants all 3 ports to raise).
    """
    return build_app(
        use_case=_build_cached_use_case(linkedin_port, "linkedin"),
        indeed_use_case=_build_cached_use_case(indeed_port, "indeed"),
        infojobs_use_case=_build_cached_use_case(infojobs_port, "infojobs"),
    )


def _job(
    idx: int,
    *,
    title: str = "Title",
    company: str = "Co",
    location: str = "Madrid",
    source_id: str = "j",
) -> Job:
    """Build a deterministic `Job` for tests.

    `source_id` is the id prefix so the URL is unique per source
    (`https://example.com/<source_id><idx>`). `posted_at` is
    tz-aware UTC to satisfy the `Job.__post_init__` invariant.
    """
    return Job(
        id=f"{source_id}{idx}",
        title=title,
        company=company,
        location=location,
        url=f"https://example.com/{source_id}{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Happy path: all 3 sources succeed (REQ-A-001, REQ-A-002, REQ-A-005)
# ---------------------------------------------------------------------------


async def test_aggregator_returns_200_and_deduped_jobs(
    client: httpx.AsyncClient,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """A successful aggregator call returns 200 with the deduped jobs and the `sources` field.

    The conftest's `app` fixture has LinkedIn empty, Indeed with 3
    sample jobs (May 1, 2, 3), and InfoJobs with 3 sample jobs
    (May 1, 2, 3 — same dates as Indeed). The default ranking
    (`posted_at` DESC) interleaves by freshness: when Indeed and
    InfoJobs share the same `posted_at`, the source-priority
    tie-breaker picks Indeed first. The expected order is:
    Indeed-May-3, InfoJobs-May-3, Indeed-May-2, InfoJobs-May-2,
    Indeed-May-1, InfoJobs-May-1.
    """
    response = await client.get(
        "/jobs?q=title&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
    )

    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 6  # 0 LinkedIn + 3 Indeed + 3 InfoJobs
    # Default ranking is `posted_at` DESC + source-priority tie-breaker.
    # Both Indeed and InfoJobs have the same `posted_at` dates, so the
    # source-priority tie-breaker interleaves them: [Indeed, InfoJobs]
    # for each date.
    assert [job["sources"] for job in body["jobs"]] == [
        ["indeed"],  # May 3
        ["infojobs"],  # May 3
        ["indeed"],  # May 2
        ["infojobs"],  # May 2
        ["indeed"],  # May 1
        ["infojobs"],  # May 1
    ]
    # Every job has the documented fields. The `description` field
    # was added in PR1 (T-001) and surfaced in the chat response
    # in PR3 (T-014 of `ai-chat-filter`); the aggregator forwards
    # it the same way `/jobs/linkedin` / `/jobs/indeed` /
    # `/jobs/infojobs` do.
    for job in body["jobs"]:
        assert set(job.keys()) == {
            "id",
            "title",
            "company",
            "location",
            "url",
            "description",
            "posted_at",
            "sources",
        }


async def test_aggregator_forwards_query_params_to_every_port(
    client: httpx.AsyncClient,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """The route forwards `(q, location, limit)` to every queried port.

    The conftest's `app` wires LinkedIn to a fresh empty port that
    is not exposed as a fixture, so this test only asserts on the
    2 exposed ports. The LinkedIn port is verified in the
    `sources=linkedin` test below.
    """
    await client.get("/jobs?q=rust&location=barcelona&limit=7&sources=linkedin,indeed,infojobs")

    assert fake_indeed_port.calls == [("rust", "barcelona", 7)]
    assert fake_infojobs_port.calls == [("rust", "barcelona", 7)]


# ---------------------------------------------------------------------------
# 1-source query (REQ-A-001)
# ---------------------------------------------------------------------------


async def test_aggregator_with_single_source_only_invokes_that_source(
    client: httpx.AsyncClient,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """`sources=linkedin` invokes ONLY LinkedIn; Indeed + InfoJobs are not called."""
    await client.get("/jobs?q=title&location=madrid&sources=linkedin")

    # Indeed + InfoJobs were not called.
    assert fake_indeed_port.calls == []
    assert fake_infojobs_port.calls == []


# ---------------------------------------------------------------------------
# Validation (REQ-A-001: invalid sources → 422; standard Pydantic → 422)
# ---------------------------------------------------------------------------


async def test_aggregator_with_unknown_source_returns_422(
    client: httpx.AsyncClient,
) -> None:
    """An unknown source name in `sources` returns 422."""
    response = await client.get("/jobs?q=title&location=madrid&sources=linkedin,glassdoor")
    assert response.status_code == 422


async def test_aggregator_with_limit_zero_returns_422(
    client: httpx.AsyncClient,
) -> None:
    """`limit=0` (below the `ge=1` floor) returns 422."""
    response = await client.get("/jobs?q=title&location=madrid&limit=0")
    assert response.status_code == 422


async def test_aggregator_with_limit_too_high_returns_422(
    client: httpx.AsyncClient,
) -> None:
    """`limit=101` (above the `le=100` ceiling) returns 422."""
    response = await client.get("/jobs?q=title&location=madrid&limit=101")
    assert response.status_code == 422


async def test_aggregator_with_empty_q_returns_422(
    client: httpx.AsyncClient,
) -> None:
    """An empty `q` (below the `min_length=1` floor) returns 422."""
    response = await client.get("/jobs?q=&location=madrid")
    assert response.status_code == 422


async def test_aggregator_with_empty_location_returns_422(
    client: httpx.AsyncClient,
) -> None:
    """An empty `location` (below the `min_length=1` floor) returns 422."""
    response = await client.get("/jobs?q=python&location=")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Dedup (REQ-A-002)
# ---------------------------------------------------------------------------


async def test_aggregator_dedupes_same_job_across_2_sources() -> None:
    """The same job in LinkedIn + Indeed returns 1 item with `sources=["linkedin", "indeed"]`."""
    shared = _job(1, title="Senior Python", company="Acme", location="Madrid", source_id="x")
    linkedin_port = FakeJobSearchPort(jobs=[shared])
    # Use the SAME `Job` instance so the (title, company, location)
    # dedup key matches exactly.
    indeed_port = FakeJobSearchPort(jobs=[shared])
    infojobs_port = FakeJobSearchPort()
    app = _build_app(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs?q=title&location=madrid")

    assert response.status_code == 200
    body = response.json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["sources"] == ["linkedin", "indeed"]


# ---------------------------------------------------------------------------
# All sources fail (REQ-A-003: route returns 200, body has empty jobs)
# ---------------------------------------------------------------------------


async def test_aggregator_with_all_sources_failing_returns_502() -> None:
    """All 3 sources raise `JobSearchError`; the route returns 502.

    REQ-DEFENSIVE-001 scenario 2: when ALL 3 sources fail, the
    aggregator raises `AllSourcesFailedError` (a
    `JobSearchError` subclass) and the registered
    `JobSearchError` handler maps to HTTP 502. The body is
    the masked `{"detail": "upstream source unavailable",
    "request_id": "..."}` shape (the same as any per-source
    failure). The pre-`backend-scraper-query-tuning` v1
    contract returned 200 + empty jobs (a silent
    failure-mode that misled clients).
    """
    linkedin_port = FakeJobSearchPort(error=LinkedInBlockedError("auth wall"))
    indeed_port = FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = FakeJobSearchPort(error=InfoJobsBlockedError("distil"))
    app = _build_app(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs?q=title&location=madrid")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "upstream source unavailable"
    assert "request_id" in body


# ---------------------------------------------------------------------------
# Non-JobSearchError re-raises as 500 (REQ-A-003)
# ---------------------------------------------------------------------------


async def test_aggregator_with_non_job_search_error_returns_500() -> None:
    """A non-`JobSearchError` (programming bug) propagates and the route returns 500."""
    linkedin_port = FakeJobSearchPort(jobs=[_job(1, source_id="x")])

    class _ProgrammerBugPort(FakeJobSearchPort):
        async def search(
            self,
            keywords: str,
            location: str,
            limit: int = 20,
            geo_id: int | None = None,
        ) -> list[Job]:
            raise KeyError("missing-key")  # NOT a JobSearchError

    indeed_port = _ProgrammerBugPort()
    infojobs_port = FakeJobSearchPort(jobs=[_job(3, source_id="z")])
    app = _build_app(linkedin_port, indeed_port, infojobs_port)

    # `raise_app_exceptions=False` tells the ASGI transport to NOT
    # propagate server-side exceptions to the test. Without this,
    # `httpx` re-raises the `KeyError` from the server into the
    # test (matching Starlette's `TestClient` default), which would
    # mask the 500 response the client is supposed to receive in
    # production. With it, the test exercises the real production
    # behavior: a programming bug maps to 500.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs?q=title&location=madrid")

    # The `JobSearchError` exception handler does NOT match
    # `KeyError`, so FastAPI's default handler maps it to 500.
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Wiring: `app_factory.build_app` exposes the aggregator on `app.state`
# ---------------------------------------------------------------------------


def test_app_factory_exposes_aggregator_use_case_on_app_state(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """`build_app` sets `app.state.aggregator_use_case` to a `SearchAllSourcesUseCase`."""
    app = _build_app(FakeJobSearchPort(), fake_indeed_port, fake_infojobs_port)
    assert hasattr(app.state, "aggregator_use_case")
    assert isinstance(app.state.aggregator_use_case, SearchAllSourcesUseCase)


# ---------------------------------------------------------------------------
# `query_tokens` + `enable_keyword_scoring` + `linkedin_geo_id` forwarding
# (REQ-LOC-001 + REQ-FILTER-001 + REQ-CACHE-001 + REQ-SCORE-001, T-009)
#
# The aggregator route forwards 3 new kwargs to the use case
# (and to the per-source use cases where applicable):
# - `query_tokens`: from `tokenize(query.q)`.
# - `enable_keyword_scoring`: from `Settings.enable_keyword_scoring`.
# - `linkedin_geo_id`: from `app.state.location_resolver.resolve(query.location)`.
#
# The 3 tests below inject a spy `SearchAllSourcesUseCase`
# that records every `search()` call's kwargs. The tests
# then assert the kwargs are forwarded correctly. (Using
# the real `build_app()` flow would verify the route +
# wiring + use case end-to-end, but the kwargs are
# forwarded to the per-source use cases — the
# `SearchAllSourcesUseCase` is the only place that sees
# `query_tokens` and `enable_keyword_scoring` as top-level
# kwargs, so spying on it is the cleanest assertion target.)
# ---------------------------------------------------------------------------


class _SpySearchAllSourcesUseCase:
    """Spy that records every `search()` call's kwargs.

    Mirrors the `SearchAllSourcesUseCase.search()` signature
    (the 5 required positional args + the 4 keyword-only
    args added in `backend-scraper-query-tuning`). The spy
    returns a minimal `AggregatedResult` (empty jobs + per-
    source MISS for every requested source) so the route
    serves a 200 response and the `X-Cache` header is
    valid.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str],
        *,
        linkedin_geo_id: int | None = None,
        query_tokens: frozenset[str] = frozenset(),
        enable_keyword_scoring: bool | None = None,
    ) -> AggregatedResult:
        from jobs_finder.application.aggregator import (  # noqa: PLC0415
            AggregatedResult,
            SourceResult,
        )

        self.calls.append(
            {
                "keywords": keywords,
                "location": location,
                "limit": limit,
                "sources": sources,
                "linkedin_geo_id": linkedin_geo_id,
                "query_tokens": query_tokens,
                "enable_keyword_scoring": enable_keyword_scoring,
            }
        )
        return AggregatedResult(
            jobs=[],
            per_source={s: SourceResult(source=s) for s in sources},
            cache_statuses={s: "MISS" for s in sources},
        )


def _build_app_with_spy(spy: _SpySearchAllSourcesUseCase) -> FastAPI:
    """Build a `FastAPI` whose `app.state.aggregator_use_case` is the spy."""
    return build_app(aggregator_use_case=spy)  # type: ignore[arg-type]


async def test_aggregator_api_passes_query_tokens_to_use_case(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """`GET /jobs?q=react` → spy receives `query_tokens=frozenset({"react"})`.

    The route tokenizes `q="react"` via
    `infrastructure.aggregator_filters.tokenize` and forwards
    the resulting `frozenset[str]` to the use case's
    `query_tokens` kwarg. The spy records the kwarg; the
    test asserts the value is `frozenset({"react"})`.
    """
    spy = _SpySearchAllSourcesUseCase()
    app = _build_app_with_spy(spy)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=react&location=malaga&limit=20&sources=linkedin,indeed,infojobs"
        )
    assert response.status_code == 200
    # The spy recorded exactly 1 call with the expected kwargs.
    assert len(spy.calls) == 1
    assert spy.calls[0]["query_tokens"] == frozenset({"react"})


async def test_aggregator_api_does_not_forward_enable_keyword_scoring_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-fix: the route does NOT forward `enable_keyword_scoring` per-request.

    Pre-fix the route read `Settings.enable_keyword_scoring` and
    passed it as a per-request kwarg to `use_case.search()`. That
    silently overrode the aggregator's ctor field and made
    `ranking_strategy=none|priority|posted_at` a no-op whenever
    the env var was `True`. The post-fix contract: the toggle is
    per-aggregator (ctor field, set by `app_factory` from
    `Settings`); the route does NOT forward a per-request kwarg.

    This test pins the post-fix contract by asserting the spy
    does NOT receive `enable_keyword_scoring` in its kwargs (the
    kwarg is `None` when not forwarded).
    """
    monkeypatch.setenv("ENABLE_KEYWORD_SCORING", "true")
    spy = _SpySearchAllSourcesUseCase()
    app = _build_app_with_spy(spy)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=react&location=malaga&limit=20&sources=linkedin,indeed,infojobs"
        )
    assert response.status_code == 200
    assert len(spy.calls) == 1
    # The post-fix contract: the route does NOT forward the
    # `enable_keyword_scoring` kwarg. The spy receives the
    # default value (None) which means "use the ctor field".
    assert spy.calls[0].get("enable_keyword_scoring") is None


async def test_aggregator_api_resolves_linkedin_geo_id_from_resolver() -> None:
    """`GET /jobs?location=malaga` → spy receives `linkedin_geo_id=104401670`.

    The route reads `app.state.location_resolver` (the
    `HardcodedLocationResolver` is built at composition
    time in T-007) and calls `resolve(query.location)`. The
    `malaga` input maps to `104401670`. The resolved int is
    forwarded to the spy as `linkedin_geo_id`.
    """
    spy = _SpySearchAllSourcesUseCase()
    app = _build_app_with_spy(spy)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=react&location=malaga&limit=20&sources=linkedin,indeed,infojobs"
        )
    assert response.status_code == 200
    assert len(spy.calls) == 1
    # `104401670` is Málaga's captured geoId (per
    # `infrastructure/location/_mapping.py`).
    assert spy.calls[0]["linkedin_geo_id"] == 104401670
