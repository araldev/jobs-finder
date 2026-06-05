"""Outbound ports: the application layer's contracts with any job-search
source (LinkedIn, Indeed, InfoJobs, ...) and with any TTL cache
(in-memory v1, future Redis / Memcached).

Spec: REQ-008 (search port), REQ-C-001 (cache port), REQ-C-005
(per-source key isolation), REQ-RL-001 (rate-limit port), REQ-RL-004
(NoOp pre-condition).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Protocol, TypeVar

from jobs_finder.domain.job import Job

K_co = TypeVar("K_co", contravariant=True)  # noqa: PLC0105
V = TypeVar("V")


class JobSearchPort(Protocol):
    """A job-search source. Implementations live in `infrastructure/`.

    The default value on `limit` is duplicated in the Pydantic schema at the
    presentation boundary; the application trusts the caller to pass an
    already-validated value.
    """

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        """Search the source for jobs matching the criteria."""
        ...


class CachePort(Protocol[K_co, V]):
    """A typed key/value cache with TTL semantics.

    Implementations MUST be safe for concurrent use in a single
    process. Cross-process / cross-host caching is out of scope
    for v1 (the `cache-ttl` change ships an in-memory
    implementation only; the Protocol is the seam that lets a
    future change swap in Redis / Memcached without touching the
    application layer).
    """

    async def get(self, key: K_co) -> V | None:
        """Return the stored value if not expired, else `None`."""
        ...

    async def set(self, key: K_co, value: V) -> None:
        """Store the value with the configured TTL. Overwrites prior."""
        ...

    async def delete(self, key: K_co) -> None:
        """Remove the key (no-op if absent)."""
        ...

    async def clear(self) -> None:
        """Remove all keys. Used by tests; not exposed in production."""
        ...


class JobSearchCacheKey(NamedTuple):
    """The cache key tuple for the 3 source use cases.

    The `source` field is a string literal in
    `{"linkedin", "indeed", "infojobs"}` so a query on
    `/jobs/linkedin?keywords=python&location=madrid` does NOT
    share a cache entry with the same query on `/jobs/indeed`
    (REQ-C-005 — per-source isolation).

    Tuple equality and hashing are exact for `NamedTuple`, so
    there is no key collision risk.
    """

    source: str
    keywords: str
    location: str
    limit: int


# ---------------------------------------------------------------------------
# Rate limiting (REQ-RL-001, REQ-RL-004 NoOp pre-condition)
#
# `RateLimitPort` is the application layer's seam for "any token-bucket
# rate limiter". Two implementations live in `infrastructure/rate_limit/`:
# `InMemoryTokenBucket` (the default, per-process) and `RedisTokenBucket`
# (the optional, cross-process backend; added in T-003). The factory in
# `infrastructure/rate_limit/_factory.py` dispatches between them per
# `RATE_LIMIT_BACKEND=memory|redis` (REQ-RL-004).
#
# `NoOpRateLimiter` is the dispatch target for `RATE_LIMIT_ENABLED=false`
# (REQ-RL-004). It holds NO per-key state (a true no-op — see design §15.4)
# and every call returns `allowed=True` with `remaining=capacity` and
# `retry_after=0.0`. The factory in T-003 returns this class so the
# disabled-state is `isinstance`-assertable in tests.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The result of a `try_acquire` call.

    REQ-RL-001 pins 4 fields:
      - `allowed: bool` — whether the request is permitted.
      - `remaining: float` — tokens left after this request.
      - `reset_after: float` — seconds until full refill (informational).
      - `retry_after: float` — seconds until enough tokens exist for `cost`
        (only meaningful when `allowed=False`; may equal `reset_after`
        for token bucket when `tokens=0`).

    `frozen=True` makes the decision immutable (consumers cannot mutate
    the result of a `try_acquire` call). `slots=True` saves ~280 bytes
    per decision at 1M decisions/day — same pattern as the project's
    `Job` value-object style (`domain/job.py`).
    """

    allowed: bool
    remaining: float
    reset_after: float
    retry_after: float


class RateLimitPort(Protocol):
    """A token-bucket rate limiter. Implementations live in `infrastructure/`.

    REQ-RL-001: the only public method is `async def try_acquire(key,
    cost=1.0) -> RateLimitDecision`. Implementations MUST be safe for
    concurrent use in a single process (per-key serialization) and MUST
    NEVER raise (a backend outage degrades to `allowed=True`, not 5xx).

    The default `cost=1.0` is duplicated in the per-route cost map at
    the presentation boundary; the algorithm trusts the caller to pass
    an already-validated value.
    """

    async def try_acquire(self, key: str, cost: float = 1.0) -> RateLimitDecision:
        """Try to acquire `cost` tokens for `key`.

        Returns a `RateLimitDecision`. On `allowed=True`, the call has
        decremented the bucket (or is a no-op for `NoOpRateLimiter`).
        On `allowed=False`, the bucket state is unchanged and
        `retry_after` is the seconds-until-enough-tokens.
        """
        ...


class NoOpRateLimiter:
    """A true no-op rate limiter. The dispatch target for `RATE_LIMIT_ENABLED=false`.

    REQ-RL-004 NoOp pre-condition: a disabled rate limiter MUST NOT
    consume any per-key state and MUST be a true no-op for
    testability. Every `try_acquire` returns
    `RateLimitDecision(allowed=True, remaining=capacity, reset_after=0.0,
    retry_after=0.0)` regardless of `cost`. The class is a separate
    `class` (NOT a flag inside `InMemoryTokenBucket`) so:
      1. The factory in T-003 is `isinstance`-assertable
         (`build_rate_limiter(settings)` returns a `NoOpRateLimiter`).
      2. The "disabled" concept is NOT leaked into the algorithm code.
      3. The class exposes no per-key state — a future refactor that
         adds a `_buckets` dict would surface in
         `test_noop_rate_limiter_holds_no_per_key_state`.

    The class is NOT a `Protocol` subclass; it satisfies the
    `RateLimitPort` Protocol structurally (duck-typed `try_acquire`).
    Holding a `__slots__` of `("capacity",)` documents the
    no-state invariant at the type level.
    """

    __slots__ = ("_capacity",)

    def __init__(self, capacity: int) -> None:
        # The capacity is the value reported as `remaining` on every
        # call. A disabled limiter does not actually have a
        # `capacity` (no throttling happens), but reporting the
        # `RATE_LIMIT_REQUESTS` value gives clients a consistent
        # `X-RateLimit-Limit` header when `RATE_LIMIT_ENABLED=false`.
        self._capacity = float(capacity)

    async def try_acquire(self, key: str, cost: float = 1.0) -> RateLimitDecision:
        """Always allow. Never consumes state. `remaining=capacity`, `retry_after=0.0`."""
        return RateLimitDecision(
            allowed=True,
            remaining=self._capacity,
            reset_after=0.0,
            retry_after=0.0,
        )
