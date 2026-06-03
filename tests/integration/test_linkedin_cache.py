"""Integration tests for the `cache-ttl` change on the LinkedIn route.

Spec: REQ-C-003 (X-Cache header), REQ-C-005 (per-source isolation).

The LinkedIn use case is the first of the 3 source use cases to
gain a `CachedJobSearchUseCase` wrapper. The composition root
(`app_factory.build_app()`) builds a `CachedJobSearchUseCase` by
default for the LinkedIn source. The route handler reads the
`SearchResult.cache_status` and sets the `X-Cache: HIT|MISS`
response header.

This test file is the RED → GREEN → REFACTOR anchor for T-003.
It must be authored BEFORE the wiring is changed, run to confirm
it fails (RED), then the wiring is changed, then the test passes
(GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

# LinkedIn source uses an empty fake port (no jobs needed) — the
# wrapper will return an empty list on miss.
JOB_FIELDS: set[str] = {"id", "title", "company", "location", "url", "posted_at"}


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
# REQ-C-003 — X-Cache: MISS on the first call
# ---------------------------------------------------------------------------


async def test_linkedin_first_call_returns_x_cache_miss(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """The first `GET /jobs/linkedin` returns `X-Cache: MISS`.

    The cache is empty (a fresh cache per test), so the wrapper
    invokes the port and the `cache_status` is `MISS`.
    """
    # The conftest `app` fixture already provides a fresh `InMemoryTTLCache`
    # for each test. Use the `client` to drive a request.
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


# ---------------------------------------------------------------------------
# REQ-C-003 — X-Cache: HIT on the second call within TTL
# ---------------------------------------------------------------------------


async def test_linkedin_second_call_returns_x_cache_hit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """The second `GET /jobs/linkedin` within the TTL returns `X-Cache: HIT`.

    The first call populated the cache (MISS), the second call
    serves from the cache (HIT). The port is invoked only once
    across both calls.
    """
    # First call: MISS.
    first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert first.status_code == 200
    assert first.headers.get("X-Cache") == "MISS"

    # Second call: HIT.
    second = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# REQ-C-005 — per-source isolation (LinkedIn only; Indeed + InfoJobs
# are wired in T-004. The cross-source isolation test lives in
# `tests/integration/test_cache_headers.py` (T-005) once all 3
# routes emit the header.)
# ---------------------------------------------------------------------------


async def test_linkedin_cache_is_fresh_per_test(client: httpx.AsyncClient) -> None:
    """Each test gets a fresh LinkedIn cache (no leakage from prior tests).

    The conftest `app` fixture builds a new `InMemoryTTLCache` for
    each test, so the first call in this test MUST be a MISS even
    if a prior test populated the cache with the same query.
    """
    # First call: MISS (empty cache).
    first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"


# ---------------------------------------------------------------------------
# Different limits bypass the cache (cache key includes `limit`)
# ---------------------------------------------------------------------------


async def test_different_limit_is_a_cache_miss(client: httpx.AsyncClient) -> None:
    """Two calls with the same keywords+location but different limits are
    independent cache entries. The second call is a MISS (different key).
    """
    # First call: default limit=20 → MISS.
    first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"

    # Second call: limit=5 (different cache key) → MISS.
    second = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=5")
    assert second.headers.get("X-Cache") == "MISS"

    # Third call: back to limit=20 → HIT (cache hit on the first call's key).
    third = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert third.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# Different keywords bypass the cache
# ---------------------------------------------------------------------------


async def test_different_keywords_is_a_cache_miss(client: httpx.AsyncClient) -> None:
    """Two calls with different keywords are independent cache entries."""
    first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"

    second = await client.get("/jobs/linkedin?keywords=rust&location=madrid")
    assert second.headers.get("X-Cache") == "MISS"

    # Repeat the first query: HIT.
    third = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert third.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# The route still returns the same JSON body shape (REQ-C-003 does not
# change the response contract)
# ---------------------------------------------------------------------------


async def test_linkedin_response_body_shape_is_unchanged(
    client: httpx.AsyncClient,
) -> None:
    """The cache wiring does NOT change the JSON response body shape.

    `body["jobs"]` is still a list of `JobResponse` objects with
    the 6 documented fields. The X-Cache header is ADDITIVE — it
    does not change the body.
    """
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert isinstance(body["jobs"], list)
    # The first call's X-Cache is MISS (empty port returns []).
    assert response.headers.get("X-Cache") == "MISS"
