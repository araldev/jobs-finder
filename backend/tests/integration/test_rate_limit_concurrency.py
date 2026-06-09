"""Integration tests for the rate-limiter under concurrent load.

Spec: REQ-RL-002 concurrency + REQ-RL-003 Lua atomicity (folded).

10 concurrent `GET /jobs/linkedin` requests against a `capacity=3`
bucket must yield exactly 3×200 + 7×429. The race in concurrent
in-memory `try_acquire` is the most likely regression; this test
pins it. The test uses the `app_with_rate_limit_concurrent` fixture
which sets `rate_limit_requests=3` so 7 are denied.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
async def client(
    app_with_rate_limit_concurrent: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app with `capacity=3`."""
    transport = httpx.ASGITransport(app=app_with_rate_limit_concurrent)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_ten_concurrent_requests_yield_exactly_three_allowed_seven_denied(
    client: httpx.AsyncClient,
) -> None:
    """10 concurrent requests against `capacity=3` yield 3×200 + 7×429.

    The per-key `asyncio.Lock` (in-memory) serializes the
    read-modify-write of the token bucket, so 10 concurrent
    acquires against the same key allow exactly `capacity` and
    deny the rest. The middleware's response code is the
    observable: 200 on allow, 429 on deny.
    """
    responses = await asyncio.gather(
        *(client.get("/jobs/linkedin?keywords=python&location=madrid") for _ in range(10))
    )
    allowed = [r for r in responses if r.status_code == 200]
    denied = [r for r in responses if r.status_code == 429]
    assert len(allowed) == 3, f"expected exactly 3×200, got {len(allowed)}"
    assert len(denied) == 7, f"expected exactly 7×429, got {len(denied)}"
