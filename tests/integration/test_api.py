"""Integration tests for the FastAPI presentation layer.

Spec: REQ-002, REQ-006, REQ-017, REQ-018, REQ-019, REQ-020, REQ-021, REQ-022.
Drives the FastAPI app in-process with `httpx.AsyncClient` over
`ASGITransport`. The use case is constructed against a `FakeJobSearchPort`
so the suite never launches a browser and never contacts LinkedIn.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.linkedin.exceptions import LinkedInBlockedError
from jobs_finder.presentation.app_factory import build_app

# ---------------------------------------------------------------------------
# Fake port
# ---------------------------------------------------------------------------


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort` for integration tests.

    Records every call so tests can assert the route forwarded the input
    correctly, including the default `limit=20`. Can be primed (or
    mutated) to raise an exception on the next call.
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
        self.calls.append((keywords, location, limit))
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _sample(idx: int) -> Job:
    """Build a Job with deterministic, unique fields per index."""
    return Job(
        id=f"385000000{idx}",
        title=f"Title {idx}",
        company=f"Company {idx}",
        location="Madrid, Spain",
        url=f"https://www.linkedin.com/jobs/view/385000000{idx}/",
        posted_at=datetime(2026, 5, idx, tzinfo=UTC),
    )


JOB_FIELDS: set[str] = {
    "id",
    "title",
    "company",
    "location",
    "url",
    "description",
    "posted_at",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_port() -> FakeJobSearchPort:
    """A fake port primed with 3 sample jobs, no error."""
    return FakeJobSearchPort(jobs=[_sample(1), _sample(2), _sample(3)])


@pytest.fixture
def app(fake_port: FakeJobSearchPort) -> FastAPI:
    """A FastAPI app whose use case is wired to the fake port.

    The `cache-ttl` change wraps the raw use case in a
    `CachedJobSearchUseCase`. The fixture builds the cached wrapper
    with a fresh `InMemoryTTLCache` (no shared state across tests)
    so the route's `X-Cache: HIT|MISS` header reflects the cache
    state per-test.
    """
    cached = CachedJobSearchUseCase(
        port=fake_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )
    return build_app(use_case=cached)


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-017 — happy path
# ---------------------------------------------------------------------------


async def test_get_jobs_linkedin_returns_three_jobs_with_all_six_fields(
    client: httpx.AsyncClient, fake_port: FakeJobSearchPort
) -> None:
    """The 200 response has `jobs: [...]` with exactly the 6 spec fields per job."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 3

    for job in body["jobs"]:
        assert set(job.keys()) == JOB_FIELDS

    # The first job's fields are populated from the fake.
    assert body["jobs"][0]["id"] == "3850000001"
    assert body["jobs"][0]["title"] == "Title 1"
    assert body["jobs"][0]["company"] == "Company 1"
    assert body["jobs"][0]["location"] == "Madrid, Spain"
    assert body["jobs"][0]["url"].startswith("https://")
    assert body["jobs"][0]["posted_at"] is not None


async def test_get_jobs_linkedin_forwards_keywords_location_and_default_limit(
    client: httpx.AsyncClient, fake_port: FakeJobSearchPort
) -> None:
    """The default `limit=20` from the Pydantic schema reaches the port."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 200
    # Default limit is 20 (design §5; Pydantic default).
    assert fake_port.calls == [("python", "madrid", 20)]


async def test_get_jobs_linkedin_forwards_explicit_limit(
    client: httpx.AsyncClient, fake_port: FakeJobSearchPort
) -> None:
    """`limit=5` is forwarded to the port unchanged."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=5")

    assert response.status_code == 200
    assert fake_port.calls == [("python", "madrid", 5)]


# ---------------------------------------------------------------------------
# REQ-018 — missing required query params → 422
# ---------------------------------------------------------------------------


