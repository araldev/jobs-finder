"""Integration tests for the per-source observability headers on
`GET /jobs`.

Spec: REQ-A-006.
The aggregator response includes:
- `X-Cache: HIT,MISS,HIT` — one value per queried source in
  source-priority order (LinkedIn > Indeed > InfoJobs). Each
  value is `HIT` or `MISS` per the closed `cache-ttl` design.
- `X-Aggregator-Sources: linkedin,indeed,infojobs` — the sources
  that were queried, in source-priority order.
- `X-Aggregator-Errors: indeed` (or absent) — the sources that
  returned a 502 / `JobSearchError`, in source-priority order.
  Absent if all sources succeeded.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _build_cached_use_case(port: FakeJobSearchPort, source: str) -> CachedJobSearchUseCase:
    """Wrap a `FakeJobSearchPort` in a fresh cached wrapper."""
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


def _build_app_with_ports(
    linkedin_port: FakeJobSearchPort,
    indeed_port: FakeJobSearchPort,
    infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """Build a `FastAPI` with the 3 ports wrapped in cached use cases."""
    return build_app(
        use_case=_build_cached_use_case(linkedin_port, "linkedin"),
        indeed_use_case=_build_cached_use_case(indeed_port, "indeed"),
        infojobs_use_case=_build_cached_use_case(infojobs_port, "infojobs"),
    )


def _job(idx: int, source_id: str = "j") -> Job:
    """A deterministic `Job` for tests."""
    return Job(
        id=f"{source_id}{idx}",
        title=f"Title {idx}",
        company="Co",
        location="Madrid",
        url=f"https://example.com/{source_id}{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# All sources succeed (REQ-A-006: joined X-Cache + X-Aggregator-Sources, no
# X-Aggregator-Errors)
# ---------------------------------------------------------------------------


async def test_aggregator_headers_x_cache_joins_per_source_in_priority_order(
    client: httpx.AsyncClient,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """All sources succeed → `X-Cache: HIT,MISS,HIT` (one per source, in order).

    The 3 fake ports are pre-primed with the conftest's `app`
    fixture. The first call to each source is a MISS (the
    wrapper's `cache.get` returns `None`). So the joined header
    is `MISS,MISS,MISS` on the first call.
    """
    response = await client.get("/jobs?q=python&location=madrid&sources=linkedin,indeed,infojobs")

    assert response.status_code == 200
    # All 3 sources are queried, all cache MISSes (first call).
    assert response.headers["x-cache"] == "MISS,MISS,MISS"
    # Sources queried, in source-priority order.
    assert response.headers["x-aggregator-sources"] == "linkedin,indeed,infojobs"
    # No errors → header is absent.
    assert "x-aggregator-errors" not in response.headers


async def test_aggregator_headers_x_cache_second_call_is_all_hit(
    client: httpx.AsyncClient,
) -> None:
    """The second call within the TTL is all `HIT` (cache populated by the first call)."""
    # First call: populate the cache.
    await client.get("/jobs?q=python&location=madrid&sources=linkedin,indeed,infojobs")
    # Second call: all 3 sources are cache HITs.
    response = await client.get("/jobs?q=python&location=madrid&sources=linkedin,indeed,infojobs")

    assert response.status_code == 200
    assert response.headers["x-cache"] == "HIT,HIT,HIT"
    assert response.headers["x-aggregator-sources"] == "linkedin,indeed,infojobs"


# ---------------------------------------------------------------------------
# One source fails (REQ-A-006: X-Aggregator-Errors lists the failed source)
# ---------------------------------------------------------------------------


async def test_aggregator_headers_x_aggregator_errors_lists_only_failed_sources() -> None:
    """When Indeed fails, the header lists ONLY Indeed (in source-priority order).

    LinkedIn + InfoJobs succeed; Indeed raises IndeedBlockedError.
    The `X-Aggregator-Errors` header is the comma-separated list
    of failed sources in source-priority order, absent only when
    ALL sources succeed.
    """
    linkedin_port = FakeJobSearchPort(jobs=[_job(1, source_id="x")])
    indeed_port = FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = FakeJobSearchPort(jobs=[_job(2, source_id="z")])
    app = _build_app_with_ports(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs?q=python&location=madrid&sources=linkedin,indeed,infojobs")

    assert response.status_code == 200
    # LinkedIn (MISS) + Indeed (errored → MISS) + InfoJobs (MISS).
    # Indeed's cache_status stays "MISS" because the wrapper records
    # it on a miss even when the port raises.
    assert response.headers["x-cache"] == "MISS,MISS,MISS"
    assert response.headers["x-aggregator-sources"] == "linkedin,indeed,infojobs"
    assert response.headers["x-aggregator-errors"] == "indeed"


# ---------------------------------------------------------------------------
# 1-source query (REQ-A-006: single value, no commas in X-Cache)
# ---------------------------------------------------------------------------


async def test_aggregator_headers_single_source_no_commas_in_x_cache() -> None:
    """`sources=linkedin` produces `X-Cache: HIT` (single value, no commas)."""
    linkedin_port = FakeJobSearchPort(jobs=[_job(1, source_id="x")])
    # Indeed + InfoJobs are not invoked.
    indeed_port = FakeJobSearchPort()
    infojobs_port = FakeJobSearchPort()
    app = _build_app_with_ports(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs?q=python&location=madrid&sources=linkedin")

    assert response.status_code == 200
    assert response.headers["x-cache"] == "MISS"
    assert response.headers["x-aggregator-sources"] == "linkedin"
    assert "x-aggregator-errors" not in response.headers


# ---------------------------------------------------------------------------
# All sources fail (REQ-A-006: X-Aggregator-Errors lists ALL 3, body is empty)
# ---------------------------------------------------------------------------


async def test_aggregator_headers_all_sources_fail_lists_all_three_in_errors() -> None:
    """All 3 sources raise; the errors header lists all 3 in priority order."""
    linkedin_port = FakeJobSearchPort(error=LinkedInBlockedError("auth wall"))
    indeed_port = FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = FakeJobSearchPort(error=InfoJobsBlockedError("distil"))
    app = _build_app_with_ports(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs?q=python&location=madrid&sources=linkedin,indeed,infojobs")

    assert response.status_code == 200
    assert response.headers["x-cache"] == "MISS,MISS,MISS"
    assert response.headers["x-aggregator-errors"] == "linkedin,indeed,infojobs"
    # Body is empty (no successful source).
    assert response.json() == {"jobs": []}


# ---------------------------------------------------------------------------
# 2-source query (REQ-A-006: only the queried sources appear in the headers)
# ---------------------------------------------------------------------------


async def test_aggregator_headers_two_source_query_only_lists_those_sources() -> None:
    """`sources=linkedin,infojobs` lists only those 2 in the headers."""
    linkedin_port = FakeJobSearchPort(jobs=[_job(1, source_id="x")])
    indeed_port = FakeJobSearchPort(jobs=[_job(2, source_id="y")])  # not invoked
    infojobs_port = FakeJobSearchPort(jobs=[_job(3, source_id="z")])
    app = _build_app_with_ports(linkedin_port, indeed_port, infojobs_port)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs?q=python&location=madrid&sources=linkedin,infojobs")

    assert response.status_code == 200
    assert response.headers["x-cache"] == "MISS,MISS"  # Indeed NOT included
    assert response.headers["x-aggregator-sources"] == "linkedin,infojobs"  # Indeed NOT
    # Indeed was not called.
    assert indeed_port.calls == []
    assert "x-aggregator-errors" not in response.headers
