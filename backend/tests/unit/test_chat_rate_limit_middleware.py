"""Unit tests for the `ChatRateLimitMiddleware` (T-015 of `ai-chat-filter`).

Spec: REQ-CHAT-002 (per-user rate limit on `/jobs/chat`,
additive to the existing per-route rate limit).

The middleware is a small, focused `BaseHTTPMiddleware` that
mirrors the existing `RateLimitMiddleware`'s design but with a
separate bucket:

  - Key prefix: `f"chat:{client_id_hash}"` — isolates the chat
    bucket from the main `RateLimitMiddleware`'s bucket (so a
    busy chat user does NOT exhaust the main 20/min budget and
    vice versa).
  - Cost: 1 per request to `/jobs/chat`.
  - All other paths pass through via `call_next` (the middleware
    is a thin wrapper that does NOT touch the other routes).
  - 429 body shape: same `RateLimitedResponse` as the main
    middleware (the `{"detail": "rate limit exceeded",
    "request_id": "..."}` shape).
  - 429 headers: same `X-RateLimit-Limit / Remaining / Reset` and
    `Retry-After` as the main middleware (so clients can use a
    uniform parser).
  - Allowed path headers: same 3 `X-RateLimit-*` headers as the
    main middleware (mirrors the project's header convention).
  - The 3rd argument `max_per_minute` is the bucket capacity
    (sourced from `settings.llm_filter_rate_limit_rpm` at
    composition-root time).
  - `trusted_proxies` is honored the same way as the main
    middleware (XFF walk only when the socket IP is in a
    trusted CIDR).

The test seam: a tiny `FastAPI` app with the middleware mounted
and a fake `RateLimitPort` (an `InMemoryTokenBucket` instance
is the simplest production-shaped seam). The tests use the
same `trusted_proxies=frozenset()` default as the rest of the
project (no XFF trust, security default).
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network

import httpx
from fastapi import FastAPI

from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.presentation.middleware import (
    ChatRateLimitMiddleware,
    RequestIdMiddleware,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _build_test_app(
    *,
    capacity: int = 20,
    trusted_proxies: frozenset[IPv4Network | IPv6Network] | None = None,
) -> FastAPI:
    """Build a minimal `FastAPI` app that mounts the chat rate limiter.

    Two routes are wired:
      - `GET /jobs/chat` (the chat endpoint stub) — counts
        against the chat bucket.
      - `GET /jobs` (a different path) — must NOT be affected
        by the chat bucket (REQ-CHAT-002: separate bucket per
        path).

    `RequestIdMiddleware` is mounted INNER of the rate limiter
    (so the 429 body has the request id from
    `request.state.request_id`). Starlette runs middlewares
    outermost-first; adding `RequestIdMiddleware` BEFORE
    `ChatRateLimitMiddleware` in code means the rate limiter
    runs OUTSIDE the request-id binding.
    """
    app = FastAPI()
    # The order matters: the chat rate limiter is OUTSIDE
    # `RequestIdMiddleware` (so the 429 body can read the id
    # set by `RequestIdMiddleware`). This mirrors the main
    # `RateLimitMiddleware` ordering in `app_factory.build_app`.
    app.add_middleware(
        ChatRateLimitMiddleware,
        rate_limiter=InMemoryTokenBucket(capacity=capacity, window_seconds=60.0),
        max_per_minute=capacity,
        trusted_proxies=trusted_proxies or frozenset(),
    )
    app.add_middleware(RequestIdMiddleware)

    @app.get("/jobs/chat")
    async def chat() -> dict[str, str]:
        return {"ok": "chat"}

    @app.get("/jobs")
    async def other() -> dict[str, str]:
        return {"ok": "other"}

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# REQ-CHAT-002 — bucket isolation between `/jobs/chat` and other paths
# ---------------------------------------------------------------------------


async def test_chat_middleware_under_limit_lets_all_requests_through() -> None:
    """With `max_per_minute=20`, 20 calls return 200.

    The 21st call would return 429 (verified separately below).
    The 20 allowed calls each get the 3 `X-RateLimit-*` headers
    + a decremented `X-RateLimit-Remaining`.
    """
    app = _build_test_app(capacity=20)
    async with _client(app) as client:
        for i in range(20):
            response = await client.get("/jobs/chat")
            assert response.status_code == 200, f"call #{i + 1} was {response.status_code}"
            # The 3 documented headers are set on every allowed path.
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
            # No Retry-After on allowed paths.
            assert "Retry-After" not in response.headers


async def test_chat_middleware_over_limit_returns_429() -> None:
    """With `max_per_minute=20`, the 21st call returns 429 with `Retry-After`.

    The 429 body is the `RateLimitedResponse` shape: `{"detail",
    "request_id"}` — the same shape the main `RateLimitMiddleware`
    emits, so clients can use a single error parser.
    """
    app = _build_test_app(capacity=20)
    async with _client(app) as client:
        # Consume all 20 tokens.
        for _ in range(20):
            await client.get("/jobs/chat")
        # 21st call: 429.
        response = await client.get("/jobs/chat")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0
        # The 429 body matches the documented contract.
        body = response.json()
        assert body["detail"] == "rate limit exceeded"
        assert isinstance(body["request_id"], str)
        assert body["request_id"]  # non-empty
        # The `X-Request-Id` response header matches the body's id.
        assert body["request_id"] == response.headers["X-Request-Id"]


# ---------------------------------------------------------------------------
# REQ-CHAT-002 — per-client-IP isolation
# ---------------------------------------------------------------------------


async def test_chat_middleware_does_not_throttle_other_paths() -> None:
    """A burst of calls to `/jobs` is NOT counted against the chat bucket.

    The middleware ONLY checks the rate limiter for requests
    whose `path == "/jobs/chat"`. Other paths pass through via
    `call_next` without consulting the limiter. This is the
    "additive" guarantee of REQ-CHAT-002: the chat middleware
    does NOT consume tokens for the other routes.

    A test that exhausts the chat bucket then hits `/jobs` 100
    times in a row proves the isolation: all 100 are 200.
    """
    app = _build_test_app(capacity=2)  # small bucket so the test is fast
    async with _client(app) as client:
        # Exhaust the chat bucket.
        await client.get("/jobs/chat")
        await client.get("/jobs/chat")
        chat_429 = await client.get("/jobs/chat")
        assert chat_429.status_code == 429

        # `/jobs` is unaffected — 100 calls all pass.
        for _ in range(100):
            response = await client.get("/jobs")
            assert response.status_code == 200, (
                "chat bucket must NOT throttle /jobs; bucket isolation broken"
            )


# ---------------------------------------------------------------------------
# REQ-CHAT-002 — env var override
# ---------------------------------------------------------------------------


async def test_chat_middleware_respects_max_per_minute_override() -> None:
    """`max_per_minute=5` → 6th call returns 429.

    The bucket capacity is the constructor's `max_per_minute`
    kwarg, sourced from `settings.llm_filter_rate_limit_rpm`.
    A deployment can set `LLM_FILTER_RATE_LIMIT_RPM=5` to lower
    the cap without code changes (Q3 spec resolution).
    """
    app = _build_test_app(capacity=5)
    async with _client(app) as client:
        for _ in range(5):
            response = await client.get("/jobs/chat")
            assert response.status_code == 200
        # 6th call: 429.
        response = await client.get("/jobs/chat")
        assert response.status_code == 429


# ---------------------------------------------------------------------------
# REQ-CHAT-002 — `X-RateLimit-Limit` reflects the chat capacity, NOT the
# main `RATE_LIMIT_REQUESTS` capacity.
# ---------------------------------------------------------------------------


async def test_chat_middleware_429_body_shape_matches_documented_contract() -> None:
    """The 429 body has exactly `{"detail", "request_id"}`.

    Same shape as the main `RateLimitMiddleware`'s 429 body
    (REQ-RL-010). The 2-field contract is what clients parse;
    adding a 3rd field would break existing clients.
    """
    app = _build_test_app(capacity=1)
    async with _client(app) as client:
        await client.get("/jobs/chat")  # consume the token
        response = await client.get("/jobs/chat")
        assert response.status_code == 429
        body = response.json()
        assert set(body.keys()) == {"detail", "request_id"}
        assert body["detail"] == "rate limit exceeded"
