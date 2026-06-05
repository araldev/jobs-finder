"""Integration tests for the `RateLimitMiddleware` exempt paths.

Spec: REQ-RL-007 (exempt paths — default list, docs surface, env-var override, no headers).

`/health` is in `EXEMPT_UNCONDITIONAL` (hardcoded in the middleware) so
the k8s liveness probe never 429s the pod. `/docs`, `/openapi.json`,
and `/redoc` are appended to the effective exempt set by
`app_factory` so a `curl /docs` does not consume the bucket. All
exempt responses MUST NOT carry any `X-RateLimit-*` / `Retry-After`
header.

The 4 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
async def client(app_with_rate_limit: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app with rate limiting."""
    transport = httpx.ASGITransport(app=app_with_rate_limit)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-RL-007 — /health exempt (default)
# ---------------------------------------------------------------------------


async def test_health_is_exempt_by_default_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """11 back-to-back `GET /health` calls all return 200 with no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 1: `/health` exempt by default. The bucket
    is sized to `rate_limit_requests=2` (per the fixture), so a
    normal route would 429 on the 3rd call. `/health` is exempt
    and bypasses the limiter entirely (no `try_acquire` call, no
    `X-RateLimit-*` headers).
    """
    for _ in range(11):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        # No `X-RateLimit-*` headers on exempt responses.
        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers
        assert "Retry-After" not in response.headers


# ---------------------------------------------------------------------------
# REQ-RL-007 — /docs, /openapi.json, /redoc exempt (app_factory appends)
# ---------------------------------------------------------------------------


async def test_docs_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /docs` (FastAPI Swagger UI) is exempt — 200, no `X-RateLimit-*` headers.

    The default branch of `app_factory` unions
    `frozenset({"/docs", "/openapi.json", "/redoc"})` into the
    effective exempt set, so a `curl /docs` does not consume
    the bucket. REQ-RL-007 scenario 2.
    """
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


async def test_openapi_json_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /openapi.json` is exempt — 200, no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 3. The schema endpoint is part of the
    FastAPI docs surface and is unconditionally exempt.
    """
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


async def test_redoc_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /redoc` (FastAPI ReDoc UI) is exempt — 200, no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 4. The redoc endpoint is part of the
    FastAPI docs surface and is unconditionally exempt.
    """
    response = await client.get("/redoc")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers
