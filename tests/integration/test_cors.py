"""Integration tests for CORS preflight handling.

Spec: REQ-006. The FastAPI app MUST configure CORS as open (configurable
later). A browser preflight (`OPTIONS` with an `Origin` header) MUST come
back with the documented `Access-Control-Allow-*` headers so a JS client
on a different origin can call the API.

The middleware stack is exercised in-process with `httpx.AsyncClient` over
`ASGITransport`. The use case is wired to a `FakeJobSearchPort`; the port
is never invoked because CORS short-circuits the preflight before the
route runs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.presentation.app_factory import build_app

from .test_api import FakeJobSearchPort


@pytest.fixture
def app() -> FastAPI:
    """An app with an empty fake port (never called by these tests)."""
    fake_port = FakeJobSearchPort(jobs=[])
    return build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=fake_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_options_preflight_returns_cors_allow_origin_header(
    client: httpx.AsyncClient,
) -> None:
    """An OPTIONS preflight with an `Origin` header carries `Access-Control-Allow-Origin: *`.

    Spec: REQ-006. The default CORS policy is open (any origin) so
    a browser-based client can call the API in development.

    The preflight includes the standard `Access-Control-Request-Method`
    header that real browsers send; without it FastAPI's CORS
    middleware does not recognize the request as a preflight and
    the route returns 405.
    """
    response = await client.options(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # CORS preflights return 200 with the CORS headers, not 405.
    assert response.status_code == 200
    # The default `*` policy is set on Settings.cors_allow_origins.
    assert response.headers.get("access-control-allow-origin") == "*"


async def test_options_preflight_advertises_get_method(
    client: httpx.AsyncClient,
) -> None:
    """The preflight lists the methods the endpoint actually accepts (`GET`).

    A browser will only fire the preflight if the advertised methods
    include the method of the actual request.
    """
    response = await client.options(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # `allow_methods=["GET"]` in CORSMiddleware → header lists GET.
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods.upper()


async def test_get_request_carries_cors_allow_origin_header(
    client: httpx.AsyncClient,
) -> None:
    """A simple cross-origin `GET` also gets `Access-Control-Allow-Origin`.

    The actual request (not the preflight) must also include the
    CORS header so the browser will let the JS read the response body.
    """
    response = await client.get(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={"Origin": "http://example.com"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
