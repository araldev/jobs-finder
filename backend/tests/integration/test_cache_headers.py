"""Integration tests for the `X-Cache: HIT|MISS` response header on all 3 routes.

Spec: REQ-C-003 (X-Cache header set on every 200 response).

The header is set by the route handler from
`SearchResult.cache_status.value` (the source of truth is the
cached use case; the route just maps the enum to a header). The
test exercises 3 routes × 2 scenarios = 6 tests:

  - First call: `X-Cache: MISS`
  - Second call within TTL: `X-Cache: HIT`

This test file is the RED → GREEN → REFACTOR anchor for T-005.
It must be authored BEFORE the route handlers set the header, run
to confirm it fails (RED), then the routes are updated, then the
tests pass (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# LinkedIn — MISS on first, HIT on second
# ---------------------------------------------------------------------------


async def test_linkedin_x_cache_miss_on_first_call(client: httpx.AsyncClient) -> None:
    """A fresh `GET /jobs/linkedin` returns `X-Cache: MISS`."""
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


async def test_linkedin_x_cache_hit_on_second_call(client: httpx.AsyncClient) -> None:
    """A second `GET /jobs/linkedin` within the TTL returns `X-Cache: HIT`."""
    first = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    second = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# Indeed — MISS on first, HIT on second
# ---------------------------------------------------------------------------


async def test_indeed_x_cache_miss_on_first_call(client: httpx.AsyncClient) -> None:
    """A fresh `GET /jobs/indeed` returns `X-Cache: MISS`."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


async def test_indeed_x_cache_hit_on_second_call(client: httpx.AsyncClient) -> None:
    """A second `GET /jobs/indeed` within the TTL returns `X-Cache: HIT`."""
    first = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    second = await client.get("/jobs/indeed?keywords=python&location=madrid")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# InfoJobs — MISS on first, HIT on second
# ---------------------------------------------------------------------------


async def test_infojobs_x_cache_miss_on_first_call(client: httpx.AsyncClient) -> None:
    """A fresh `GET /jobs/infojobs` returns `X-Cache: MISS`."""
    response = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"


async def test_infojobs_x_cache_hit_on_second_call(client: httpx.AsyncClient) -> None:
    """A second `GET /jobs/infojobs` within the TTL returns `X-Cache: HIT`."""
    first = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert first.headers.get("X-Cache") == "MISS"
    second = await client.get("/jobs/infojobs?keywords=python&location=madrid")
    assert second.status_code == 200
    assert second.headers.get("X-Cache") == "HIT"


# ---------------------------------------------------------------------------
# Header value contract: the literal strings are "HIT" and "MISS" (uppercase)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected_first"),
    [
        ("/jobs/linkedin?keywords=python&location=madrid", "MISS"),
        ("/jobs/indeed?keywords=python&location=madrid", "MISS"),
        ("/jobs/infojobs?keywords=python&location=madrid", "MISS"),
    ],
)
async def test_x_cache_header_value_is_uppercase(
    client: httpx.AsyncClient, path: str, expected_first: str
) -> None:
    """The `X-Cache` header value is `"HIT"` or `"MISS"` (uppercase, exact string).

    The value is the `CacheStatus` enum's `.value` (REQ-C-003). The
    test pins the exact string so a future refactor that accidentally
    lowercases or otherwise transforms the value surfaces here.
    """
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == expected_first


async def test_x_cache_header_value_on_hit_is_exactly_uppercase_hit(
    client: httpx.AsyncClient,
) -> None:
    """A HIT response has `X-Cache: HIT` (exact uppercase, no quotes)."""
    await client.get("/jobs/linkedin?keywords=python&location=madrid")  # MISS
    second = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert second.headers.get("X-Cache") == "HIT"
    # Also check the value is the exact bytes "HIT" — not "Hit", "hit", or quoted.
    assert second.headers["X-Cache"] == "HIT"
