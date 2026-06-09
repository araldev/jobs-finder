"""Factory that builds the right `RateLimitPort` per `Settings.rate_limit_*`.

Spec: REQ-RL-004.

`build_rate_limiter(settings, *, client=None)` is the only
sanctioned way to construct a `RateLimitPort` for the
`app_factory`. It selects between:

  - `NoOpRateLimiter` (the true no-op) when
    `settings.rate_limit_enabled is False`. The factory returns
    this class so the disabled state is `isinstance`-assertable
    in tests (REQ-RL-004 scenario 1).
  - `InMemoryTokenBucket` (the default) when
    `settings.rate_limit_enabled is True and
    settings.rate_limit_backend == "memory"`. The factory
    computes `refill_rate = capacity / window_seconds` and
    forwards both to the constructor.
  - `RedisTokenBucket` when
    `settings.rate_limit_enabled is True and
    settings.rate_limit_backend == "redis"`. The factory
    uses the injected `client` (preferred — single connection
    pool) or constructs one via
    `redis.asyncio.from_url(settings.rate_limit_redis_url,
    db=settings.rate_limit_redis_db)` (fallback). The
    `swallow_errors=True` default is the documented fail-open
    contract (REQ-RL-003).

An unknown `rate_limit_backend` raises `ValueError` (the closed
dispatcher means a typo in config surfaces as a startup error,
not a runtime AttributeError).

Mirrors the `build_cache` pattern from the `persistent-cache`
change.
"""

from __future__ import annotations

import redis.asyncio as redis_async

from jobs_finder.application.ports import NoOpRateLimiter, RateLimitPort
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.infrastructure.rate_limit.redis_token_bucket import (
    RedisTokenBucket,
)


def build_rate_limiter(
    settings: Settings,
    *,
    client: redis_async.Redis | None = None,
) -> RateLimitPort:
    """Build the right `RateLimitPort` per `settings.rate_limit_*`.

    Args:
        settings: The runtime configuration. The factory reads
            `rate_limit_enabled`, `rate_limit_backend`,
            `rate_limit_requests`, `rate_limit_window_seconds`,
            `rate_limit_redis_url`, `rate_limit_redis_namespace`,
            and `rate_limit_redis_db` from this object.
        client: Optional pre-built `redis.asyncio.Redis` client.
            The composition root injects a single shared client
            so the rate-limiter and the cache share one
            connection pool. If `None` and
            `rate_limit_backend == "redis"`, the factory calls
            `redis.asyncio.from_url(...)` to construct one.

    Returns:
        A `RateLimitPort` — either a `NoOpRateLimiter`
        (disabled), an `InMemoryTokenBucket` (memory backend),
        or a `RedisTokenBucket` (redis backend).

    Raises:
        ValueError: If `settings.rate_limit_backend` is not in
            `{"memory", "redis"}`. The closed dispatcher means
            a typo in `RATE_LIMIT_BACKEND` surfaces as a startup
            error, not a runtime AttributeError.
    """
    # Disabled → no-op. Returns `NoOpRateLimiter` (a separate,
    # clearly-named class — design §15.4) so the factory
    # dispatch is `isinstance`-assertable.
    if not settings.rate_limit_enabled:
        return NoOpRateLimiter(capacity=settings.rate_limit_requests)

    refill_rate = settings.rate_limit_requests / settings.rate_limit_window_seconds

    if settings.rate_limit_backend == "memory":
        return InMemoryTokenBucket(
            capacity=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    if settings.rate_limit_backend == "redis":
        if client is None:
            client = redis_async.from_url(  # type: ignore[no-untyped-call]
                settings.rate_limit_redis_url,
                db=settings.rate_limit_redis_db,
            )
        return RedisTokenBucket(
            client=client,
            namespace=settings.rate_limit_redis_namespace,
            capacity=settings.rate_limit_requests,
            refill_rate=refill_rate,
            swallow_errors=True,
        )

    raise ValueError(
        f"unknown rate_limit_backend={settings.rate_limit_backend!r}; valid: ['memory', 'redis']"
    )
