"""End-to-end smoke test for the BOTH-sources composition (T-012).

Spec: REQ-I-014, REQ-I-016, REQ-I-018.

The composition root must serve BOTH `/jobs/linkedin` and `/jobs/indeed`
in the same FastAPI app. This smoke test drives BOTH routes against
fake ports in-process and asserts the BOTH-sources composition is
wired correctly. The test exists to give the verify phase a single
end-to-end pass that exercises the whole stack EXCEPT the live
Playwright browser — no live scraping here (REQ-I-016), just an
in-process composition check.

The test does NOT cover:
  - The parser contract (covered by `test_indeed_parsers.py`).
  - The scraper's pagination or block-page detection (covered by
    `test_indeed_scraper.py`).
  - 422 / 502 / X-Request-Id (covered by `test_indeed_api.py`).

The scope is intentionally narrow: prove that the composition wires
BOTH sources and that both routes return the documented 200 shape
when a fake port is injected.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_indeed_jobs import SearchJobsUseCase
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort


def _linkedin_job(idx: int) -> Job:
    return Job(
        id=f"385000000{idx}",
        title=f"Smoke LinkedIn {idx}",
        company=f"Co LinkedIn {idx}",
        location="Madrid, Spain",
        url=f"https://www.linkedin.com/jobs/view/385000000{idx}/",
        posted_at=datetime(2026, 5, idx, tzinfo=UTC),
    )


def _indeed_job(idx: int) -> Job:
    return Job(
        id=f"10000000{idx}",
        title=f"Smoke Indeed {idx}",
        company=f"Co Indeed {idx}",
        location="Madrid, Spain",
        url=f"https://es.indeed.com/viewjob?jk=10000000{idx}",
        posted_at=datetime(2026, 5, idx, tzinfo=UTC),
    )


@pytest.fixture
def both_sources_app() -> FastAPI:
    """A `FastAPI` app whose BOTH use cases share a single fake port.

    The same `FakeJobSearchPort` (primed with 2 jobs) is wired into
    BOTH the LinkedIn and the Indeed use cases. The smoke test does
    not care which source the jobs come from — it just cares that
    BOTH routes return 200 with the documented `{"jobs": [...]}` shape
    against the composition root.
    """
    shared_port = FakeJobSearchPort(jobs=[_linkedin_job(1), _indeed_job(1)])
    return build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=shared_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
        indeed_use_case=SearchJobsUseCase(port=shared_port),
    )


@pytest.fixture
async def both_sources_client(
    both_sources_app: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the BOTH-sources app."""
    transport = httpx.ASGITransport(app=both_sources_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_linkedin_route_returns_two_jobs_in_smoke(
    both_sources_client: httpx.AsyncClient,
) -> None:
    """`/jobs/linkedin` returns 200 with `{"jobs": [...]}` (limit=2)."""
    response = await both_sources_client.get(
        "/jobs/linkedin?keywords=python&location=madrid&limit=2",
    )
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert isinstance(body["jobs"], list)
    assert len(body["jobs"]) == 2


async def test_indeed_route_returns_two_jobs_in_smoke(
    both_sources_client: httpx.AsyncClient,
) -> None:
    """`/jobs/indeed` returns 200 with `{"jobs": [...]}` (limit=2)."""
    response = await both_sources_client.get(
        "/jobs/indeed?keywords=python&location=madrid&limit=2",
    )
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert isinstance(body["jobs"], list)
    assert len(body["jobs"]) == 2


async def test_health_returns_ok_with_both_sources_wired(
    both_sources_client: httpx.AsyncClient,
) -> None:
    """`GET /health` is 200 `{"status":"ok"}` even when BOTH use cases are wired.

    Mirrors the LinkedIn /health independence invariant from
    `test_api.py::test_health_returns_ok_without_calling_port`, but
    for the BOTH-sources composition. The liveness probe must not
    trigger any port call regardless of how many sources are wired.
    """
    response = await both_sources_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
