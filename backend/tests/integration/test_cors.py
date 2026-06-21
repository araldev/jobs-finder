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
from pydantic import SecretStr

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
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
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    # CORS preflights return 200 with the CORS headers, not 405.
    # The dev default allowlist (see Settings._auto_cors_for_development)
    # is `["http://localhost:3000", "http://127.0.0.1:3000"]` — NOT `*`.
    # The Origin header MUST match one of the allowed origins for the
    # preflight to succeed (hardened dev default; the v1 `*` policy
    # would have allowed any origin).
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_options_preflight_advertises_get_method(
    client: httpx.AsyncClient,
) -> None:
    """The preflight lists the methods the endpoint actually accepts (`GET`).

    A browser will only fire the preflight if the advertised methods
    include the method of the actual request.

    T-009 (chat-streaming) — REQ-CORS-001: the preflight
    also advertises `POST` (the new `POST /jobs/chat/stream`
    endpoint shares the CORS middleware). The widening is
    strictly additive; the GET outcome is unchanged.
    """
    response = await client.options(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # `allow_methods=["GET", "POST"]` in CORSMiddleware → header lists both.
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods.upper()
    # T-009 — POST is now advertised (the v1 assertion widened).
    assert "POST" in allow_methods.upper()


async def test_options_preflight_for_post_jobs_chat_stream_succeeds(
    client: httpx.AsyncClient,
) -> None:
    """A preflight `OPTIONS /jobs/chat/stream` with POST method succeeds.

    REQ-CORS-001 1st scenario: the new SSE endpoint's
    preflight returns 200 (or 204) with the CORS headers
    so a browser at a different origin can call it.

    Note: when chat is DISABLED (the default `Settings`
    with no `LLM_API_KEY`), `POST /jobs/chat/stream`
    returns 404 because the route is NOT registered.
    The preflight itself is handled by the CORS
    middleware BEFORE the route is matched, so it
    still returns 200 with the CORS headers (the
    preflight is "yes, you can send a POST here"
    regardless of whether the underlying route exists).
    """
    response = await client.options(
        "/jobs/chat/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    # The preflight returns 200 with the CORS headers.
    assert response.status_code == 200
    # The CORS Allow-Origin echoes the dev-allowlisted origin (NOT `*`).
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    # Allow-Methods includes POST (and GET, for the per-source routes).
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods.upper()
    # Allow-Headers echoes the requested Content-Type.
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "content-type" in allow_headers.lower()


async def test_actual_post_to_chat_endpoint_cross_origin_succeeds(
    client: httpx.AsyncClient,
) -> None:
    """An actual `POST /jobs/chat` from a different origin returns 200 + CORS header.

    REQ-CORS-001 2nd scenario: when chat is ENABLED
    (the test below uses a `Settings(llm_filter_enabled=True,
    llm_api_key=...)` injection), the actual POST
    succeeds and the response carries the CORS header.
    A test that does NOT enable chat is below — this
    one DOES enable chat via a `Settings` injection
    so the chat route is registered.
    """
    settings = Settings(
        llm_filter_enabled=True,
        llm_api_key=SecretStr("test-key"),
        llm_base_url="https://api.example.invalid",  # not actually called
    )
    fake_port = FakeJobSearchPort(jobs=[])
    app = build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=fake_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
        settings=settings,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/jobs/chat/stream",
            json={"message": "python"},
            headers={"Origin": "http://localhost:3000"},
        )

    # The POST itself returns 200 (SSE) or 4xx (validation). The
    # important assertion is the CORS header — the dev allowlist
    # echoes the origin (NOT `*`).
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_get_request_carries_cors_allow_origin_header(
    client: httpx.AsyncClient,
) -> None:
    """A simple cross-origin `GET` also gets `Access-Control-Allow-Origin`.

    The actual request (not the preflight) must also include the
    CORS header so the browser will let the JS read the response body.
    """
    response = await client.get(
        "/jobs/linkedin?keywords=python&location=madrid",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    # Dev allowlist echoes the origin (NOT `*`).
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
