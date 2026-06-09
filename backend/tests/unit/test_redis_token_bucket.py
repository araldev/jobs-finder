"""Unit tests for the `RedisTokenBucket` implementation.

Spec: REQ-RL-003.

The test seam is a custom `_FakeRedisWithLua` class that simulates
the atomic Lua script execution in Python. The standard
`fakeredis.aioredis.FakeRedis` does NOT support `EVAL` (it raises
`ResponseError: unknown command 'eval'`), so the unit tests need
a fake client that implements the same atomic semantics as the
production Lua script.

The 4 scenarios are Given/When/Then, observable behavior, deterministic
(no real network, no wall-clock dependence).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, cast

import pytest
import redis.asyncio as redis_async
import redis.exceptions

from jobs_finder.infrastructure.rate_limit.redis_token_bucket import RedisTokenBucket


class _AsyncRedisLike(Protocol):
    """A structural type for the `eval` method the bucket uses.

    Defined locally so the test fakes (`_FakeRedisWithLua`,
    `_RecordingFakeRedis`, `_BrokenRedis`) can be passed to
    `RedisTokenBucket(client=...)` without `# type: ignore`
    workarounds. The real `redis.asyncio.Redis` matches this
    shape.
    """

    async def eval(  # noqa: D102
        self,
        script: str | bytes,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeRedisWithLua(_AsyncRedisLike):
    """A `redis.asyncio.Redis`-shaped fake that simulates atomic Lua execution.

    `fakeredis.aioredis.FakeRedis` does NOT support `EVAL` (it
    raises `ResponseError: unknown command 'eval'`). This fake
    implements the same atomic semantics as the production Lua
    script in pure Python so the unit tests can verify the
    algorithm without a real Redis.

    The fake maintains per-key `(tokens, last_ts)` state and
    serializes each `eval` call with an `asyncio.Lock` so
    concurrent calls produce the same atomicity as the real
    `EVAL`. The fake does NOT spawn background tasks; refill
    is computed from the `now` argument (no time.monotonic).
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()
        self.eval_calls: list[tuple[str, list[str], list[str]]] = []

    async def eval(
        self,
        script: str | bytes,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Any:
        """Simulate the Lua script: atomic refill + check + decrement."""
        # Record the call (for the namespace-prefix assertion).
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        script_str = script if isinstance(script, str) else script.decode()
        self.eval_calls.append((script_str, [str(k) for k in keys], [str(a) for a in args]))

        # Atomic execution: hold the lock across the read-modify-write.
        async with self._lock:
            key = keys[0]
            capacity = float(args[0])
            rate = float(args[1])
            now = float(args[2])
            cost = float(args[3])
            entry = self._store.get(key)
            if entry is None:
                tokens = capacity
                last_ts = now
            else:
                tokens = entry["tokens"]
                last_ts = entry["ts"]
            # Refill (clamped to >= 0).
            delta = now - last_ts
            delta = max(delta, 0.0)
            tokens = min(capacity, tokens + delta * rate)
            allowed = 0
            retry_after = 0.0
            if tokens >= cost:
                tokens -= cost
                allowed = 1
            else:
                deficit = cost - tokens
                retry_after = deficit / rate if rate > 0 else 0.0
            reset_after = (capacity - tokens) / rate if rate > 0 else 0.0
            self._store[key] = {"tokens": tokens, "ts": now}
            return [allowed, str(tokens), str(reset_after), str(retry_after)]


class _RecordingFakeRedis(_AsyncRedisLike):
    """A `_FakeRedisWithLua` wrapper that records every `eval` call.

    Used to assert the key format (per-source namespace prefix).
    Wraps the Lua-fake and forwards `eval` (recording the keys).
    """

    def __init__(self, inner: _FakeRedisWithLua) -> None:
        self._inner = inner
        self.eval_keys: list[str] = []

    async def eval(
        self,
        script: str | bytes,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Any:
        keys = list(keys_and_args[:numkeys])
        for k in keys:
            self.eval_keys.append(k if isinstance(k, str) else k.decode())
        return await self._inner.eval(script, numkeys, *keys_and_args)


class _BrokenRedis(_AsyncRedisLike):
    """A `redis.asyncio.Redis`-shaped fake that always raises `ConnectionError`.

    Used to assert graceful degradation: `try_acquire` MUST catch
    `redis.exceptions.RedisError` and return `allowed=True` when
    `swallow_errors=True` (the default).
    """

    async def eval(
        self,
        script: str | bytes,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Any:
        raise redis.exceptions.ConnectionError("simulated: connection refused")

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# REQ-RL-003 — Lua script atomicity (1 scenario)
# ---------------------------------------------------------------------------


async def test_lua_atomicity_under_concurrent_gather() -> None:
    """10 concurrent `try_acquire` on the same key yield exactly `capacity` allows.

    The Lua script is atomic at the Redis level (single `EVAL`
    call, no client-side race). With `capacity=3, refill_rate=0.0`
    (frozen clock — the fake's `now` is the same on every call)
    and 10 concurrent acquires, exactly 3 are allowed and 7
    are denied.
    """
    bucket = RedisTokenBucket(
        client=cast(redis_async.Redis, _FakeRedisWithLua()),
        namespace="rl-test",
        capacity=3,
        refill_rate=0.0,
    )

    decisions = await asyncio.gather(*(bucket.try_acquire("k", cost=1.0) for _ in range(10)))
    allowed_count = sum(1 for d in decisions if d.allowed)
    denied_count = sum(1 for d in decisions if not d.allowed)
    assert allowed_count == 3, f"expected exactly 3 allowed, got {allowed_count}"
    assert denied_count == 7, f"expected exactly 7 denied, got {denied_count}"


# ---------------------------------------------------------------------------
# REQ-RL-003 — Namespace prefix in key
# ---------------------------------------------------------------------------


async def test_namespace_prefix_in_redis_key() -> None:
    """The captured Redis key is `f"{namespace}:{key}"` (per-source namespace).

    REQ-RL-003 scenario 2: "Namespace prefix in key". The
    `RedisTokenBucket` stores state at `{namespace}:{key}` (a
    HASH via `HMSET` in the Lua script). The test asserts the
    captured key starts with the namespace.
    """
    inner = _FakeRedisWithLua()
    recorder = _RecordingFakeRedis(inner)
    client = cast(redis_async.Redis, recorder)
    bucket = RedisTokenBucket(
        client=client,
        namespace="jobs-finder:rl",
        capacity=5,
        refill_rate=0.0,
    )

    await bucket.try_acquire("user-1", cost=1.0)

    assert len(recorder.eval_keys) == 1
    assert recorder.eval_keys[0] == "jobs-finder:rl:user-1"


# ---------------------------------------------------------------------------
# REQ-RL-003 — `swallow_errors=True` fail-open
# ---------------------------------------------------------------------------


async def test_swallow_errors_true_returns_fail_open_on_redis_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `ConnectionError` is swallowed and returns `allowed=True` + WARNING logged.

    REQ-RL-003 scenario 3: `swallow_errors=True` fail-open. A
    rate-limiter Redis outage degrades to "no throttling" (the
    caller gets `allowed=True`), never a 5xx. A WARNING is
    logged so operators can investigate.
    """
    bucket = RedisTokenBucket(
        client=cast(redis_async.Redis, _BrokenRedis()),
        namespace="rl-test",
        capacity=5,
        refill_rate=1.0,
        swallow_errors=True,  # explicit (also the default)
    )

    logger_name = "jobs_finder.infrastructure.rate_limit.redis_token_bucket"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        decision = await bucket.try_acquire("k", cost=1.0)

    assert decision.allowed is True
    assert decision.remaining == 5.0  # fail-open returns capacity
    assert decision.retry_after == 0.0
    # A WARNING was logged with the op + key + error.
    assert any("op=try_acquire" in rec.message and "k" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# REQ-RL-003 — `swallow_errors=False` propagates
# ---------------------------------------------------------------------------


async def test_swallow_errors_false_propagates_redis_error() -> None:
    """`swallow_errors=False` lets the `ConnectionError` propagate to the caller.

    REQ-RL-003 scenario 4: `swallow_errors=False` propagates. The
    caller can opt out of fail-open and handle the error itself
    (e.g. for tests that want to assert the error path).
    """
    bucket = RedisTokenBucket(
        client=cast(redis_async.Redis, _BrokenRedis()),
        namespace="rl-test",
        capacity=5,
        refill_rate=1.0,
        swallow_errors=False,
    )

    with pytest.raises(redis.exceptions.ConnectionError):
        await bucket.try_acquire("k", cost=1.0)
