"""Integration tests for the Redis rate-limiter's fail-open behavior.

Spec: REQ-RL-003 + REQ-RL-009 (Redis-degrade scenario).

When the rate-limiter Redis client is unreachable, the middleware
MUST fail open (return 200, log WARNING) — never 5xx. This is the
asymmetric-to-cache contract: the cache fail-fasts on startup, the
rate-limiter degrades to "no throttling" on outage (the rate
limiter is optional, the cache is not).

The unreachable test points the rate-limiter Redis at a port that
refuses connections (port 1, reserved). The lifespan starts
successfully (NO ping), and a subsequent request returns 200 +
WARNING logged.

The lifespan-close test (T-005 follow-up) asserts REQ-RL-009
scenario 3: the rate-limiter Redis client's `aclose()` IS
called during the lifespan exit (the spec's documented
contract).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from jobs_finder.infrastructure.rate_limit.redis_token_bucket import (
    RedisTokenBucket,
)

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


# ---------------------------------------------------------------------------
# REQ-RL-009 #3 — Redis client `aclose()` called in lifespan (T-005 follow-up)
# ---------------------------------------------------------------------------


class _AcloseSpy:
    """A drop-in replacement for the rate-limiter Redis client that spies on `aclose()`.

    The spy delegates `eval(...)` to the real client (or short-
    circuits on a refused connection, preserving the
    fail-open WARNING behavior) and records every `aclose()`
    call so the test can assert the lifespan closes the client
    exactly once on shutdown.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.aclose_calls: int = 0

    async def aclose(self) -> None:
        """Record the call and delegate to the inner client (if any)."""
        self.aclose_calls += 1
        inner_close = getattr(self._inner, "aclose", None)
        if inner_close is not None:
            await inner_close()

    async def eval(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate `eval` to the inner client (preserves fail-open semantics)."""
        return await self._inner.eval(*args, **kwargs)


async def test_redis_client_closed_in_lifespan(
    app_with_redis_rate_limit_unreachable: FastAPI,
) -> None:
    """REQ-RL-009 #3: the rate-limiter Redis client's `aclose()` is called in the lifespan.

    The spec scenario: "Redis client closed in lifespan: ...
    `client.aclose()` was called exactly once on the
    rate-limiter client during lifespan exit (assert via spy)."

    The test reaches the rate-limiter middleware via
    `app.user_middleware` introspection (mirrors the pattern
    in `test_aggregator_consumes_3_tokens` /
    `test_disabled_middleware_absent_from_stack`), replaces
    the `RedisTokenBucket._client` with a spy that records
    `aclose()` calls, then runs the lifespan via
    `LifespanManager`. On exit, the spy MUST have been
    called exactly once — proving the lifespan closed the
    rate-limiter Redis client (not just the cache client).
    """
    # Find the `RateLimitMiddleware` and reach the underlying
    # `RedisTokenBucket` (the spy wraps its `_client`).
    found: Any = None
    for mw in app_with_redis_rate_limit_unreachable.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            found = mw
            break
    assert found is not None, "RateLimitMiddleware not in app.user_middleware"
    limiter: RedisTokenBucket = found.kwargs["limiter"]
    assert isinstance(limiter, RedisTokenBucket), (
        f"expected RedisTokenBucket, got {type(limiter).__name__}"
    )

    # Wrap the limiter's Redis client in a spy that records `aclose()`.
    spy = _AcloseSpy(limiter._client)
    limiter._client = spy  # type: ignore[assignment]

    # Run the lifespan via `LifespanManager`. On exit, the
    # production code's `finally` block MUST call
    # `rl_redis_client.aclose()` once (per the design §10 and
    # the spec REQ-RL-009 scenario 3).
    async with LifespanManager(app_with_redis_rate_limit_unreachable):
        pass  # no requests needed — the assertion is on the shutdown path

    # The spy was called exactly once during the lifespan exit.
    assert spy.aclose_calls == 1, (
        f"expected rate-limiter Redis client.aclose() to be called "
        f"exactly once during lifespan exit, got {spy.aclose_calls}"
    )
