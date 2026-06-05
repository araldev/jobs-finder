"""Unit tests for the `InMemoryTokenBucket` algorithm.

Spec: REQ-RL-002 (`InMemoryTokenBucket` — token-bucket, per-key, lazy refill).

The algorithm: a per-key `(tokens, last_refill_ts)` state, lazy refill on
every `try_acquire` call, then atomic check-and-decrement under a per-key
`asyncio.Lock`. No background tasks. The `clock: Callable[[], float]` is
constructor-injected for testability (the first place in the project to
inject a clock — the cache precedent uses `time.monotonic` directly).

The 6 scenarios are Given/When/Then, observable behavior, deterministic
(synthetic clock + `asyncio.Lock` for the concurrency check).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import pytest

from jobs_finder.application.ports import RateLimitDecision
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)

# ---------------------------------------------------------------------------
# REQ-RL-002 — 6 scenarios
# ---------------------------------------------------------------------------


async def test_allows_up_to_capacity_then_denies_one_over() -> None:
    """Bucket with `capacity=3, refill_rate=0.0` (frozen clock) allows 3, denies 4th.

    REQ-RL-002 scenario 1+2: "Allows up to capacity" + "Rejects one
    over capacity". The frozen clock is `lambda: 0.0` so the
    refill math is a no-op (0 tokens/sec * 0 delta = 0).
    """
    bucket = InMemoryTokenBucket(
        capacity=3,
        window_seconds=60.0,  # refill_rate = 3 / 60 = 0.05 (irrelevant — clock is frozen)
        clock=_frozen_clock(),
    )

    # 3 successful acquires, each with `remaining = 2, 1, 0`.
    for expected_remaining in (2, 1, 0):
        decision = await bucket.try_acquire("k", cost=1.0)
        assert decision.allowed is True
        assert decision.remaining == expected_remaining

    # 4th acquire: denied. `remaining=0`, `retry_after > 0`.
    denied = await bucket.try_acquire("k", cost=1.0)
    assert denied.allowed is False
    assert denied.remaining == 0.0
    assert denied.retry_after > 0.0


async def test_refill_after_window_with_synthetic_clock() -> None:
    """Bucket with `refill_rate=1.0` refills 1 token per second (synthetic clock).

    REQ-RL-002 scenario 3: "Refill after window". The test starts
    at `t=0`, consumes the bucket, advances the synthetic clock to
    `t=1.0`, and asserts the next `try_acquire(cost=1)` is allowed.
    """
    clock = _stepping_clock(initial=0.0)
    bucket = InMemoryTokenBucket(
        capacity=2,
        window_seconds=2.0,  # refill_rate = 2 / 2 = 1.0 token/sec
        clock=clock,
    )

    # Consume the bucket.
    await bucket.try_acquire("k", cost=1.0)  # remaining=1
    await bucket.try_acquire("k", cost=1.0)  # remaining=0
    denied = await bucket.try_acquire("k", cost=1.0)
    assert denied.allowed is False

    # Advance 1.0s: 1 token refilled.
    clock.advance(1.0)
    allowed = await bucket.try_acquire("k", cost=1.0)
    assert allowed.allowed is True
    assert allowed.remaining == pytest.approx(0.0, abs=1e-9)


async def test_clock_injection_used_for_refill_not_time_monotonic() -> None:
    """The bucket's `clock` parameter is the source of `last_refill_ts` (REQ-RL-002).

    REQ-RL-002 scenario 4: "Clock injection". The test sets the
    synthetic clock to a non-monotonic value (100.0) and asserts
    the bucket's internal state records that exact value (proving
    `time.monotonic()` is NOT used as a hidden fallback).
    """
    clock = _stepping_clock(initial=100.0)
    bucket = InMemoryTokenBucket(
        capacity=2,
        window_seconds=60.0,
        clock=clock,
    )

    await bucket.try_acquire("k", cost=1.0)
    # The internal `_buckets["k"]` is `(tokens, last_refill_ts)`. The
    # `last_refill_ts` MUST be exactly the clock's current value (100.0),
    # NOT `time.monotonic()` (which would be some small float near 0).
    _, last_refill_ts = bucket._buckets["k"]  # noqa: SLF001
    assert last_refill_ts == 100.0
    # And a second call updates it to the new clock value.
    clock.advance(5.0)
    await bucket.try_acquire("k", cost=1.0)
    _, last_refill_ts = bucket._buckets["k"]  # noqa: SLF001
    assert last_refill_ts == 105.0


async def test_per_key_isolation() -> None:
    """Two different keys each have their own bucket (no cross-key bleed).

    REQ-RL-002 scenario 5: "Per-key isolation". Consuming key `a`'s
    bucket does NOT affect key `b`'s bucket.
    """
    bucket = InMemoryTokenBucket(
        capacity=1,
        window_seconds=60.0,
        clock=_frozen_clock(),
    )

    # Consume key `a`.
    a1 = await bucket.try_acquire("a", cost=1.0)
    assert a1.allowed is True
    assert a1.remaining == 0.0

    # Key `b` is independent — its first call still has the full capacity.
    b1 = await bucket.try_acquire("b", cost=1.0)
    assert b1.allowed is True
    assert b1.remaining == 0.0

    # Key `a`'s 2nd call is still denied (no cross-key refill).
    a2 = await bucket.try_acquire("a", cost=1.0)
    assert a2.allowed is False


async def test_no_background_tasks_created() -> None:
    """The bucket creates NO long-lived `asyncio.Task`s (lazy refill only).

    REQ-RL-002 scenario 6: "No background tasks". The test snapshots
    the live `asyncio.all_tasks()` set, drives 100 `try_acquire`
    calls, and asserts no new long-lived tasks appeared.
    """
    bucket = InMemoryTokenBucket(
        capacity=5,
        window_seconds=60.0,
        clock=_frozen_clock(),
    )

    before = set(asyncio.all_tasks())
    for _ in range(100):
        await bucket.try_acquire("k", cost=1.0)
    after = set(asyncio.all_tasks())
    new_tasks = after - before
    # `all_tasks` may include the test's own coroutine; the point is
    # no bucket-spawned task is left over. The diff is 0 in practice
    # (the only difference is the test's own lifecycle).
    assert new_tasks == set(), f"unexpected new tasks: {new_tasks}"


async def test_concurrent_acquire_is_atomic_per_key() -> None:
    """10 concurrent `try_acquire` on the same key yield exactly `capacity` allows.

    REQ-RL-002 concurrency invariant: the per-key `asyncio.Lock`
    serializes the read-modify-write of the token bucket, so 10
    concurrent acquires against `capacity=3` allow exactly 3 and
    deny the other 7.
    """
    bucket = InMemoryTokenBucket(
        capacity=3,
        window_seconds=60.0,
        clock=_frozen_clock(),
    )

    decisions: list[RateLimitDecision] = await asyncio.gather(
        *(bucket.try_acquire("k", cost=1.0) for _ in range(10))
    )
    allowed_count = sum(1 for d in decisions if d.allowed)
    denied_count = sum(1 for d in decisions if not d.allowed)
    assert allowed_count == 3, f"expected exactly 3 allowed, got {allowed_count}"
    assert denied_count == 7, f"expected exactly 7 denied, got {denied_count}"


# ---------------------------------------------------------------------------
# Edge cases (additional to REQ-RL-002)
# ---------------------------------------------------------------------------


async def test_cost_greater_than_capacity_is_denied_with_correct_retry_after() -> None:
    """`cost > capacity` returns `allowed=False, retry_after = cost / refill_rate`.

    REQ-RL-002: "A `cost > capacity` request MUST return
    `allowed=False, retry_after = cost / refill_rate` (deferred
    until cost is satisfiable, not 'never')." The literal formula
    is `cost / refill_rate` (per the spec), even though the bucket
    could only fully satisfy the request if its `capacity` grew —
    the value is the "deferred" hint, not a strict ETA.
    """
    bucket = InMemoryTokenBucket(
        capacity=5,
        window_seconds=10.0,  # refill_rate = 5 / 10 = 0.5 token/sec
        clock=_frozen_clock(),
    )

    decision = await bucket.try_acquire("k", cost=10.0)
    assert decision.allowed is False
    # retry_after = cost / refill_rate = 10 / 0.5 = 20.0 (per spec).
    assert decision.retry_after == pytest.approx(20.0, abs=1e-9)


async def test_zero_or_negative_cost_is_a_no_op() -> None:
    """`cost <= 0` returns `allowed=True` with no token consumption (degenerate).

    REQ-RL-002: "A `cost <= 0` MUST return `allowed=True, remaining =
    current_bucket_level` (degenerate, but defined)." For a
    never-touched key, the `current_bucket_level` is `capacity`.
    A subsequent normal `cost=1` call MUST still see the full
    bucket (degenerate cost did not consume any state).
    """
    clock = _stepping_clock(initial=0.0)
    bucket = InMemoryTokenBucket(
        capacity=5,
        window_seconds=60.0,
        clock=clock,
    )

    decision_zero = await bucket.try_acquire("k", cost=0.0)
    assert decision_zero.allowed is True
    # `remaining` reports the current bucket level (full for a fresh key).
    assert decision_zero.remaining == pytest.approx(5.0, abs=1e-9)

    decision_neg = await bucket.try_acquire("k", cost=-1.0)
    assert decision_neg.allowed is True
    assert decision_neg.remaining == pytest.approx(5.0, abs=1e-9)

    # A subsequent normal call still gets the full bucket — degenerate
    # costs did NOT consume any state.
    real = await bucket.try_acquire("k", cost=1.0)
    assert real.allowed is True
    assert real.remaining == pytest.approx(4.0, abs=1e-9)


async def test_clock_going_backward_yields_zero_delta() -> None:
    """`clock()` going backward computes `delta = 0` (no free tokens from a jump).

    A wall-clock adjustment (e.g. NTP) would not generate free
    tokens from a backward jump. The algorithm clamps `delta` to
    `max(0, now - last_refill_ts)`.
    """
    clock = _stepping_clock(initial=100.0)
    bucket = InMemoryTokenBucket(
        capacity=5,
        window_seconds=10.0,  # refill_rate = 0.5
        clock=clock,
    )

    # Consume the bucket.
    for _ in range(5):
        await bucket.try_acquire("k", cost=1.0)

    # Advance the clock to 50.0 (BACKWARD). No tokens should refill.
    clock.advance(-50.0)
    decision = await bucket.try_acquire("k", cost=1.0)
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frozen_clock() -> Callable[[], float]:
    """Return a clock that always returns 0.0 (frozen time, no refill)."""
    return lambda: 0.0


class _SteppingClock:
    """A mutable-clock fixture for refill tests.

    `initial` is the starting value. `advance(delta)` moves the
    clock forward (or backward) by `delta`. `__call__` returns
    the current value. Two `SteppingClock` instances are
    independent (no global state).
    """

    def __init__(self, initial: float) -> None:
        self._now = initial

    def advance(self, delta: float) -> None:
        self._now += delta

    def __call__(self) -> float:
        return self._now


def _stepping_clock(initial: float) -> _SteppingClock:
    """Return a `_SteppingClock` starting at `initial`."""
    return _SteppingClock(initial)


# Sanity check: the default constructor uses `time.monotonic` (the
# REQ-RL-002 design spec). The test asserts the runtime type is
# `time.monotonic` (not the synthetic) when no clock is injected —
# the type's identity is stable, the call returns a float.


def test_default_clock_is_time_monotonic() -> None:
    """The default `clock` parameter is `time.monotonic` (no test injection).

    REQ-RL-002: the constructor default is `clock: Callable[[], float]
    = time.monotonic`. The test asserts the runtime default IS the
    `time.monotonic` builtin (not a sentinel or a stub).
    """
    bucket = InMemoryTokenBucket(capacity=5, window_seconds=60.0)
    # `time.monotonic` returns a float strictly >= 0; the test asserts
    # the function name and the call result shape.
    assert bucket._clock is time.monotonic  # noqa: SLF001
    assert isinstance(bucket._clock(), float)  # noqa: SLF001
    assert bucket._clock() >= 0.0  # noqa: SLF001
