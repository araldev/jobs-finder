"""In-memory token-bucket rate limiter.

Spec: REQ-RL-002 (`InMemoryTokenBucket` — token-bucket, per-key, lazy refill).

Algorithm:
  State per key: `(tokens: float, last_refill_at: float)`.
  On `try_acquire(key, cost, now=clock())`:
    1. Lazy-init the bucket to `(capacity, now)` if missing.
    2. Compute `delta = max(0, now - last_refill_at)`.
    3. Refill: `tokens = min(capacity, tokens + delta * refill_rate)`.
    4. Update `last_refill_at = now`.
    5. Atomic check-and-decrement under a per-key `asyncio.Lock`:
         - If `tokens >= cost`: decrement, allow.
         - Else: compute `retry_after = (cost - tokens) / refill_rate`, deny.

Edge cases (pinned by tests):
  - `cost > capacity`: deny immediately with `retry_after = cost / refill_rate`
    (deferred, not "never" — a future bucket could grow into satisfying it).
  - `cost <= 0`: always allow, no token consumption (degenerate; defensive).
  - `clock()` going backward: `delta = 0` (no free tokens from a clock jump).
  - Per-key `asyncio.Lock` is created lazily on first access.

The `clock: Callable[[], float] = time.monotonic` injection pattern
(introduced here, not in the cache) gives the unit tests a deterministic
way to drive the refill math without `asyncio.sleep`. Production callers
omit the arg and the real monotonic clock is used.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from jobs_finder.application.ports import RateLimitDecision, RateLimitPort


class InMemoryTokenBucket(RateLimitPort):
    """Per-key in-memory token-bucket rate limiter. Default backend.

    REQ-RL-002: implements the `RateLimitPort` Protocol using the
    token-bucket algorithm. `capacity` and `refill_rate` are derived
    from `Settings.rate_limit_requests` (capacity) and
    `capacity / window_seconds` (refill rate in tokens/sec). The
    `clock` parameter is constructor-injected for testability.

    No background tasks are spawned — the refill is lazy on every
    `try_acquire` call. Per-key concurrency is serialized with an
    `asyncio.Lock` created on first access.

    `__slots__` is set so the instance has no `__dict__` (saves
    memory at high request rates; mirrors the project's
    `RateLimitDecision` dataclass style).
    """

    __slots__ = (
        "_capacity",
        "_refill_rate",
        "_clock",
        "_buckets",
        "_locks",
    )

    def __init__(
        self,
        capacity: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Construct the bucket.

        Args:
            capacity: Max tokens per key (= max burst). Pinned from
                `Settings.rate_limit_requests`.
            window_seconds: Refill period. The refill rate is
                `capacity / window_seconds` tokens per second.
            clock: A callable returning a monotonic float.
                Production: `time.monotonic`. Tests inject a
                synthetic clock to drive the refill math
                deterministically without `asyncio.sleep`.
        """
        self._capacity: float = float(capacity)
        self._refill_rate: float = float(capacity) / float(window_seconds)
        self._clock: Callable[[], float] = clock
        # `(tokens, last_refill_at)` per key. Lazy-initialized on first access.
        self._buckets: dict[str, tuple[float, float]] = {}
        # Per-key lock; lazy-initialized on first access. Held only across
        # the read-modify-write of the bucket state (microseconds).
        self._locks: dict[str, asyncio.Lock] = {}

    async def try_acquire(self, key: str, cost: float = 1.0) -> RateLimitDecision:
        """Try to acquire `cost` tokens for `key`.

        Returns a `RateLimitDecision`. On `allowed=True`, the call
        has decremented the bucket. On `allowed=False`, the bucket
        state is unchanged and `retry_after` is the seconds-until-
        enough-tokens.

        Edge cases (pinned by tests):
          - `cost <= 0` -> always allow, no consumption.
          - `cost > capacity` -> always deny, `retry_after = cost / refill_rate`.
          - `clock()` going backward -> `delta = 0` (no free tokens).
        """
        # Defensive: degenerate `cost` (zero or negative) is always allowed
        # and does NOT consume tokens (a misconfigured caller should not
        # poison the bucket).
        if cost <= 0.0:
            tokens_now = self._current_tokens(key)
            return RateLimitDecision(
                allowed=True,
                remaining=tokens_now,
                reset_after=self._reset_after_for(tokens_now),
                retry_after=0.0,
            )

        # Defensive: cost larger than capacity is unsatisfiable, so deny
        # with the `retry_after` that would have been needed. The bucket
        # state is unchanged (we did NOT consume tokens).
        if cost > self._capacity:
            return RateLimitDecision(
                allowed=False,
                remaining=0.0,
                reset_after=self._capacity / self._refill_rate,
                retry_after=cost / self._refill_rate,
            )

        # Per-key lock for atomic read-modify-write. The lock is
        # acquired INSIDE the per-key dict (a single asyncio.Lock per
        # key, created lazily). The lock body is microseconds — the
        # async event loop yields nothing inside the body.
        lock = self._locks.get(key) or self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = self._clock()
            tokens, last_refill_at = self._buckets.get(key, (self._capacity, now))
            # Lazy refill: clamp `delta` to >= 0 so a backward clock
            # jump does not generate free tokens.
            delta = now - last_refill_at
            delta = max(delta, 0.0)
            tokens = min(self._capacity, tokens + delta * self._refill_rate)
            last_refill_at = now

            if tokens >= cost:
                tokens -= cost
                self._buckets[key] = (tokens, last_refill_at)
                return RateLimitDecision(
                    allowed=True,
                    remaining=tokens,
                    reset_after=self._reset_after_for(tokens),
                    retry_after=0.0,
                )
            # Denied: compute seconds until `cost` tokens are available.
            deficit = cost - tokens
            retry_after = deficit / self._refill_rate
            # Persist the (refilled but not decremented) state so the
            # caller sees a coherent snapshot.
            self._buckets[key] = (tokens, last_refill_at)
            return RateLimitDecision(
                allowed=False,
                remaining=0.0,
                reset_after=self._reset_after_for(tokens),
                retry_after=retry_after,
            )

    def _current_tokens(self, key: str) -> float:
        """Read the bucket's current token count (lazy-refilled)."""
        now = self._clock()
        tokens, last_refill_at = self._buckets.get(key, (self._capacity, now))
        delta = now - last_refill_at
        delta = max(delta, 0.0)
        return min(self._capacity, tokens + delta * self._refill_rate)

    def _reset_after_for(self, tokens: float) -> float:
        """Seconds until the bucket is full at the current refill rate.

        When `refill_rate=0` (frozen clock), this is `inf` — the
        bucket can never refill. The middleware caps the value at
        `int(math.ceil(...))`; `inf` becomes a very large int,
        which is acceptable for the `X-RateLimit-Reset` header
        (the only realistic way to hit `inf` is `window_seconds=0`,
        which the `Settings` validator rejects with `gt=0.0`).
        """
        if self._refill_rate <= 0.0:
            return float("inf")
        return (self._capacity - tokens) / self._refill_rate
