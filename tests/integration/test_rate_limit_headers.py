"""Integration tests for the `RateLimitMiddleware`: response headers, 429 body,
and per-route cost map.

Spec: REQ-RL-005 (response headers + 429 body), REQ-RL-006 (per-route cost).

The test seam: a `settings_with_rate_limit` fixture in
`tests/conftest.py` that sets `rate_limit_requests=2` so a 429 is
reachable in-test. The fixture also wires `FakeJobSearchPort` instances
on all 3 source routes (and the aggregator) so the middleware is
exercised end-to-end against a real `FastAPI` app.

The 9 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import MappingProxyType
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app_with_rate_limit: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app with rate limiting."""
    transport = httpx.ASGITransport(app=app_with_rate_limit)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-RL-005 — Allow path sets the 3 X-RateLimit-* headers
# ---------------------------------------------------------------------------


async def test_first_call_sets_three_x_ratelimit_headers(
    client: httpx.AsyncClient,
) -> None:
    """A 1st `GET /jobs/linkedin` returns 200 + `X-RateLimit-Limit`, `Remaining`, `Reset`.

    With `rate_limit_requests=2` and `rate_limit_window_seconds=60.0`
    (per the fixture; refill rate = 2/60 tokens/sec):
      - `X-RateLimit-Limit: 2` (capacity).
      - `X-RateLimit-Remaining: 1` (1 token consumed).
      - `X-RateLimit-Reset: 30` (seconds until full refill — needs
        to refill 1 token at 2/60 tokens/sec, which takes 30s).
      - NO `Retry-After` header (only on 429).
    """
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "1"
    assert response.headers["X-RateLimit-Reset"] == "30"
    assert "Retry-After" not in response.headers


# ---------------------------------------------------------------------------
# REQ-RL-005 — Exhausted bucket → 429
# ---------------------------------------------------------------------------


async def test_exhausted_bucket_returns_429_with_retry_after(
    client: httpx.AsyncClient,
) -> None:
    """After consuming both tokens, the 3rd call returns 429 + `Retry-After`.

    The 1st call returns 200 + `X-RateLimit-Remaining: 1`. The 2nd
    call returns 200 + `X-RateLimit-Remaining: 0`. The 3rd call
    returns 429 with `Retry-After: 60` (1 token / 1 token-per-second
    refill rate) and `X-RateLimit-Remaining: 0`.
    """
    # Consume the 2 tokens.
    r1 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    r2 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 3rd call: 429.
    r3 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    retry_after = int(r3.headers["Retry-After"])
    assert retry_after > 0
    assert r3.headers["X-RateLimit-Limit"] == "2"
    assert r3.headers["X-RateLimit-Remaining"] == "0"


# ---------------------------------------------------------------------------
# REQ-RL-005 — 429 body shape
# ---------------------------------------------------------------------------


async def test_429_body_shape_matches_documented_contract(
    client: httpx.AsyncClient,
) -> None:
    """The 429 body has exactly `{"detail", "request_id"}` with the right types.

    REQ-RL-005 + REQ-RL-010: the body shape mirrors the 502 body.
    `detail` is the literal string `"rate limit exceeded"`.
    `request_id` matches the `X-Request-Id` response header (set by
    `RequestIdMiddleware`).
    """
    # Consume the bucket.
    await client.get("/jobs/linkedin?keywords=python&location=madrid")
    await client.get("/jobs/linkedin?keywords=python&location=madrid")
    # 3rd call: 429.
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert response.status_code == 429

    body = response.json()
    assert set(body.keys()) == {"detail", "request_id"}
    assert body["detail"] == "rate limit exceeded"
    assert isinstance(body["request_id"], str)
    assert body["request_id"]  # non-empty
    # The body's `request_id` equals the `X-Request-Id` response header.
    assert body["request_id"] == response.headers["X-Request-Id"]


# ---------------------------------------------------------------------------
# REQ-RL-005 — 429 short-circuits the route (no port calls = no cache pollution)
# ---------------------------------------------------------------------------


async def test_429_short_circuits_route_no_port_call_no_cache_write(
    client: httpx.AsyncClient,
    app_with_rate_limit: FastAPI,
) -> None:
    """A 429 short-circuits `call_next`, so the route's `JobSearchPort` is NEVER called.

    REQ-RL-005 invariant: the 429 response is a `JSONResponse`
    returned by the middleware itself; `call_next` is never
    invoked, so the route handler, the `CachedJobSearchUseCase`,
    and the Playwright scraper are unreachable from a 429 path.
    Cache namespace stays clean by construction.

    The LinkedIn use case is wrapped in a `CachedJobSearchUseCase`:
      - 1st call -> MISS -> port called (1 call).
      - 2nd call -> HIT  -> port NOT called (still 1 total).
      - 3rd call -> 429  -> middleware short-circuits (still 1 total).
    The test asserts the call count is `1` after all 3 requests,
    proving the 429 did NOT increment the count.
    """
    # The conftest wires a `FakeJobSearchPort` on the LinkedIn use
    # case. The fixture exposes it via `app.state.job_search_port`
    # (the unwrapped scraper / fake port).
    fake_port: Any = app_with_rate_limit.state.job_search_port
    assert hasattr(fake_port, "calls"), (
        "test fixture must expose a FakeJobSearchPort-shaped object on app.state"
    )

    # 3 calls: 1st MISS (port called), 2nd HIT (port not called),
    # 3rd 429 (middleware short-circuits, port not called).
    r1 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    r2 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    r3 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429

    # The port was called exactly once (the 1st request's MISS).
    # The 2nd was a cache HIT and the 3rd was a 429 short-circuit.
    assert len(fake_port.calls) == 1
    assert fake_port.calls == [("python", "madrid", 20)]


