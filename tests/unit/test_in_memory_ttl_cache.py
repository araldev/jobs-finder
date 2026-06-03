"""Unit tests for the in-memory TTL cache primitive.

Spec: REQ-C-001, REQ-C-002.

The cache is a thread-safe, in-memory `dict[K, tuple[V, float]]` with
absolute expiry. Lazy expiration on `get` (no background thread).
The class is the only concrete `CachePort[K, V]` implementation for
v1 of `cache-ttl`; future implementations (Redis, Memcached) would
satisfy the same `CachePort` Protocol.

This test file is the RED → GREEN → REFACTOR anchor for T-001. It
must be authored BEFORE the production class, run to confirm it
fails (RED), then the production class is added, then the test
passes (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

import threading
import time
from typing import NamedTuple

import pytest

from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Sample(NamedTuple):
    """A small value type so tests can assert identity preservation."""

    label: str
    n: int


def _make_value(n: int, label: str = "v") -> _Sample:
    return _Sample(label=label, n=n)


# ---------------------------------------------------------------------------
# Construction + validation (REQ-C-001)
# ---------------------------------------------------------------------------


def test_init_with_positive_ttl_succeeds() -> None:
    """`InMemoryTTLCache(60.0)` constructs without raising."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    assert cache is not None


def test_init_with_zero_ttl_succeeds() -> None:
    """`InMemoryTTLCache(0.0)` is allowed — zero TTL = "always expired".

    Setting `CACHE_TTL_SECONDS=0` in production is the documented
    kill-switch that disables caching (the use case wrapper checks
    this and short-circuits to the port on every call).
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=0.0)
    assert cache is not None


def test_init_with_negative_ttl_raises_value_error() -> None:
    """A negative TTL is rejected — there is no semantic interpretation.

    The constructor raises `ValueError` so misconfiguration surfaces
    at app startup, not on the first cache miss.
    """
    with pytest.raises(ValueError, match="ttl_seconds must be >= 0"):
        InMemoryTTLCache(ttl_seconds=-1.0)


def test_get_on_empty_cache_returns_none() -> None:
    """A `get` on an empty cache returns `None`."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    assert cache.get("any-key") is None


# ---------------------------------------------------------------------------
# Basic set / get (REQ-C-001)
# ---------------------------------------------------------------------------


def test_set_then_get_returns_stored_value() -> None:
    """A value stored via `set` is retrievable via `get` before TTL expiry."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("k", _make_value(1))
    assert cache.get("k") == _make_value(1)


def test_get_after_expiry_returns_none() -> None:
    """After TTL elapses, a `get` returns `None` and evicts the entry.

    Uses a tiny `ttl=0.01` and a `time.sleep` long enough to exceed it
    but short enough not to slow the suite. The exact wall-clock
    elision is timing-sensitive; the test asserts the behavior
    contract, not the precise millisecond.
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=0.01)
    cache.set("k", _make_value(1))
    time.sleep(0.05)
    assert cache.get("k") is None


def test_get_after_expiry_evicts_entry() -> None:
    """Lazy expiration: a `get` on an expired entry evicts it from the store.

    A subsequent `set` on the same key must NOT see the stale value
    leak (the internal store should no longer have the entry).
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=0.01)
    cache.set("k", _make_value(1))
    time.sleep(0.05)
    # First get returns None AND evicts.
    assert cache.get("k") is None
    # Overwrite with a new value; the cache must not have any stale data.
    cache.set("k", _make_value(2))
    assert cache.get("k") == _make_value(2)


def test_set_overwrites_with_last_write_wins() -> None:
    """A second `set` on the same key replaces the prior value (no merge)."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("k", _make_value(1))
    cache.set("k", _make_value(2))
    assert cache.get("k") == _make_value(2)


def test_set_resets_ttl_to_new_write_time() -> None:
    """A second `set` resets the TTL window (absolute, not sliding)."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("k", _make_value(1))
    # Re-set with a different value; the original TTL window is
    # replaced, NOT extended from the original write.
    time.sleep(0.01)
    cache.set("k", _make_value(2))
    # The new value is still retrievable 0.05s later (well within 60s).
    time.sleep(0.05)
    assert cache.get("k") == _make_value(2)


def test_set_with_zero_ttl_means_immediate_expiry() -> None:
    """A `set` on a `ttl=0` cache stores nothing usable — every `get` is None.

    This is the documented behavior of `CACHE_TTL_SECONDS=0`: the
    cache acts as if it never stores anything. (The application
    layer can short-circuit to the port on every call, but a
    `ttl=0` cache is also a safe fallback.)
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=0.0)
    cache.set("k", _make_value(1))
    # Even immediately after the set, the entry is already expired.
    assert cache.get("k") is None


# ---------------------------------------------------------------------------
# delete + clear
# ---------------------------------------------------------------------------


