"""Async Redis-backed implementation of the `RateLimitPort` Protocol.

Spec: REQ-RL-003 (atomic Lua, namespace, fail-open).

`RedisTokenBucket` is the optional cross-worker / cross-host rate
limiter, selected when `Settings.rate_limit_backend == "redis"`. It
coexists with `InMemoryTokenBucket` (the default) so a single
deployment can switch backends via the `RATE_LIMIT_BACKEND` env
var without restarting the app.

Atomicity: the refill+consume happens inside a single Lua script
(`_LUA_SCRIPT`, inlined at the top of this module). Redis `EVAL`
is atomic — the entire script runs as a single command on the
server; no concurrent client can interleave a read or write
between the GET and the SET below. This is the canonical CAS
boundary for the rate limiter (design §6).

The client is `redis.asyncio.Redis` (`redis>=5.0`, already a dep
for the cache). The key format is `f"{namespace}:{key}"` (a HASH
with `tokens` + `ts` fields). The TTL is `ceil(capacity / rate) * 2`
seconds (2× the window) so a key that goes idle does not accumulate
stale state forever.

`socket_errors` (default `True`) catches `redis.exceptions.RedisError`
on any `try_acquire` call, logs WARNING, and returns
`allowed=True` (fail-open). A rate-limiter Redis outage degrades
to "no throttling", never 5xx (asymmetric to the cache's fail-fast
ping — the rate limiter is OPTIONAL, the cache is not).
"""

from __future__ import annotations

import logging
import time

import redis.asyncio as redis_async
import redis.exceptions

from jobs_finder.application.ports import RateLimitDecision, RateLimitPort

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lua script (module-level triple-quoted string)
# ---------------------------------------------------------------------------
# Atomicity guarantee: Redis EVAL is atomic — the entire script
# runs as a single command on the server; no concurrent client can
# interleave a read or write between the HMGET and the HMSET
# below. This is the canonical CAS boundary for the rate limiter.
# A future refactor that splits the script into 2+ EVAL calls
# would break the atomicity guarantee — keep it as a single
# script.

_LUA_SCRIPT = """
-- Token-bucket refill + try_acquire, atomic via Redis EVAL.
-- KEYS[1] = "{namespace}:{key}"   (e.g. "rate-limiter:1.2.3.4")
-- ARGV[1] = capacity (float, e.g. "60")
-- ARGV[2] = refill_rate (float tokens/sec, e.g. "1")
-- ARGV[3] = now (float; client passes via ARGV, not TIME, so
--                tests can inject a deterministic clock)
-- ARGV[4] = cost (float, default "1")
-- Returns: {allowed (0|1), remaining (string float), reset_after
--           (string float), retry_after (string float)}
local key       = KEYS[1]
local capacity  = tonumber(ARGV[1])
local rate      = tonumber(ARGV[2])
local now       = tonumber(ARGV[3])
local cost      = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local last_ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    last_ts = now
end

local delta = now - last_ts
if delta < 0 then delta = 0 end
tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
local retry_after = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    local deficit = cost - tokens
    retry_after = deficit / rate
end

local reset_after = (capacity - tokens) / rate

redis.call("HMSET", key, "tokens", tokens, "ts", now)
-- 2x the window is a generous TTL so a key that goes idle does not
-- accumulate stale state forever. Server-side TIME drift is bounded
-- by this TTL.
local ttl = math.ceil(capacity / rate) * 2
redis.call("EXPIRE", key, ttl)

return {allowed, tostring(tokens), tostring(reset_after), tostring(retry_after)}
"""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class RedisTokenBucket(RateLimitPort):
    """Async Redis-backed token bucket. Satisfies the `RateLimitPort` Protocol.

    REQ-RL-003: implements `RateLimitPort` using a single
    atomic `EVAL` of `_LUA_SCRIPT`. The namespace isolates
    multiple `RedisTokenBucket` instances on the same Redis
    (the composition root can create separate buckets for
    separate features by passing different `namespace` values;
    the rate-limiter factory uses
    `settings.rate_limit_redis_namespace`).

    `swallow_errors=True` (default) catches any
    `redis.exceptions.RedisError` on `try_acquire` and returns
    a fail-open decision. The caller is NEVER expected to
    handle Redis errors from this class — the fail-open is the
    whole point.
    """

    __slots__ = (
        "_client",
        "_namespace",
        "_capacity",
        "_refill_rate",
        "_swallow_errors",
    )

    def __init__(
        self,
        *,
        client: redis_async.Redis,
        namespace: str,
        capacity: int,
        refill_rate: float,
        swallow_errors: bool = True,
    ) -> None:
        """Construct the Redis-backed token bucket.

        Args:
            client: A `redis.asyncio.Redis` instance (injected
                for testability — production wires one shared
                client per app via the composition root, tests
                inject `fakeredis.aioredis.FakeRedis`).
            namespace: The key prefix (e.g. `"rate-limiter"`).
            capacity: Max tokens per key (max burst).
            refill_rate: Tokens per second (computed by the
                factory as `capacity / window_seconds`).
            swallow_errors: When `True` (default), any
                `redis.exceptions.RedisError` is caught, a
                WARNING is logged, and the call returns
                `allowed=True` (fail-open). Set to `False` to
                let the error propagate (useful in tests).
        """
        self._client = client
        self._namespace = namespace
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._swallow_errors = swallow_errors

    def _key(self, key: str) -> str:
        """Build the Redis key for `key` (`f"{namespace}:{key}"`)."""
        return f"{self._namespace}:{key}"

    async def try_acquire(self, key: str, cost: float = 1.0) -> RateLimitDecision:
        """Try to acquire `cost` tokens for `key` (single atomic `EVAL`).

        The `EVAL` is atomic: the entire refill+check+decrement
        runs as a single command on the Redis server. A race
        between 2 concurrent `try_acquire` calls on the same key
        is impossible — the second `EVAL` sees the first's
        decrement (or vice versa).
        """
        redis_key = self._key(key)
        # NOTE: `now` is passed as ARGV (not server-side `TIME`) so
        # tests can inject a deterministic clock by patching the
        # `client` or the `try_acquire` call site. Production uses
        # the real `time.monotonic` (or whatever the test fixture
        # wires).
        now = time.monotonic()
        try:
            raw = await self._client.eval(  # type: ignore[misc]
                _LUA_SCRIPT,
                1,  # numkeys
                redis_key,
                str(self._capacity),
                str(self._refill_rate),
                str(now),
                str(cost),
            )
        except redis.exceptions.RedisError as exc:
            if not self._swallow_errors:
                raise
            _LOGGER.warning(
                "RedisTokenBucket try_acquire failed: op=try_acquire key=%r error=%r",
                key,
                exc,
            )
            return RateLimitDecision(
                allowed=True,
                remaining=self._capacity,
                reset_after=0.0,
                retry_after=0.0,
            )

        # Decode the Lua return: `[allowed_int, remaining_str,
        # reset_after_str, retry_after_str]`. The strings are
        # already float-formatted by the script's `tostring()`.
        allowed_int, remaining_str, reset_after_str, retry_after_str = raw
        return RateLimitDecision(
            allowed=bool(int(allowed_int)),
            remaining=float(remaining_str),
            reset_after=float(reset_after_str),
            retry_after=float(retry_after_str),
        )
