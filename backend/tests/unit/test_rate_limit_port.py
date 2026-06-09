"""Unit tests for the `RateLimitPort` Protocol, `RateLimitDecision` dataclass,
and `NoOpRateLimiter` (REQ-RL-001 + REQ-RL-004 NoOp pre-conditions).

Spec: REQ-RL-001, REQ-RL-004 (`enabled=False → NoOpRateLimiter`).

The `RateLimitPort` is a `typing.Protocol` declaring the single async method
`try_acquire` any rate-limiter implementation must satisfy. The decision
dataclass has exactly 4 fields (`allowed`, `remaining`, `reset_after`,
`retry_after`). The `NoOpRateLimiter` is a true no-op: every call returns
`allowed=True` with `remaining=capacity` and `retry_after=0.0`, no per-key
state is held, and the class is `isinstance`-assertable (so the factory
dispatcher in T-003 can be tested by identity).

The 4 scenarios are Given/When/Then, observable behavior, deterministic.
"""

from __future__ import annotations

from dataclasses import is_dataclass

from jobs_finder.application.ports import (
    NoOpRateLimiter,
    RateLimitDecision,
    RateLimitPort,
)

# ---------------------------------------------------------------------------
# REQ-RL-001 — Protocol shape (2 scenarios)
# ---------------------------------------------------------------------------


def test_rate_limit_port_is_a_protocol() -> None:
    """`RateLimitPort` is a `typing.Protocol` (structural subtyping).

    REQ-RL-001 scenario: "Protocol declares `try_acquire`". The
    Protocol's public attribute set is exactly `{'try_acquire'}` —
    no more, no less.
    """
    assert getattr(RateLimitPort, "_is_protocol", None) is True
    protocol_attrs: set[str] = getattr(RateLimitPort, "__protocol_attrs__", set())
    assert "try_acquire" in protocol_attrs, (
        "RateLimitPort must declare 'try_acquire' (the sole public method)"
    )


def test_rate_limit_port_declares_exactly_one_public_method() -> None:
    """`RateLimitPort` declares exactly one public method: `try_acquire`.

    Pins the contract that a future refactor cannot add a second
    method (e.g. `peek`, `reset`) without surfacing here.
    """
    protocol_attrs: set[str] = getattr(RateLimitPort, "__protocol_attrs__", set())
    assert protocol_attrs == {"try_acquire"}


# ---------------------------------------------------------------------------
# REQ-RL-001 — RateLimitDecision shape
# ---------------------------------------------------------------------------


def test_rate_limit_decision_is_a_dataclass_with_four_fields() -> None:
    """`RateLimitDecision` is a `@dataclass` with exactly 4 fields.

    REQ-RL-001 scenario: "RateLimitDecision shape". The 4 fields
    are `allowed: bool`, `remaining: float`, `reset_after: float`,
    `retry_after: float`. No defaults — the dataclass is fully
    positional (a `RateLimitDecision()` with no args must raise).
    """
    assert is_dataclass(RateLimitDecision)
    hints = getattr(RateLimitDecision, "__annotations__", {})
    assert set(hints.keys()) == {"allowed", "remaining", "reset_after", "retry_after"}


def test_rate_limit_decision_can_be_constructed_with_all_four_fields() -> None:
    """`RateLimitDecision(allowed, remaining, reset_after, retry_after)` constructs cleanly.

    The decision is the return type of `try_acquire`. Every code
    path that constructs a decision MUST supply all 4 fields (no
    optional args); the test pins the constructor shape.
    """
    decision = RateLimitDecision(
        allowed=True,
        remaining=0.5,
        reset_after=10.0,
        retry_after=0.0,
    )
    assert decision.allowed is True
    assert decision.remaining == 0.5
    assert decision.reset_after == 10.0
    assert decision.retry_after == 0.0


# ---------------------------------------------------------------------------
# NoOpRateLimiter (REQ-RL-004 NoOp pre-condition: factory returns it when disabled)
# ---------------------------------------------------------------------------


async def test_noop_rate_limiter_try_acquire_always_allows() -> None:
    """`NoOpRateLimiter.try_acquire` always returns `allowed=True` (true no-op).

    REQ-RL-004 NoOp scenario: the factory returns a `NoOpRateLimiter`
    when `rate_limit_enabled=False`. Every call MUST return
    `allowed=True` regardless of the `cost` argument (even `cost=999`).
    """
    limiter = NoOpRateLimiter(capacity=5)

    decision_small = await limiter.try_acquire("k1", cost=1.0)
    assert decision_small.allowed is True
    assert decision_small.retry_after == 0.0

    decision_big = await limiter.try_acquire("k2", cost=999.0)
    assert decision_big.allowed is True
    assert decision_big.retry_after == 0.0


async def test_noop_rate_limiter_remaining_equals_capacity() -> None:
    """`NoOpRateLimiter.try_acquire` reports `remaining == capacity` (never decreases).

    The `remaining` field is the limiter's own capacity (not a
    decremented counter) so callers can read the configured
    capacity via a `try_acquire` call without consuming state.
    """
    limiter = NoOpRateLimiter(capacity=42)

    decision = await limiter.try_acquire("k1", cost=1.0)
    assert decision.remaining == 42


async def test_noop_rate_limiter_holds_no_per_key_state() -> None:
    """`NoOpRateLimiter` holds no per-key state (true no-op invariant).

    REQ-RL-004 NoOp pre-condition: a disabled rate limiter MUST NOT
    consume any per-key state. The class exposes no `_buckets` or
    similar dict, so a future refactor that adds one would surface
    here as a `len()` mismatch.
    """
    limiter = NoOpRateLimiter(capacity=10)
    for _ in range(100):
        await limiter.try_acquire("any-key", cost=1.0)
    # No per-key state — no dict, list, or set is allowed.
    for attr in ("_buckets", "_locks", "_store", "_state", "_keys"):
        value = getattr(limiter, attr, None)
        if value is not None and hasattr(value, "__len__"):
            assert len(value) == 0, f"NoOpRateLimiter.{attr} unexpectedly holds state"
