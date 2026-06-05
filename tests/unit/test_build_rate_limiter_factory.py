"""Unit tests for the `build_rate_limiter` factory.

Spec: REQ-RL-004.

The factory is the only sanctioned way to construct a `RateLimitPort`
for the `app_factory`. It selects between `NoOpRateLimiter` (when
`rate_limit_enabled=False`), `InMemoryTokenBucket` (when
`rate_limit_enabled=True` and `rate_limit_backend="memory"`), and
`RedisTokenBucket` (when `rate_limit_enabled=True` and
`rate_limit_backend="redis"`).

The 5 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import redis.asyncio as redis_async

from jobs_finder.application.ports import NoOpRateLimiter
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.rate_limit._factory import build_rate_limiter
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.infrastructure.rate_limit.redis_token_bucket import (
    RedisTokenBucket,
)

# ---------------------------------------------------------------------------
# REQ-RL-004 — `enabled=False` → NoOpRateLimiter
# ---------------------------------------------------------------------------


def test_build_rate_limiter_with_disabled_returns_noop() -> None:
    """`rate_limit_enabled=False` returns a `NoOpRateLimiter` (true no-op).

    REQ-RL-004 scenario 1: the disabled state is a `NoOpRateLimiter`
    instance (not a flag inside another class). The test asserts
    `isinstance(limiter, NoOpRateLimiter)` so the factory's
    dispatch is identity-checkable.
    """
    settings = Settings(
        rate_limit_enabled=False,
        rate_limit_requests=5,
        rate_limit_window_seconds=60.0,
    )

    limiter = build_rate_limiter(settings)

    assert isinstance(limiter, NoOpRateLimiter)
    # The NoOp's `capacity` matches the configured capacity (so the
    # `X-RateLimit-Limit` header is consistent with the config).
    assert limiter._capacity == 5.0  # noqa: SLF001


# ---------------------------------------------------------------------------
# REQ-RL-004 — `enabled=True, backend="memory"` → InMemoryTokenBucket
# ---------------------------------------------------------------------------


def test_build_rate_limiter_with_memory_backend_returns_in_memory() -> None:
    """`rate_limit_enabled=True, backend="memory"` returns an `InMemoryTokenBucket`.

    REQ-RL-004 scenario 2: the memory branch is the default. The
    factory passes `capacity` and `window_seconds` to the
    constructor (the refill rate is derived inside the bucket).
    """
    settings = Settings(
        rate_limit_enabled=True,
        rate_limit_backend="memory",
        rate_limit_requests=5,
        rate_limit_window_seconds=60.0,
    )

    limiter = build_rate_limiter(settings)

    assert isinstance(limiter, InMemoryTokenBucket)
    # The factory wires `capacity` and `refill_rate` correctly.
    assert limiter._capacity == 5.0  # noqa: SLF001
    # refill_rate = capacity / window_seconds = 5 / 60
    assert limiter._refill_rate == pytest.approx(5.0 / 60.0)  # noqa: SLF001


# ---------------------------------------------------------------------------
# REQ-RL-004 — `backend="redis"` w/ injected client
# ---------------------------------------------------------------------------


def test_build_rate_limiter_with_redis_and_injected_client() -> None:
    """`backend="redis"` + injected client returns `RedisTokenBucket` with the namespace.

    REQ-RL-004 scenario 3: when the composition root injects a
    shared `redis.asyncio.Redis` client, the factory uses it
    (single connection pool, 3 logical rate limiters). The
    namespace is `settings.rate_limit_redis_namespace`.
    """
    settings = Settings(
        rate_limit_enabled=True,
        rate_limit_backend="redis",
        rate_limit_requests=10,
        rate_limit_window_seconds=60.0,
        rate_limit_redis_namespace="rate-limiter",
    )
    mock_client: redis_async.Redis = MagicMock(spec=redis_async.Redis)

    limiter = build_rate_limiter(settings, client=mock_client)

    assert isinstance(limiter, RedisTokenBucket)
    assert limiter._client is mock_client  # noqa: SLF001
    assert limiter._namespace == "rate-limiter"  # noqa: SLF001
    assert limiter._capacity == 10.0  # noqa: SLF001
    # `swallow_errors=True` is the default (fail-open on Redis outage).
    assert limiter._swallow_errors is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# REQ-RL-004 — `backend="redis"` w/o client → `from_url` spy
# ---------------------------------------------------------------------------


def test_build_rate_limiter_with_redis_and_no_client_calls_from_url() -> None:
    """`backend="redis"` w/o client calls `redis.asyncio.from_url(url, db=db)`.

    REQ-RL-004 scenario 4: when the composition root does NOT
    inject a client, the factory calls
    `redis.asyncio.from_url(settings.rate_limit_redis_url,
    db=settings.rate_limit_redis_db)`. The test patches
    `from_url` and asserts it was called with the right args.
    """
    settings = Settings(
        rate_limit_enabled=True,
        rate_limit_backend="redis",
        rate_limit_requests=10,
        rate_limit_window_seconds=60.0,
        rate_limit_redis_url="redis://example.com:6380/2",
        rate_limit_redis_db=2,
    )

    sentinel_client: Any = MagicMock(spec=redis_async.Redis)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(redis_async, "from_url", lambda url, db=0: sentinel_client)
        limiter = build_rate_limiter(settings)

    assert isinstance(limiter, RedisTokenBucket)
    assert limiter._client is sentinel_client  # noqa: SLF001
    assert limiter._namespace == "rate-limiter"  # noqa: SLF001


# ---------------------------------------------------------------------------
# REQ-RL-004 — Unknown backend → `ValueError`
# ---------------------------------------------------------------------------


def test_build_rate_limiter_with_unknown_backend_raises_value_error() -> None:
    """An unknown `rate_limit_backend` value raises `ValueError`.

    REQ-RL-004 scenario 5: the factory is a closed dispatcher.
    A typo in config (`RATE_LIMIT_BACKEND=memmory`) surfaces as
    a 500 at startup, not as a cryptic AttributeError inside a
    route handler. The test bypasses the Pydantic `Literal`
    validation to test the factory's own dispatching logic.
    """
    settings = Settings()
    object.__setattr__(settings, "rate_limit_backend", "unknown_value")  # bypass Literal

    with pytest.raises(ValueError, match="unknown rate_limit_backend"):
        build_rate_limiter(settings)
