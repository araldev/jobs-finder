"""Thread-safe in-memory cache with absolute TTL semantics.

Spec: REQ-C-001, REQ-C-002.

The cache is a thin wrapper around a `dict[K, tuple[V, float]]`
where the float is the absolute expiry timestamp (`time.monotonic()`-based
to avoid wall-clock adjustments). The TTL is ABSOLUTE: a `set`
always resets the expiry to `now() + ttl`, not to the prior
write's expiry. Lazy expiration: `get` checks the expiry timestamp
and returns `None` on miss; no background thread sweeps expired
entries. For an in-memory dict with modest size, the sweep is
unnecessary — expired entries are reclaimed on the next `get` or
`set` that touches them, and the lazy reclamation bounds memory
without the operational cost of a sweeper thread.

Thread safety: a `threading.Lock` guards the dict mutation path.
`get` also acquires the lock for the read-then-evict check, so
two concurrent `get`s cannot both return the expired value (only
the first one that observes the expiry evicts; the second sees
the missing key and returns `None`). The lock is held only across
the dict access (a few microseconds); the long-running port call
(outside the cache) is NOT held under the lock. This avoids
head-of-line blocking across the 3 source caches.
"""

from __future__ import annotations

import threading
import time
from typing import TypeVar

K = TypeVar("K")
V = TypeVar("V")


class InMemoryTTLCache[K, V]:
    """Thread-safe in-memory cache with absolute TTL.

    The TTL is absolute, not sliding: a `set` always resets the
    expiry to `now() + ttl_seconds`. Lazy expiration: `get` checks
    the expiry timestamp and returns `None` on miss; no background
    thread sweeps expired entries.
    """

    def __init__(self, ttl_seconds: float) -> None:
        """Construct the cache with the given TTL in seconds.

        `ttl_seconds` MUST be `>= 0`. `0` is the documented kill-switch
        that disables caching (every `get` returns `None` because
        the entry is already expired by the time `get` runs).
        Negative TTL is rejected at construction time so
        misconfiguration surfaces at app startup, not on the first
        cache miss.
        """
        if ttl_seconds < 0:
            raise ValueError(f"ttl_seconds must be >= 0, got {ttl_seconds}")
        self._ttl: float = ttl_seconds
        self._store: dict[K, tuple[V, float]] = {}
        self._lock = threading.Lock()

    async def get(self, key: K) -> V | None:
        """Return the stored value if not expired, else `None`.

        Lazy expiration: an expired entry is evicted on the read
        path. Concurrent reads are safe; the lock is held only
        across the dict access.

        The method is `async def` to satisfy the upgraded
        `CachePort` Protocol (REQ-C-001 MODIFIED per Path A,
        2026-06-05). The body remains synchronous — the underlying
        ops (`dict` access under a `threading.Lock`) are sync — so
        the `async def` is a no-op wrapper. This lets the same
        Protocol be implemented by both the sync in-memory cache
        and the async Redis cache (which uses `redis.asyncio`).
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                # Lazy expiration: evict on the read path.
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: K, value: V) -> None:
        """Store the value with the configured TTL. Overwrites prior.

        The TTL is absolute: the expiry is `now() + ttl_seconds`,
        regardless of any prior write's expiry (last-write-wins).
        """
        with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)

    async def delete(self, key: K) -> None:
        """Remove the key (no-op if absent)."""
        with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Remove all keys. Used by tests; not exposed in production."""
        with self._lock:
            self._store.clear()
