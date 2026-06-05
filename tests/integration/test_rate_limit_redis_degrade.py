"""Integration tests for the Redis rate-limiter's fail-open behavior.

Spec: REQ-RL-003 + REQ-RL-009 (Redis-degrade scenario).

When the rate-limiter Redis client is unreachable, the middleware
MUST fail open (return 200, log WARNING) — never 5xx. This is the
asymmetric-to-cache contract: the cache fail-fasts on startup, the
rate-limiter degrades to "no throttling" on outage (the rate
limiter is optional, the cache is not).

The test points the rate-limiter Redis at a port that refuses
connections (port 1, reserved). The lifespan starts successfully
(NO ping), and a subsequent request returns 200 + WARNING logged.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(
    app_with_redis_rate_limit_unreachable: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app with a broken Redis."""
    transport = httpx.ASGITransport(app=app_with_redis_rate_limit_unreachable)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-RL-003 / REQ-RL-009 — Redis unreachable → 200 + WARNING
# ---------------------------------------------------------------------------


async def test_redis_unreachable_returns_200_and_logs_warning(
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request to a broken-Redis rate limiter returns 200 + WARNING logged.

    REQ-RL-003 scenario 3 (fail-open) + REQ-RL-009 (no lifespan
    ping). The rate limiter is OPTIONAL — a Redis outage degrades
    to "no throttling", never 5xx. The app starts successfully
    (no ping on startup) and a subsequent request returns 200
    with the 3 X-RateLimit-* headers (the fail-open decision
    reports `allowed=True` with `remaining=capacity`).
    """
    with caplog.at_level(
        logging.WARNING, logger="jobs_finder.infrastructure.rate_limit.redis_token_bucket"
    ):
        response = await client.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 200
    # The X-RateLimit-* headers ARE set (the fail-open decision
    # reports `remaining=capacity`).
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    # A WARNING was logged with the op + key + error.
    assert any("op=try_acquire" in rec.message for rec in caplog.records), (
        "expected WARNING with op=try_acquire to be logged"
    )
