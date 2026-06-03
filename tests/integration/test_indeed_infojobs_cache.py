"""Integration tests for the `cache-ttl` change on the Indeed + InfoJobs routes.

Spec: REQ-C-003 (X-Cache header), REQ-C-005 (per-source isolation).

T-003 wired the cache for the LinkedIn route. T-004 mirrors the
pattern for the Indeed + InfoJobs routes. Each source has its
OWN `InMemoryTTLCache` instance in the default branch of
`app_factory.build_app()` so the 3 caches are independent
(REQ-C-005 — per-source isolation).

This test file is the RED → GREEN → REFACTOR anchor for T-004.
It must be authored BEFORE the wiring is changed, run to confirm
it fails (RED), then the wiring is changed, then the test passes
(GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Indeed — MISS / HIT
# ---------------------------------------------------------------------------


async def test_indeed_first_call_is_a_miss(client: httpx.AsyncClient) -> None:
    """A fresh Indeed call returns `MISS` (port invoked)."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


async def test_indeed_second_call_is_a_hit(client: httpx.AsyncClient) -> None:
    """A second Indeed call within the TTL returns `HIT` (port NOT invoked)."""
    first = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    second = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# InfoJobs — MISS / HIT
# ---------------------------------------------------------------------------


async def test_infojobs_first_call_is_a_miss(client: httpx.AsyncClient) -> None:
    """A fresh InfoJobs call returns `MISS` (port invoked)."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


async def test_infojobs_second_call_is_a_hit(client: httpx.AsyncClient) -> None:
    """A second InfoJobs call within the TTL returns `HIT` (port NOT invoked)."""
    first = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    second = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# Per-source isolation (REQ-C-005)
# ---------------------------------------------------------------------------


async def test_three_sources_have_independent_caches(
    client: httpx.AsyncClient,
) -> None:
    """The LinkedIn, Indeed, and InfoJobs caches are independent.

    A query that hits LinkedIn's cache does NOT serve a cached
    response on Indeed or InfoJobs — each source has its own
    `InMemoryTTLCache` instance and the cache key includes the
    source name (REQ-C-005).
    """
    # LinkedIn: first call → MISS, second call → HIT.
    li_first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    li_second = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert li_first.headers.get("X-Cache") == "MISS"
    assert li_second.headers.get("X-Cache") == "HIT"

    # Indeed: first call → MISS (LinkedIn cache hit doesn't affect it).
    in_first = await client.get("/jobs/indeed?keywords=python&location=madrid")
    in_second = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert in_first.headers.get("X-Cache") == "MISS"
    assert in_second.headers.get("X-Cache") == "HIT"

    # InfoJobs: first call → MISS (neither LinkedIn nor Indeed cache affect it).
    ij_first = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    ij_second = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert ij_first.headers.get("X-Cache") == "MISS"
    assert ij_second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# Different limits bypass the cache
# ---------------------------------------------------------------------------


async def test_indeed_different_limit_is_a_miss(client: httpx.AsyncClient) -> None:
    """Different `limit` values are independent cache keys."""
    first = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    # Different limit: independent cache entry.
    different_limit = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=5")
    assert different_limit.headers.get("X-Cache") == "MISS"
    # Back to limit=20: HIT.
    back = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert back.headers.get("X-Cache") == "HIT"


async def test_infojobs_different_limit_is_a_miss(client: httpx.AsyncClient) -> None:
    """Different `limit` values are independent cache keys (InfoJobs)."""
    first = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    different_limit = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=5")
    assert different_limit.headers.get("X-Cache") == "MISS"
    back = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert back.headers.get("X-Cache") == "HIT"
