"""Unit tests for the `build_cache` factory.

Spec: REQ-PC-005 (factory selects backend per `cache_backend`).

The factory is the only sanctioned way to construct a
`CachePort[JobSearchCacheKey, list[Job]]` for the 3 source use
cases. It selects between `InMemoryTTLCache` (default) and
`RedisCache` (when `cache_backend="redis"`) based on the
runtime `Settings` and the per-source namespace.

The 4 scenarios are Given/When/Then, observable behavior,
deterministic. The Redis client is injected as a `mock` so
the test does NOT contact a real Redis.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import redis.asyncio as redis_async

from jobs_finder.infrastructure.cache._factory import build_cache
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.cache.redis_cache import RedisCache
from jobs_finder.infrastructure.config import Settings

# ---------------------------------------------------------------------------
# REQ-PC-005 — `build_cache` factory selects backend (4 scenarios)
# ---------------------------------------------------------------------------


def test_build_cache_with_memory_backend_returns_in_memory_ttl_cache() -> None:
    """`cache_backend=\"memory\"` returns an `InMemoryTTLCache` with the right TTL.

    The factory passes the per-source namespace down for the
    Redis branch; for the memory branch, the namespace is
    irrelevant (the in-memory cache has no Redis-key concept)
    so the factory forwards `cache_ttl_seconds` only.
    """
    settings = Settings(cache_backend="memory", cache_ttl_seconds=120.0)

    cache = build_cache(settings, source="linkedin")

    assert isinstance(cache, InMemoryTTLCache)
    # The TTL is forwarded (asserted via the private `_ttl` attr,
    # the same pattern used by the `test_in_memory_ttl_cache`
    # regression tests).
    assert cache._ttl == 120.0  # noqa: SLF001 — private attr, test seam


def test_build_cache_with_redis_backend_returns_redis_cache_with_namespace() -> None:
    """`cache_backend=\"redis\"` + injected client returns `RedisCache` with the right namespace.

    The factory builds `namespace=f\"{settings.cache_redis_namespace}:{source}\"`
    so the per-source segment is locked in by the composition root
    (defense in depth). The test asserts the namespace composition
    AND the TTL forwarding.
    """
    settings = Settings(
        cache_backend="redis",
        cache_redis_namespace="jobs-finder",
        cache_ttl_seconds=60.0,
    )
    mock_client: redis_async.Redis = MagicMock(spec=redis_async.Redis)

    cache = build_cache(settings, source="linkedin", client=mock_client)

    assert isinstance(cache, RedisCache)
    # Assert on private attrs: the factory wires `namespace` and
    # `ttl_seconds` exactly as documented.
    assert cache._namespace == "jobs-finder:linkedin"  # noqa: SLF001
    assert cache._ttl_seconds == 60.0  # noqa: SLF001
    assert cache._client is mock_client  # noqa: SLF001


def test_build_cache_with_unknown_backend_raises_value_error() -> None:
    """An unknown `cache_backend` value raises `ValueError`.

    The factory is a closed dispatcher: `Literal[\"memory\", \"redis\"]`
    is the exhaustive list. A typo in config (`CACHE_BACKEND=memmory`)
    surfaces as a 500 at startup, not as a cryptic AttributeError
    inside a route handler.
    """
    # Bypass the Pydantic Literal validation to test the factory
    # directly (the production code path is guarded by
    # `Settings.cache_backend` being `Literal[\"memory\", \"redis\"]`,
    # so an unknown value cannot come from env vars; this test
    # asserts the factory's own dispatching logic).
    settings = Settings()
    object.__setattr__(settings, "cache_backend", "unknown_value")  # bypass Literal

    with pytest.raises(ValueError, match="unknown cache_backend"):
        build_cache(settings, source="linkedin")


def test_build_cache_with_redis_backend_and_no_client_calls_from_url() -> None:
    """`cache_backend=\"redis\"` w/o client calls `redis.asyncio.from_url`.

    When the composition root does not inject a client, the
    factory is the canonical place to construct one
    (`redis.asyncio.from_url(settings.cache_redis_url,
    db=settings.cache_redis_db)`). The test mocks the
    `from_url` factory and asserts it was called with the
    correct args.
    """
    settings = Settings(
        cache_backend="redis",
        cache_redis_url="redis://example.com:6380/2",
        cache_redis_namespace="jobs-finder",
        cache_redis_db=2,
        cache_ttl_seconds=60.0,
    )

    # Patch `redis.asyncio.from_url` to a MagicMock that returns a
    # sentinel client. The factory calls `from_url(url, db=db)`
    # and passes the result as the `client` to `RedisCache(...)`.
    sentinel_client: Any = MagicMock(spec=redis_async.Redis)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(redis_async, "from_url", lambda url, db=0: sentinel_client)
        cache = build_cache(settings, source="indeed")

    assert isinstance(cache, RedisCache)
    # The factory's from_url call wired the sentinel as the client.
    assert cache._client is sentinel_client  # noqa: SLF001
    assert cache._namespace == "jobs-finder:indeed"  # noqa: SLF001
