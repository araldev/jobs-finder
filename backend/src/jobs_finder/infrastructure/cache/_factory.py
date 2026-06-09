"""Factory that builds the right `CachePort` for the 3 source use cases.

Spec: REQ-PC-005 (factory selects backend per `cache_backend`).

`build_cache(settings, *, source, client=None)` is the only
sanctioned way to construct a `CachePort[JobSearchCacheKey,
list[Job]]` for the LinkedIn / Indeed / InfoJobs use cases. It
selects between:

  - `InMemoryTTLCache` (the default) when
    `settings.cache_backend == "memory"`. The per-source
    namespace is irrelevant for the in-memory backend (a `dict`
    keyed by the full `JobSearchCacheKey` is already source-
    isolated by the `source` field — REQ-C-005).
  - `RedisCache` when `settings.cache_backend == "redis"`. The
    factory pre-fixes `f"{settings.cache_redis_namespace}:
    {source}"` to the `namespace` arg so the per-source segment
    is locked in by the composition root, not by the key's own
    `.source` field — defense in depth.

When `cache_backend == "redis"` and `client is None`, the
factory constructs the client via
`redis.asyncio.from_url(settings.cache_redis_url,
db=settings.cache_redis_db)`. The composition root prefers the
`client=` injection so a single shared connection pool serves
the 3 source caches; the auto-construct path is the fallback
for callers that don't manage the pool themselves.
"""

from __future__ import annotations

import redis.asyncio as redis_async

from jobs_finder.application.ports import (
    CachePort,
    JobSearchCacheKey,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import (
    InMemoryTTLCache,
)
from jobs_finder.infrastructure.cache.redis_cache import RedisCache
from jobs_finder.infrastructure.config import Settings


def build_cache(
    settings: Settings,
    *,
    source: str,
    client: redis_async.Redis | None = None,
) -> CachePort[JobSearchCacheKey, list[Job]]:
    """Build the right `CachePort` for `source` per `settings.cache_backend`.

    Args:
        settings: The runtime configuration. The factory reads
            `cache_backend`, `cache_ttl_seconds`,
            `cache_redis_url`, `cache_redis_namespace`, and
            `cache_redis_db` from this object.
        source: The source name (`"linkedin"`, `"indeed"`, or
            `"infojobs"`). For the Redis backend, this is
            appended to the namespace so each source has its
            own key space in Redis.
        client: Optional pre-built `redis.asyncio.Redis` client.
            The composition root injects a single shared
            client so all 3 source caches share one connection
            pool. If `None` and `cache_backend="redis"`, the
            factory calls
            `redis.asyncio.from_url(settings.cache_redis_url,
            db=settings.cache_redis_db)` to construct one.

    Returns:
        A `CachePort[JobSearchCacheKey, list[Job]]` — either an
        `InMemoryTTLCache` (memory backend) or a `RedisCache`
        (redis backend).

    Raises:
        ValueError: If `settings.cache_backend` is not in
            `{"memory", "redis"}`. The closed dispatcher means
            a typo in `CACHE_BACKEND` surfaces as a startup
            error, not a runtime AttributeError.
    """
    if settings.cache_backend == "memory":
        return InMemoryTTLCache(ttl_seconds=settings.cache_ttl_seconds)

    if settings.cache_backend == "redis":
        if client is None:
            client = redis_async.from_url(  # type: ignore[no-untyped-call]
                settings.cache_redis_url,
                db=settings.cache_redis_db,
            )
        return RedisCache(
            client=client,
            namespace=f"{settings.cache_redis_namespace}:{source}",
            ttl_seconds=settings.cache_ttl_seconds,
        )

    raise ValueError(
        f"unknown cache_backend={settings.cache_backend!r}; valid: ['memory', 'redis']"
    )
