"""Async Redis-backed implementation of the `CachePort` Protocol.

Spec: REQ-PC-001 (JSON round-trip + EX/PX TTL precision),
REQ-PC-002 (per-source key namespace), REQ-PC-003 (graceful
degradation on Redis error), REQ-PC-006 (`clear()` logs
deleted count).

`RedisCache[K, V]` is the persistent-cache backend, selected
when `Settings.cache_backend == "redis"`. It coexists with
`InMemoryTTLCache` (the default) so a single deployment can
switch backends via the `CACHE_BACKEND` env var without
restarting the app or losing the per-source namespace
isolation.

The client is `redis.asyncio.Redis` (`redis>=5.0`); the value
serialization is `json.dumps(default=str)` (human-readable in
`redis-cli`, no security risk, `datetime` str-cast via
`default=str`); the key format is
`f"{namespace}:{source}:{sha256(repr(key)).hexdigest()[:32]}"`.

The TTL has 3 cases (matches the design):
  - `ttl >= 1.0` — `set(..., ex=int(ttl))` (Redis second-precision).
  - `0 < ttl < 1.0` — `set(..., px=int(ttl * 1000))` (PEX, ms precision).
  - `ttl == 0.0` — NO `set` is issued. The next `get` is a miss
    (the kill-switch: `CACHE_TTL_SECONDS=0` disables the cache).

Every public method wraps the Redis call in `try/except
redis.exceptions.RedisError` and logs WARNING on error so a
cache outage degrades to a cache miss, not a 502. The
`clear()` method additionally logs INFO with the deleted
key count (REQ-PC-006, OQ-1 resolved YES) so a runaway
invalidation is observable in the application logs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TypeVar

import redis.asyncio as redis_async
import redis.exceptions

from jobs_finder.application.ports import CachePort

K = TypeVar("K")
V = TypeVar("V")

_LOGGER = logging.getLogger(__name__)


class RedisCache[K, V](CachePort[K, V]):
    """Async Redis-backed cache. Satisfies the `CachePort` Protocol.

    Args:
        client: A `redis.asyncio.Redis` instance (injected for
            testability — production wires one shared client per
            app via the composition root, tests inject
            `fakeredis.aioredis.FakeRedis`).
        namespace: The key prefix (the factory passes
            `f"{settings.cache_redis_namespace}:{source}"` so the
            per-source segment is locked in by the composition
            root, not by the key's own `.source` field — defense
            in depth).
        ttl_seconds: The cache TTL. `0.0` is the kill-switch
            (every `set` is a no-op, every `get` is a miss).
            `0 < ttl < 1.0` uses PEX (ms precision); `ttl >= 1.0`
            uses EX (second precision).
    """

    def __init__(
        self,
        *,
        client: redis_async.Redis,
        namespace: str,
        ttl_seconds: float,
    ) -> None:
        self._client = client
        self._namespace = namespace
        self._ttl_seconds = ttl_seconds

    def _key(self, key: K) -> str:
        """Build the Redis key for `key`.

        The key is `f"{namespace}:{sha256(repr(key)).hexdigest()[:32]}"`.
        `sha256` over `repr` is collision-safe; `[:32]` is 128
        bits (plenty for cache key cardinality; full 64 hex is
        wasteful in Redis).

        The 2-segment form (`{namespace}:{hash}`) is the
        production shape because the factory pre-fixes
        `f"{settings.cache_redis_namespace}:{source}"` to the
        `namespace` arg — so the on-disk key has 3 segments
        (`{settings_ns}:{source}:{hash}`) and `clear()`'s
        `MATCH {namespace}:*` correctly scopes to that source.
        """
        digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:32]
        return f"{self._namespace}:{digest}"

    async def get(self, key: K) -> V | None:
        """Return the stored value, or `None` on miss / Redis error."""
        try:
            raw = await self._client.get(self._key(key))
        except redis.exceptions.RedisError as exc:
            _LOGGER.warning(
                "RedisCache get failed: op=get key=%r error=%r",
                key,
                exc,
            )
            return None
        if raw is None:
            return None
        # `redis.asyncio.Redis` decodes responses to `bytes`
        # when `decode_responses=False` (the default in this
        # project). Decode before JSON-parsing.
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        return json.loads(text)  # type: ignore[no-any-return]

    async def set(self, key: K, value: V) -> None:
        """Store the value with the configured TTL. No-op when `ttl=0.0`.

        The kill-switch `ttl=0.0` is honored by NOT issuing any
        Redis SET command — a disabled cache is also a "no
        traffic to Redis" cache.
        """
        if self._ttl_seconds <= 0.0:
            return
        payload = json.dumps(value, default=str)
        redis_key = self._key(key)
        try:
            if self._ttl_seconds >= 1.0:
                await self._client.set(redis_key, payload, ex=int(self._ttl_seconds))
            else:
                # 0 < ttl < 1.0 — use PEX for millisecond precision.
                # `int(ttl * 1000)` rounds down; a 0.0001s TTL would
                # round to 0 ms which Redis rejects. Guard against
                # that edge case so a tiny TTL still behaves
                # sensibly (use 1 ms).
                px_ms = max(1, int(self._ttl_seconds * 1000))
                await self._client.set(redis_key, payload, px=px_ms)
        except redis.exceptions.RedisError as exc:
            _LOGGER.warning(
                "RedisCache set failed: op=set key=%r error=%r",
                key,
                exc,
            )
            return None  # explicit no-op sentinel

    async def delete(self, key: K) -> None:
        """Remove the key (no-op if absent). Errors are swallowed."""
        try:
            await self._client.delete(self._key(key))
        except redis.exceptions.RedisError as exc:
            _LOGGER.warning(
                "RedisCache delete failed: op=delete key=%r error=%r",
                key,
                exc,
            )
            return None  # explicit no-op sentinel

    async def clear(self) -> None:
        """Remove all keys under the namespace; log INFO with the deleted count.

        OQ-1 resolved YES: the count is emitted EVEN when 0 so a
        cleared namespace is observable in logs (consistent with
        "every `clear()` is a real event"). The log is INFO, not
        WARNING, because `clear()` is a routine operation (called
        on test setup); operators can grep for unusually large
        counts to detect runaway invalidations.

        Never uses `FLUSHDB` — that would nuke other apps sharing
        the Redis instance. The implementation is `SCAN` with
        `MATCH {namespace}:*` + `DEL` each match.
        """
        deleted = 0
        try:
            async for redis_key in self._client.scan_iter(match=f"{self._namespace}:*", count=100):
                await self._client.delete(redis_key)
                deleted += 1
        except redis.exceptions.RedisError as exc:
            _LOGGER.warning(
                "RedisCache clear failed: op=clear namespace=%r error=%r",
                self._namespace,
                exc,
            )
            return None  # explicit no-op sentinel
        _LOGGER.info(
            "RedisCache cleared namespace=%r deleted=%d",
            self._namespace,
            deleted,
        )
        return None