def test_delete_removes_existing_key() -> None:
    """`delete` on an existing key returns None on the next `get`."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("k", _make_value(1))
    cache.delete("k")
    assert cache.get("k") is None


def test_delete_on_missing_key_is_a_noop() -> None:
    """`delete` on a missing key does not raise."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    # No prior `set` on this key — must not raise.
    cache.delete("k")
    assert cache.get("k") is None


def test_clear_removes_all_keys() -> None:
    """`clear` removes every stored entry; subsequent `get`s return None."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("a", _make_value(1))
    cache.set("b", _make_value(2))
    cache.set("c", _make_value(3))
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") is None


def test_clear_on_empty_cache_is_a_noop() -> None:
    """`clear` on an empty cache does not raise."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.clear()
    assert cache.get("any") is None


# ---------------------------------------------------------------------------
# Independence of keys
# ---------------------------------------------------------------------------


def test_distinct_keys_do_not_collide() -> None:
    """Two `set`s on different keys are both retrievable independently."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("a", _make_value(1))
    cache.set("b", _make_value(2))
    assert cache.get("a") == _make_value(1)
    assert cache.get("b") == _make_value(2)


def test_get_does_not_mutate_unrelated_keys() -> None:
    """`get` on key A does not evict or touch key B."""
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=0.01)
    cache.set("a", _make_value(1))
    cache.set("b", _make_value(2))
    time.sleep(0.05)
    # Both are expired by now, but the act of getting "a" must
    # not somehow preserve "b". The contract: each entry is
    # independently expired.
    assert cache.get("a") is None
    assert cache.get("b") is None


# ---------------------------------------------------------------------------
# Type generics (REQ-C-001: typed get/set)
# ---------------------------------------------------------------------------


def test_cache_preserves_value_type_for_arbitrary_v() -> None:
    """The cache stores and returns values of any type V unchanged.

    The protocol is `CachePort[K, V]` so a `list[Job]` value must
    survive a round-trip without copying or wrapping.
    """
    cache: InMemoryTTLCache[str, list[int]] = InMemoryTTLCache(ttl_seconds=60.0)
    original: list[int] = [1, 2, 3]
    cache.set("k", original)
    result = cache.get("k")
    assert result == [1, 2, 3]
    assert result is original  # identity, not just equality


def test_cache_supports_arbitrary_hashable_k() -> None:
    """The cache uses K's own hash; any hashable K works (str, int, tuple).

    This pins the K = `JobSearchCacheKey` (a NamedTuple) contract:
    NamedTuple hashing is exact, so a tuple of `(str, str, str, int)`
    works as a cache key.
    """
    cache: InMemoryTTLCache[tuple[str, str, int], _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    key1: tuple[str, str, int] = ("linkedin", "python", 20)
    key2: tuple[str, str, int] = ("indeed", "python", 20)
    cache.set(key1, _make_value(1))
    cache.set(key2, _make_value(2))
    assert cache.get(key1) == _make_value(1)
    assert cache.get(key2) == _make_value(2)
    # A swapped-source key is a different key.
    assert cache.get(("infojobs", "python", 20)) is None


# ---------------------------------------------------------------------------
# Thread safety (REQ-C-001: thread-safe get/set/delete/clear)
# ---------------------------------------------------------------------------


def test_concurrent_sets_on_distinct_keys_all_succeed() -> None:
    """N threads setting distinct keys do not lose any writes.

    The lock is held only for the dict access; the test asserts the
    final state is consistent (all keys present, all values
    retrievable). No lost write under contention.
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    n_threads = 16
    keys_per_thread = 50

    errors: list[BaseException] = []

    def worker(thread_idx: int) -> None:
        try:
            for i in range(keys_per_thread):
                key = f"t{thread_idx}-k{i}"
                cache.set(key, _make_value(thread_idx * 1000 + i))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"workers raised: {errors!r}"
    # All N * keys_per_thread keys must be present.
    for thread_idx in range(n_threads):
        for i in range(keys_per_thread):
            key = f"t{thread_idx}-k{i}"
            assert cache.get(key) == _make_value(thread_idx * 1000 + i)


def test_concurrent_gets_during_set_do_not_raise() -> None:
    """Concurrent reads during writes do not raise and return consistent data.

    The contract is "no torn reads": a `get` either returns the prior
    value or the new value, never a malformed pair, and never
    raises under contention.
    """
    cache: InMemoryTTLCache[str, _Sample] = InMemoryTTLCache(ttl_seconds=60.0)
    cache.set("k", _make_value(0))

    errors: list[BaseException] = []

    def writer() -> None:
        try:
            for i in range(500):
                cache.set("k", _make_value(i))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(500):
                v = cache.get("k")
                # Every read returns either None (cleared) or a _Sample —
                # never a malformed value.
                assert v is None or isinstance(v, _Sample)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads: list[threading.Thread] = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"workers raised: {errors!r}"