async def test_missing_keywords_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `keywords` returns 422 mentioning `keywords`."""
    response = await client.get("/jobs/linkedin?location=madrid")

    assert response.status_code == 422
    assert "keywords" in str(response.json())


async def test_missing_location_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `location` returns 422 mentioning `location`."""
    response = await client.get("/jobs/linkedin?keywords=python")

    assert response.status_code == 422
    assert "location" in str(response.json())


async def test_empty_keywords_returns_422(client: httpx.AsyncClient) -> None:
    """An empty `keywords` (min_length=1) returns 422."""
    response = await client.get("/jobs/linkedin?keywords=&location=madrid")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# REQ-019 — limit out of range → 422
# ---------------------------------------------------------------------------


async def test_limit_zero_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=0` is below `ge=1` and returns 422."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=0")
    assert response.status_code == 422


async def test_limit_200_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=200` is above `le=100` and returns 422."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=200")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# REQ-020 — scraper failure → 502 with masked detail
# ---------------------------------------------------------------------------


async def test_scraper_blocked_returns_502_with_masked_detail(
    app: FastAPI, fake_port: FakeJobSearchPort
) -> None:
    """`LinkedInBlockedError` becomes 502 with masked detail + request_id."""
    fake_port._error = LinkedInBlockedError("auth wall")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "upstream source unavailable"
    # The original exception type MUST NOT leak.
    assert "LinkedInBlockedError" not in str(body)
    # `request_id` is present and non-empty.
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"]


async def test_x_request_id_propagates_through_502_body_and_header(
    app: FastAPI, fake_port: FakeJobSearchPort
) -> None:
    """A client-provided `X-Request-Id` is echoed in BOTH header and 502 body.

    One test that triggers a 502 with a known header value, then asserts
    the header is echoed in the response and the body's `request_id`
    matches the same value.
    """
    fake_port._error = LinkedInBlockedError("auth wall")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Request-Id": "my-trace-1"},
        )

    assert response.status_code == 502
    body = response.json()
    assert response.headers.get("X-Request-Id") == "my-trace-1"
    assert body["request_id"] == "my-trace-1"


async def test_x_request_id_is_generated_when_client_omits_header(
    app: FastAPI, fake_port: FakeJobSearchPort
) -> None:
    """When the client does not pass `X-Request-Id`, the middleware generates one.

    The generated id appears in both the response header and the body's
    `request_id` field.
    """
    fake_port._error = LinkedInBlockedError("auth wall")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 502
    body = response.json()
    header_id = response.headers.get("X-Request-Id")
    assert header_id is not None
    assert len(header_id) > 0
    assert body["request_id"] == header_id


async def test_x_request_id_is_echoed_on_successful_200(
    client: httpx.AsyncClient,
) -> None:
    """A client-provided `X-Request-Id` is echoed on success too (REQ-020 correlation)."""
    response = await client.get(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={"X-Request-Id": "ok-trace-1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "ok-trace-1"


# ---------------------------------------------------------------------------
# REQ-021 — health endpoint, no port call
# ---------------------------------------------------------------------------


async def test_health_returns_ok_without_calling_port(
    client: httpx.AsyncClient, fake_port: FakeJobSearchPort
) -> None:
    """`GET /health` is 200, body `{"status":"ok"}`, and the port is NEVER called."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_port.calls == []


# ---------------------------------------------------------------------------
# REQ-006 / REQ-002 — app metadata + handler shape
# ---------------------------------------------------------------------------


def test_app_is_a_fastapi_instance(app: FastAPI) -> None:
    """The factory returns a `FastAPI` instance with the documented title."""
    assert isinstance(app, FastAPI)
    assert app.title == "jobs-finder"


def test_linkedin_route_handler_is_async(app: FastAPI) -> None:
    """REQ-022: the `/jobs/linkedin` route handler is a coroutine function."""
    for route in app.routes:
        if getattr(route, "path", None) == "/jobs/linkedin":
            endpoint = getattr(route, "endpoint", None)
            assert callable(endpoint)
            assert inspect.iscoroutinefunction(endpoint)
            return
    pytest.fail("/jobs/linkedin route not found")
