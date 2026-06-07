"""Integration tests for the InfoJobs FastAPI route.

Spec: REQ-J-001..REQ-J-006 (composition surface). Drives the FastAPI
app in-process with `httpx.AsyncClient` over `ASGITransport`. The
InfoJobs use case is constructed against the `fake_infojobs_port`
from `tests/conftest.py` so the suite never launches a browser and
never contacts InfoJobs.

The scenarios mirror `test_indeed_api.py` 1:1 where the contracts
are equivalent (200 happy, 422 missing/invalid, 502 with masked
detail, `X-Request-Id` echo, `/health` independence) and add the
InfoJobs-specific canonical URL contract (`/ofertas-trabajo/oferta-{id}`).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

from jobs_finder.infrastructure.infojobs.exceptions import InfoJobsBlockedError
from tests.conftest import FakeJobSearchPort

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
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app.

    Uses the conftest `app` fixture (which wires ALL THREE use cases —
    LinkedIn + Indeed + InfoJobs — to fake ports) so InfoJobs and
    the other routes are all reachable.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-J-001 — happy path
# ---------------------------------------------------------------------------


async def test_get_jobs_infojobs_returns_three_jobs_with_all_six_fields(
    client: httpx.AsyncClient, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """The 200 response has `jobs: [...]` with exactly the 6 spec fields per job.

    The InfoJobs canonical URL contract is `https://{domain}/ofertas-trabajo/oferta-{id}`
    (REQ-J-001): the parser strips the `/oferta-` prefix from the
    title-anchor `href` and rebuilds the canonical URL. The route
    must faithfully forward whatever the use case returns.
    """
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid")

    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 3

    for job in body["jobs"]:
        assert set(job.keys()) == JOB_FIELDS

    first = body["jobs"][0]
    assert first["id"] == "abc123def"  # parser extracts the slug from the href
    assert first["title"] == "InfoJobs Title 1"
    assert first["company"] == "InfoJobs Co 1"
    assert first["location"] == "Madrid, Spain"
    assert first["url"] == "https://www.infojobs.net/ofertas-trabajo/oferta-abc123def"
    assert first["posted_at"] is not None


async def test_get_jobs_infojobs_forwards_keywords_location_and_default_limit(
    client: httpx.AsyncClient, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """The default `limit=20` from the Pydantic schema reaches the port."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid")

    assert response.status_code == 200
    assert fake_infojobs_port.calls == [("python", "madrid", 20)]


async def test_get_jobs_infojobs_forwards_explicit_limit(
    client: httpx.AsyncClient, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """`limit=5` is forwarded to the port unchanged."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=5")

    assert response.status_code == 200
    assert fake_infojobs_port.calls == [("python", "madrid", 5)]


# ---------------------------------------------------------------------------
# REQ-J-005/REQ-J-006 — missing required query params -> 422
# ---------------------------------------------------------------------------


async def test_missing_keywords_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `keywords` returns 422 mentioning `keywords`."""
    response = await client.get("/jobs/infojobs?location=madrid")

    assert response.status_code == 422
    assert "keywords" in str(response.json())


async def test_missing_location_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `location` returns 422 mentioning `location`."""
    response = await client.get("/jobs/infojobs?keywords=python")

    assert response.status_code == 422
    assert "location" in str(response.json())


# ---------------------------------------------------------------------------
# REQ-J-005/REQ-J-006 — limit out of range -> 422
# ---------------------------------------------------------------------------


async def test_limit_zero_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=0` is below `ge=1` and returns 422."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=0")
    assert response.status_code == 422


async def test_limit_101_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=101` is above `le=100` and returns 422."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=101")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# REQ-J-006 — scraper failure -> 502 with masked detail
# ---------------------------------------------------------------------------


async def test_infojobs_blocked_returns_502_with_masked_detail(
    app: FastAPI, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """`InfoJobsBlockedError` becomes 502 with masked detail + request_id.

    The body MUST NOT leak the `InfoJobsBlockedError` type or message
    (the upstream source name is internal information). Same shape
    as the Indeed 502 contract.
    """
    fake_infojobs_port._error = InfoJobsBlockedError("distil challenge")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs/infojobs?keywords=python&location=madrid")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "upstream source unavailable"
    # The original exception type and message MUST NOT leak.
    assert "InfoJobsBlockedError" not in str(body)
    assert "distil" not in str(body)
    # `request_id` is present and non-empty.
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"]


# ---------------------------------------------------------------------------
# REQ-J-006 — X-Request-Id echo + correlation
# ---------------------------------------------------------------------------


async def test_x_request_id_propagates_through_502_body_and_header(
    app: FastAPI, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """A client-provided `X-Request-Id` is echoed in BOTH header and 502 body."""
    fake_infojobs_port._error = InfoJobsBlockedError("distil challenge")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs/infojobs?keywords=python&location=madrid",
            headers={"X-Request-Id": "infojobs-trace-1"},
        )

    assert response.status_code == 502
    body = response.json()
    assert response.headers.get("X-Request-Id") == "infojobs-trace-1"
    assert body["request_id"] == "infojobs-trace-1"


async def test_x_request_id_is_echoed_on_successful_200(
    client: httpx.AsyncClient,
) -> None:
    """A client-provided `X-Request-Id` is echoed on success too."""
    response = await client.get(
        "/jobs/infojobs?keywords=python&location=madrid",
        headers={"X-Request-Id": "ok-trace-infojobs"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "ok-trace-infojobs"


# ---------------------------------------------------------------------------
# REQ-J-006 — /health independence
# ---------------------------------------------------------------------------


async def test_health_returns_ok_without_calling_infojobs_port(
    client: httpx.AsyncClient, fake_infojobs_port: FakeJobSearchPort
) -> None:
    """`GET /health` is 200, body `{"status":"ok"}`, and the InfoJobs port is NEVER called.

    The test confirms the InfoJobs route AND the `/health` route
    coexist on the same app without one calling the other.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_infojobs_port.calls == []