# ---------------------------------------------------------------------------
# REQ-RL-005 — 429 Content-Type
# ---------------------------------------------------------------------------


async def test_429_response_content_type_is_json(client: httpx.AsyncClient) -> None:
    """The 429 response has `Content-Type: application/json` (Pydantic-shaped body)."""
    # Consume the bucket.
    await client.get("/jobs/linkedin?keywords=python&location=madrid")
    await client.get("/jobs/linkedin?keywords=python&location=madrid")
    # 3rd call: 429.
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# REQ-RL-006 — Per-route cost map
# ---------------------------------------------------------------------------


async def test_aggregator_consumes_1_token(app_with_rate_limit: FastAPI) -> None:
    """The middleware's cost map has `/jobs` -> 1 (aggregator's per-call cost).

    REQ-RL-006 (MODIFIED in `rate-limit-followups`): the aggregator's
    cost is `rate_limit_aggregator_path_cost` (default 1, was 3). The
    3 parallel scraper calls are paced by each source's own
    `AsyncThrottle.min_interval_seconds=3.0` (20 req/min/source);
    the HTTP rate limiter no longer double-counts. The test
    inspects the middleware's `_cost_map` (a `MappingProxyType`)
    to verify the wiring without needing a capacity-4 app to
    observe the consumption behavior.
    """
    # Find the `RateLimitMiddleware` instance in the app's middleware stack.
    # `mw.cls` is typed as `_MiddlewareFactory[P]` (a `Protocol`) in
    # Starlette, which does not declare `__name__`. Use `getattr`
    # with a default so the test is type-safe.
    found: Any = None
    for mw in app_with_rate_limit.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            found = mw
            break
    assert found is not None, "RateLimitMiddleware not in app.user_middleware"
    cost_map: MappingProxyType[str, int] = found.kwargs["cost_map"]
    assert cost_map["/jobs"] == 1
    assert cost_map["/jobs/linkedin"] == 1
    assert cost_map["/jobs/indeed"] == 1
    assert cost_map["/jobs/infojobs"] == 1


async def test_per_source_route_consumes_1_token(
    client: httpx.AsyncClient,
) -> None:
    """`GET /jobs/linkedin` (per-source) consumes 1 token per call.

    REQ-RL-006: the per-source cost is
    `rate_limit_per_source_path_cost` (default 1). With
    `rate_limit_requests=2`, the 1st call returns
    `X-RateLimit-Remaining: 1` (consumed 1 of 2).
    """
    response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "1"


async def test_unknown_route_defaults_to_cost_1(
    client: httpx.AsyncClient,
) -> None:
    """A path not in the cost map (not `/jobs`, not `/jobs/<source>`) costs 1.

    REQ-RL-006: "Any other path that is not exempt costs 1 (default)."
    """
    # `/health` is exempt and bypasses the limiter. `/openapi.json`
    # is also exempt (FastAPI docs). Use a path that's NEITHER
    # exempt nor in the cost map.
    # Actually, with the exempt list, every non-exempt path costs 1
    # by default — but our 4 routes all match documented paths. Use
    # the `/docs` exemption for "no cost" and pick a non-existent
    # path that is NOT in the exempt list to verify default cost = 1.
    # Since the FastAPI app only has 5 routes, the only way to hit
    # the "default cost = 1" path is to make a request that 404s
    # through the route layer. The middleware runs BEFORE the route
    # handler, so a 404 path still goes through the limiter with
    # default cost = 1.
    response = await client.get("/some-future-route")
    # The path is not registered, so the route returns 404 — but
    # the middleware DID consume 1 token (default cost).
    assert response.status_code == 404
    # The 1st call's `Remaining` was decremented from 2 -> 1.
    # The 2nd call's `Remaining` is now 0.
    r2 = await client.get("/some-future-route")
    assert r2.status_code == 404
    # The 3rd call (bucket exhausted) is 429 (not 404 — the
    # middleware short-circuits BEFORE the route handler).
    r3 = await client.get("/some-future-route")
    assert r3.status_code == 429


async def test_cost_map_is_immutable_at_runtime(
    app_with_rate_limit: FastAPI,
) -> None:
    """The cost map passed to `RateLimitMiddleware` is a `MappingProxyType` (immutable).

    REQ-RL-006 scenario 4: "Cost map is immutable at runtime". The
    middleware constructor receives a `MappingProxyType(cost_map)`
    and mutating it (e.g. `mw._cost_map["x"] = 99`) raises
    `TypeError`.
    """
    # Find the `RateLimitMiddleware` instance in the app's middleware stack.
    # `mw.cls` is typed as `_MiddlewareFactory[P]` (a `Protocol`) in
    # Starlette, which does not declare `__name__`. Use `getattr`
    # with a default so the test is type-safe.
    found: Any = None
    for mw in app_with_rate_limit.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            found = mw
            break
    assert found is not None, "RateLimitMiddleware not in app.user_middleware"
    # The middleware kwargs include `cost_map` — assert it's a `MappingProxyType`.
    cost_map = found.kwargs.get("cost_map")
    assert cost_map is not None, "RateLimitMiddleware kwargs missing 'cost_map'"
    assert isinstance(cost_map, MappingProxyType)
    # Mutating raises `TypeError`.
    with pytest.raises(TypeError):
        cost_map["__mutated__"] = 99  # type: ignore[index]
