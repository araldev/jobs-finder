"""Unit tests for the `RedisCache` async implementation.

Spec: REQ-PC-001 (JSON round-trip + EX/PX TTL precision),
REQ-PC-002 (per-source key namespace), REQ-PC-003 (graceful
degradation on Redis error), REQ-PC-006 (`clear()` logs deleted
count).

The test seam is `fakeredis.aioredis.FakeRedis`, an in-process
fake of `redis.asyncio.Redis` with the same `get`/`set`/
`delete`/`scan` API. Real Redis is NOT contacted — the
integration test against a real Redis lives in
`tests/integration/test_redis_cache_headers.py` and is
`@pytest.mark.skipif(not _redis_reachable())`.

The 12 scenarios are Given/When/Then, observable behavior,
deterministic (no real network, no wall-clock dependence).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import fakeredis.aioredis as fakeredis_aio
import pytest
import redis.exceptions

from jobs_finder.application.ports import JobSearchCacheKey
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.redis_cache import RedisCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job(idx: int) -> Job:
    """Build a small `Job` instance for round-trip assertions."""
    return Job(
        id=f"j{idx}",
        title=f"Title {idx}",
        company="Co",
        location="Madrid",
        url=f"https://example.com/j{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


def _make_client() -> fakeredis_aio.FakeRedis:
    """Return a fresh `FakeRedis` client (no shared state across tests)."""
    return fakeredis_aio.FakeRedis()


def _key(idx: int = 1) -> JobSearchCacheKey:
    """A deterministic but UNIQUE `JobSearchCacheKey` for tests.

    Each `idx` produces a different `keywords` field so `set` on
    `_key(1)`, `_key(2)`, `_key(3)` populates 3 distinct entries
    (the cache uses `JobSearchCacheKey` equality, not identity).
    """
    return JobSearchCacheKey(
        source="linkedin",
        keywords=f"kw-{idx}",
        location="madrid",
        limit=20,
    )


class _RecordingFakeRedis:
    """A `FakeRedis` wrapper that records every key passed to `set`.

    Used to assert the key format (per-source namespace prefix).
    Wraps the real `FakeRedis` and forwards everything except `set`
    (which is intercepted to record the key name).
    """

    def __init__(self, inner: fakeredis_aio.FakeRedis) -> None:
        self._inner = inner
        self.set_keys: list[str] = []
        self.set_ex: list[int | None] = []
        self.set_px: list[int | None] = []

    async def set(  # noqa: PLR0913
        self,
        name: str | bytes,
        value: Any = None,  # noqa: ANN401
        ex: int | None = None,
        px: int | None = None,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        # Record the call. The production code passes a `str` (JSON
        # serialized payload + the `f"{ns}:{source}:{hash}"` key);
        # tests assert the recorded key starts with the namespace.
        self.set_keys.append(name if isinstance(name, str) else name.decode())
        self.set_ex.append(ex)
        self.set_px.append(px)
        return await self._inner.set(name, value, ex=ex, px=px, **kwargs)

    async def get(self, name: str | bytes) -> Any:  # noqa: ANN401
        return await self._inner.get(name)

    async def delete(self, *names: str | bytes) -> Any:  # noqa: ANN401
        return await self._inner.delete(*names)

    async def scan_iter(  # noqa: ANN401
        self,
        match: str | bytes | None = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        return self._inner.scan_iter(match=match, count=count, **kwargs)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        # Forward any other method (ping, aclose, etc.) to the inner client.
        return getattr(self._inner, name)


class _BrokenRedis:
    """A `redis.asyncio.Redis`-shaped fake that always raises `ConnectionError`.

    Used to assert graceful degradation: every public `RedisCache`
    method must catch `redis.exceptions.RedisError` and return the
    no-op sentinel (None for `get`, no exception for the rest).
    """

    async def get(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise redis.exceptions.ConnectionError("simulated: connection refused")

    async def set(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise redis.exceptions.ConnectionError("simulated: connection refused")

    async def delete(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise redis.exceptions.ConnectionError("simulated: connection refused")

    async def scan_iter(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise redis.exceptions.ConnectionError("simulated: connection refused")
        yield  # pragma: no cover -- makes this a generator function

    async def ping(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise redis.exceptions.ConnectionError("simulated: connection refused")


# ---------------------------------------------------------------------------
# REQ-PC-001 — JSON round-trip + EX/PX TTL precision (4 scenarios)
# ---------------------------------------------------------------------------


async def test_set_then_get_returns_stored_value() -> None:
    """A value stored via `set` is retrievable via `get` after a JSON round-trip.

    The value is a `list[dict[str, str]]` (NOT a `list[Job]`) —
    a JSON round-trip cannot preserve frozen-dataclass types
    (a `Job` round-trips to a `dict`), so the test asserts deep
    equality on plain dicts which IS preserved by `json.dumps`
    + `json.loads`. The cache key is a `JobSearchCacheKey`
    (hashable) so the cache contract is exercised.
    """
    cache: RedisCache[JobSearchCacheKey, list[dict[str, str]]] = RedisCache(
        client=_make_client(),
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )
    value: list[dict[str, str]] = [
        {"id": "j1", "title": "Title 1"},
        {"id": "j2", "title": "Title 2"},
        {"id": "j3", "title": "Title 3"},
    ]

    await cache.set(_key(1), value)
    result = await cache.get(_key(1))

    assert result == value
    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0]["id"] == "j1"
    assert result[2]["title"] == "Title 3"


async def test_set_with_one_second_ttl_uses_ex_60() -> None:
    """TTL >= 1.0 uses `ex=ttl_seconds` (not `px`); the captured call is `EX 60`.

    `set(name, value, ex=60)` is the canonical Redis call. PEX
    (millisecond precision) is only used for sub-second TTL — the
    Redis native second-precision is preferred when it suffices.
    """
    client = _RecordingFakeRedis(_make_client())
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client,  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )

    await cache.set(_key(1), [_job(1)])

    assert client.set_ex == [60]
    assert client.set_px == [None]


async def test_set_with_subsecond_ttl_uses_px_500() -> None:
    """0 < TTL < 1.0 uses `px=int(ttl*1000)` (millisecond precision).

    `set(name, value, px=500)` is the canonical Redis call for a
    half-second TTL. PEX is required because EX rounds to whole
    seconds and a 0.5s TTL would round to 0 (no-op).
    """
    client = _RecordingFakeRedis(_make_client())
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client,  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=0.5,
    )

    await cache.set(_key(1), [_job(1)])

    assert client.set_px == [500]
    assert client.set_ex == [None]


async def test_set_with_zero_ttl_is_a_noop() -> None:
    """TTL=0.0 issues NO SET command; a subsequent `get` returns `None`.

    The kill-switch: `CACHE_TTL_SECONDS=0` must disable the cache.
    In the in-memory backend, the entry is stored then immediately
    expired on read. In the Redis backend, the SET is skipped
    entirely (no Redis traffic for a disabled cache) and the next
    `get` is a miss.
    """
    client = _RecordingFakeRedis(_make_client())
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client,  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=0.0,
    )

    await cache.set(_key(1), [_job(1)])
    result = await cache.get(_key(1))

    # No SET command was issued at all.
    assert client.set_keys == []
    assert client.set_ex == []
    assert client.set_px == []
    # The get is a miss because nothing was ever written.
    assert result is None


# ---------------------------------------------------------------------------
# REQ-PC-002 — Per-source key namespace (3 scenarios)
# ---------------------------------------------------------------------------


async def test_set_key_starts_with_namespace_and_source() -> None:
    """The captured Redis key starts with `{namespace}:{source}:` (defense in depth).

    The key format is `f\"{namespace}:{source}:{sha256(repr(key))[:32]}\"`.
    The namespace is `f\"{settings.cache_redis_namespace}:{source}\"`,
    so the key starts with `{settings.cache_redis_namespace}:{source}:`
    and the rest is a 32-char hex digest of the `JobSearchCacheKey`
    repr. The test asserts the prefix only — the digest is opaque.
    """
    client = _RecordingFakeRedis(_make_client())
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client,  # type: ignore[arg-type]
        namespace="jobs-finder:linkedin",
        ttl_seconds=60.0,
    )

    await cache.set(_key(1), [_job(1)])

    assert len(client.set_keys) == 1
    assert client.set_keys[0].startswith("jobs-finder:linkedin:")
    # The remaining part is a 32-char hex digest.
    suffix = client.set_keys[0].removeprefix("jobs-finder:linkedin:")
    assert len(suffix) == 32
    int(suffix, 16)  # raises if not hex


async def test_two_caches_with_different_namespaces_have_different_keys() -> None:
    """Two `RedisCache` instances with different namespaces never share a key.

    Per-source independence: a `linkedin` key in one namespace and
    the same `JobSearchCacheKey` in another namespace must produce
    two distinct Redis keys (no cross-source collision).
    """
    client_a = _RecordingFakeRedis(_make_client())
    client_b = _RecordingFakeRedis(_make_client())
    cache_a: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client_a,  # type: ignore[arg-type]
        namespace="jobs-finder:linkedin",
        ttl_seconds=60.0,
    )
    cache_b: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client_b,  # type: ignore[arg-type]
        namespace="jobs-finder:indeed",
        ttl_seconds=60.0,
    )

    same_key = _key(1)
    await cache_a.set(same_key, [_job(1)])
    await cache_b.set(same_key, [_job(1)])

    # The keys differ (no collision) because the namespace segment differs.
    assert client_a.set_keys[0] != client_b.set_keys[0]
    assert client_a.set_keys[0].startswith("jobs-finder:linkedin:")
    assert client_b.set_keys[0].startswith("jobs-finder:indeed:")


async def test_clear_only_deletes_keys_under_own_namespace() -> None:
    """`clear()` is namespace-scoped — sibling namespaces survive.

    `clear()` MUST NOT use `FLUSHDB` (which would nuke sibling
    apps sharing the Redis instance). Instead, it `SCAN`s with
    `MATCH {namespace}:*` and `DEL`s each match. Sibling keys
    with a different namespace are untouched.
    """
    # Two independent clients (one per cache). They share the same
    # underlying FakeServer via `server=` so keys are visible to both
    # SCANs — the namespace prefix is what isolates them.
    server = fakeredis_aio.FakeServer()  # type: ignore[attr-defined]
    client_a = fakeredis_aio.FakeRedis(server=server)
    client_b = fakeredis_aio.FakeRedis(server=server)

    cache_a: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client_a,
        namespace="jobs-finder:linkedin",
        ttl_seconds=60.0,
    )
    cache_b: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=client_b,
        namespace="jobs-finder:indeed",
        ttl_seconds=60.0,
    )

    # 3 keys under `linkedin` namespace + 1 key under `indeed` namespace.
    await cache_a.set(_key(1), [_job(1)])
    await cache_a.set(_key(2), [_job(2)])
    await cache_a.set(_key(3), [_job(3)])
    await cache_b.set(_key(4), [_job(4)])

    # Sanity: the sibling key IS present before clear.
    sibling_key = "jobs-finder:indeed:dummy"
    await client_b.set(sibling_key, "x")

    # Clear cache_a — only the 3 linkedin keys should be removed.
    await cache_a.clear()

    # The 3 linkedin keys are gone.
    assert await cache_a.get(_key(1)) is None
    assert await cache_a.get(_key(2)) is None
    assert await cache_a.get(_key(3)) is None
    # The sibling indeed key is untouched.
    assert await client_b.get(sibling_key) == b"x"


# ---------------------------------------------------------------------------
# REQ-PC-003 — Graceful degradation on Redis error (3 scenarios)
# ---------------------------------------------------------------------------


async def test_get_on_redis_connection_error_returns_none() -> None:
    """A `get` on a `ConnectionError` logs WARNING and returns `None`.

    The cache outage degrades to a cache miss (no 502 propagated
    to the caller). The WARNING is observable in the application
    logs so operators can investigate.
    """
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=_BrokenRedis(),  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )

    result = await cache.get(_key(1))
    assert result is None


async def test_set_on_redis_connection_error_does_not_raise() -> None:
    """A `set` on a `ConnectionError` is swallowed; no exception propagates."""
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=_BrokenRedis(),  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )

    # No exception propagates — graceful degradation.
    await cache.set(_key(1), [_job(1)])


async def test_delete_on_redis_connection_error_does_not_raise() -> None:
    """A `delete` on a `ConnectionError` is swallowed; no exception propagates."""
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=_BrokenRedis(),  # type: ignore[arg-type]
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )

    # No exception propagates — graceful degradation.
    await cache.delete(_key(1))


# ---------------------------------------------------------------------------
# REQ-PC-006 — `clear()` logs deleted count (2 scenarios)
# ---------------------------------------------------------------------------


async def test_clear_with_three_keys_logs_deleted_three(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `clear()` that removes 3 keys logs INFO with `deleted=3`."""
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=_make_client(),
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )
    await cache.set(_key(1), [_job(1)])
    await cache.set(_key(2), [_job(2)])
    await cache.set(_key(3), [_job(3)])

    with caplog.at_level(logging.INFO, logger="jobs_finder.infrastructure.cache.redis_cache"):
        await cache.clear()

    assert any("deleted=3" in rec.message for rec in caplog.records)
    assert any(rec.levelno == logging.INFO for rec in caplog.records)


async def test_clear_with_zero_keys_logs_deleted_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `clear()` on an empty cache logs INFO with `deleted=0`.

    OQ-1 resolved YES: the count is emitted EVEN when 0 so a
    cleared namespace is observable in logs (consistent with
    "every `clear()` is a real event").
    """
    cache: RedisCache[JobSearchCacheKey, list[Job]] = RedisCache(
        client=_make_client(),
        namespace="test:linkedin",
        ttl_seconds=60.0,
    )

    with caplog.at_level(logging.INFO, logger="jobs_finder.infrastructure.cache.redis_cache"):
        await cache.clear()

    assert any("deleted=0" in rec.message for rec in caplog.records)
    assert any(rec.levelno == logging.INFO for rec in caplog.records)
