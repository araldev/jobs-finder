"""Real-Redis integration tests for `RedisTokenBucket` (skipif).

Spec: REQ-RL-013 (S-3 from the prior `rate-limiting` cycle's
verify report).

The current `tests/unit/test_redis_token_bucket.py` uses a
Python fake (`_FakeRedisWithLua`) that implements the same
algorithm as the production Lua script. The fake does NOT
exercise the real `EVAL` round-trip — a Lua syntax error, a
Redis 7+ deprecation, or a KEYS/ARGV ordering bug would not
surface in CI.

This file is the real-Redis complement. It probes
`localhost:6379` (overridable via `RATE_LIMIT_REDIS_URL`) at
module import; if Redis is unreachable, all 7 tests SKIP
cleanly. Run with a local Redis for full coverage:

    docker run -d -p 6379:6379 redis:7-alpine
    RATE_LIMIT_REDIS_URL=redis://localhost:6379/0 \\
        uv run pytest tests/integration/test_rate_limit_redis_real.py

Each test:
  - Creates its own `redis.asyncio.Redis` client (hermetic, no
    shared lifespan) in a `try/finally` block.
  - Uses a unique namespace `test-rl-real-{uuid.uuid4().hex[:8]}`
    for test isolation — no cross-test key collisions.
  - Cleans up the namespace in the `finally` block (best-effort
    `FLUSHDB` would be too aggressive; per-key `DELETE` is
    sufficient).

The 7 scenarios are Given/When/Then, observable behavior,
deterministic (modulo the `asyncio.sleep(1.2)` refill test
which uses a real sleep).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import re
import uuid
from typing import Any

import pytest
import redis.asyncio as redis_async

from jobs_finder.infrastructure.rate_limit._hashing import hash_client_id
from jobs_finder.infrastructure.rate_limit.redis_token_bucket import (
    RedisTokenBucket,
)

# ---------------------------------------------------------------------------
# Skipif probe
# ---------------------------------------------------------------------------

# `RATE_LIMIT_REDIS_URL` is the env-var override (matches the
# `_factory.py` convention). The default `localhost:6379/0` mirrors
# the prior `test_redis_cache_headers.py:28-51,105` pattern.
_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")


def _redis_reachable() -> bool:
    """Return `True` if `_REDIS_URL` accepts a `ping`.

    Synchronous probe at module import. The connection is closed
    immediately to avoid leaking sockets in the test process.
    """

    async def _probe() -> bool:
        client = redis_async.from_url(  # type: ignore[no-untyped-call]
            _REDIS_URL, decode_responses=False
        )
        try:
            return bool(await client.ping())
        except Exception:  # noqa: BLE001
            return False
        finally:
            await client.aclose()

    try:
        return asyncio.run(_probe())
    except Exception:  # noqa: BLE001
        return False


# Module-level skipif: all 7 tests are skipped atomically when
# Redis is not reachable. This mirrors the
# `test_redis_cache_headers.py:105` precedent.
pytestmark = pytest.mark.skipif(
    not _redis_reachable(),
    reason=f"Redis not reachable on {_REDIS_URL}",
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _unique_namespace(prefix: str = "test-rl-real") -> str:
    """Return a unique namespace string for per-test isolation.

    Each test gets its own namespace so concurrent test runs (or
    stale keys from a previous test) don't collide. The UUID
    suffix is 8 hex chars — enough to avoid collisions for the
    ~20 tests that will use this helper over the project's
    lifetime.
    """
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 1 — Basic consumption
# ---------------------------------------------------------------------------


async def test_basic_consumption_3_of_5_then_4th_denied() -> None:
    """`capacity=5, refill=0`: 3 takes allowed (remaining=4,3,2), 4th denied.

    REQ-RL-013 scenario 1: the bucket is filled to capacity on
    first access; each consume decrements by `cost`. With
    `refill=0`, the 4th consume in a 5-capacity bucket returns
    `allowed=False`.
    """
    namespace = _unique_namespace("test-rl-real-basic")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=5,
            refill_rate=0.0,
        )
        d1 = await bucket.try_acquire("key1", cost=1.0)
        d2 = await bucket.try_acquire("key1", cost=1.0)
        d3 = await bucket.try_acquire("key1", cost=1.0)
        d4 = await bucket.try_acquire("key1", cost=1.0)
        assert d1.allowed is True
        assert d1.remaining == 4
        assert d2.allowed is True
        assert d2.remaining == 3
        assert d3.allowed is True
        assert d3.remaining == 2
        assert d4.allowed is False
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace}:key1")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 2 — Refill over time
# ---------------------------------------------------------------------------


async def test_refill_over_time_after_sleep() -> None:
    """`capacity=5, refill=1.0`: consume 5, sleep 1.2s, take 1 → allowed.

    REQ-RL-013 scenario 2: with `refill_rate=1.0` (1 token/sec),
    after a 1.2s sleep the bucket has refilled 1.2 tokens. The
    next consume (`cost=1.0`) finds `tokens >= cost` and
    returns `allowed=True` (the bucket state was incremented
    by the Lua script's `delta * rate` math before the
    `tokens >= cost` check).
    """
    namespace = _unique_namespace("test-rl-real-refill")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        # `refill_rate=1.0` = 1 token/sec. `capacity=5` so the
        # window-equivalent is 5 seconds.
        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=5,
            refill_rate=1.0,
        )
        # Drain the bucket.
        for _ in range(5):
            d = await bucket.try_acquire("key1", cost=1.0)
            assert d.allowed is True
        # Now empty (within clock granularity).
        d_empty = await bucket.try_acquire("key1", cost=1.0)
        assert d_empty.allowed is False

        # Wait 1.2 seconds; the bucket refills 1.2 tokens.
        await asyncio.sleep(1.2)

        # The next consume should be allowed (we have ≥ 1 token).
        d_refilled = await bucket.try_acquire("key1", cost=1.0)
        assert d_refilled.allowed is True
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace}:key1")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 3 — Atomicity under concurrency
# ---------------------------------------------------------------------------


async def test_atomicity_under_concurrent_gather() -> None:
    """`capacity=3, refill=0`: 20 concurrent `try_acquire` → exactly 3 allowed.

    REQ-RL-013 scenario 3: Redis `EVAL` is atomic; the
    refill+check+decrement runs as a single command. 20
    concurrent goroutines against a `capacity=3` bucket MUST
    see exactly 3 `allowed=True` and 17 `allowed=False`. This
    is the canonical "Lua script is atomic" test.
    """
    namespace = _unique_namespace("test-rl-real-concurrent")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=3,
            refill_rate=0.0,
        )
        # 20 concurrent `try_acquire` calls against the same key.
        decisions = await asyncio.gather(
            *[bucket.try_acquire("shared_key", cost=1.0) for _ in range(20)]
        )
        allowed_count = sum(1 for d in decisions if d.allowed)
        denied_count = sum(1 for d in decisions if not d.allowed)
        assert allowed_count == 3, f"expected 3 allowed, got {allowed_count}"
        assert denied_count == 17, f"expected 17 denied, got {denied_count}"
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace}:shared_key")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 4 — TTL is set
# ---------------------------------------------------------------------------


async def test_ttl_is_set_after_try_acquire() -> None:
    """After `try_acquire`, `client.ttl(redis_key)` is a positive integer ≤ 2 × window.

    REQ-RL-013 scenario 4: the Lua script does
    `EXPIRE key, ceil(capacity / rate) * 2`. With
    `capacity=5, refill_rate=1.0`, the TTL is
    `ceil(5/1) * 2 = 10` seconds. The test asserts the TTL is
    a positive integer ≤ 10 (allowing for slight clock drift
    between the `EXPIRE` and the subsequent `TTL` call).
    """
    namespace = _unique_namespace("test-rl-real-ttl")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        capacity = 5
        refill_rate = 1.0
        # `math.ceil(capacity / rate) * 2` is the Lua script's TTL formula.
        expected_ttl = math.ceil(capacity / refill_rate) * 2

        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=capacity,
            refill_rate=refill_rate,
        )
        await bucket.try_acquire("key1", cost=1.0)

        # Inspect the actual TTL.
        actual_ttl = await client.ttl(f"{namespace}:key1")
        assert actual_ttl > 0, f"TTL not set or expired: {actual_ttl}"
        # Allow a 1-second drift (Redis might have decremented
        # by 1 between the EXPIRE and the TTL inspection).
        assert actual_ttl <= expected_ttl, (
            f"TTL {actual_ttl} > expected {expected_ttl} (2 × window)"
        )
        assert actual_ttl >= expected_ttl - 2, (
            f"TTL {actual_ttl} < expected {expected_ttl} - 2 (too short)"
        )
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace}:key1")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 5 — Namespace prefix isolation
# ---------------------------------------------------------------------------


async def test_namespace_prefix_isolation() -> None:
    """Two `RedisTokenBucket` instances with different namespaces → distinct keys.

    REQ-RL-013 scenario 5: the namespace is the first
    colon-separated segment of the Redis key
    (`f"{namespace}:{key}"`). Two instances with the same key
    but different namespaces MUST produce different Redis
    keys, so the rate-limiter buckets are independent.
    """
    namespace_a = _unique_namespace("test-rl-real-ns-a")
    namespace_b = _unique_namespace("test-rl-real-ns-b")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        bucket_a = RedisTokenBucket(
            client=client, namespace=namespace_a, capacity=5, refill_rate=0.0
        )
        bucket_b = RedisTokenBucket(
            client=client, namespace=namespace_b, capacity=5, refill_rate=0.0
        )
        await bucket_a.try_acquire("shared", cost=1.0)
        await bucket_b.try_acquire("shared", cost=1.0)

        # The actual Redis keys MUST be different.
        assert f"{namespace_a}:shared" != f"{namespace_b}:shared"
        # Both keys exist in Redis.
        assert await client.exists(f"{namespace_a}:shared") == 1
        assert await client.exists(f"{namespace_b}:shared") == 1
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace_a}:shared")
            await client.delete(f"{namespace_b}:shared")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 6 — KEYS/ARGV ordering
# ---------------------------------------------------------------------------


async def test_keys_argv_ordering_in_eval_call() -> None:
    """Spy on `client.eval(...)` and assert the arg ordering: numkeys, KEY, ARGV[1..4].

    REQ-RL-013 scenario 6: Redis `EVAL` has a strict signature
    `EVAL script numkeys KEYS ARGV`. A typo in the ordering
    (e.g., `KEYS[1]` swapped with `ARGV[1]`, or `numkeys` set
    to 0) would cause silent logic bugs. The test wraps the
    real `client.eval` with a recording spy, calls
    `try_acquire`, and asserts the args.
    """
    namespace = _unique_namespace("test-rl-real-eval")
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=5,
            refill_rate=1.0,
        )

        # Spy on `client.eval`. The Lua script source is large;
        # we don't compare the script body, just the call args.
        original_eval = client.eval
        eval_calls: list[tuple[Any, ...]] = []

        async def spy_eval(  # type: ignore[no-untyped-def]
            script, numkeys, *args
        ):
            eval_calls.append((script, numkeys, *args))
            return await original_eval(script, numkeys, *args)

        client.eval = spy_eval

        # Trigger one `try_acquire`.
        await bucket.try_acquire("the_key", cost=1.0)

        # The spy recorded exactly 1 call.
        assert len(eval_calls) == 1, f"expected 1 eval call, got {len(eval_calls)}"
        script, numkeys, *args = eval_calls[0]

        # `numkeys` MUST be 1 (the script uses KEYS[1]).
        assert numkeys == 1, f"numkeys={numkeys}, expected 1"
        # `KEYS[1]` is the first positional arg.
        keys = args[:numkeys]
        argv = args[numkeys:]
        # The key is f"{namespace}:{key}".
        assert keys[0] == f"{namespace}:the_key", f"KEYS[0]={keys[0]!r}"
        # `ARGV[1..4]` are: capacity, refill_rate, now, cost.
        # They are strings (the script uses `tonumber()` to parse).
        assert len(argv) == 4, f"ARGV length={len(argv)}, expected 4"
        assert float(argv[0]) == 5.0, f"ARGV[1] (capacity)={argv[0]!r}"
        assert float(argv[1]) == 1.0, f"ARGV[2] (refill_rate)={argv[1]!r}"
        assert float(argv[2]) > 0, f"ARGV[3] (now)={argv[2]!r}"
        assert float(argv[3]) == 1.0, f"ARGV[4] (cost)={argv[3]!r}"
    finally:
        with contextlib.suppress(Exception):
            await client.delete(f"{namespace}:the_key")
        await client.aclose()


# ---------------------------------------------------------------------------
# REQ-RL-013 scenario 7 — Hash truncation correctness
# ---------------------------------------------------------------------------


async def test_hash_truncation_in_actual_redis_key() -> None:
    """A hashed client_id produces a `f"{namespace}:[0-9a-f]{16}"` Redis key.

    REQ-RL-013 scenario 7: the middleware applies
    `hash_client_id(resolved_id)` before `try_acquire`. The
    actual Redis key in the production path is
    `f"rate-limiter:{sha256(client_id)[:16]}"` — the
    raw IP is NEVER in the key. The test mirrors this end
    to end: compute the hash, call `try_acquire`, inspect
    the actual Redis key.
    """
    namespace = "rate-limiter"  # match the production default
    client_host = "2001:0db8:0000:0000:0000:ff00:0042:8329"
    expected_hash = hash_client_id(client_host)
    expected_key = f"{namespace}:{expected_hash}"

    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=False
    )
    try:
        bucket = RedisTokenBucket(
            client=client,
            namespace=namespace,
            capacity=5,
            refill_rate=0.0,
        )
        # The middleware would call `hash_client_id(client_host)`
        # BEFORE `try_acquire`. We replicate that here.
        await bucket.try_acquire(expected_hash, cost=1.0)

        # The actual Redis key matches the production pattern.
        assert await client.exists(expected_key) == 1
        # The key format is `rate-limiter:[0-9a-f]{16}`.
        assert re.fullmatch(rf"{namespace}:[0-9a-f]{{16}}", expected_key), (
            f"key format wrong: {expected_key!r}"
        )
        # The raw IPv6 is NOT a substring of the key.
        assert client_host not in expected_key
    finally:
        with contextlib.suppress(Exception):
            await client.delete(expected_key)
        await client.aclose()
