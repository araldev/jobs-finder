"""Outbound ports: the application layer's contracts with any job-search
source (LinkedIn, Indeed, InfoJobs, ...) and with any TTL cache
(in-memory v1, future Redis / Memcached).

Spec: REQ-008 (search port), REQ-C-001 (cache port), REQ-C-005
(per-source key isolation), REQ-RL-001 (rate-limit port), REQ-RL-004
(NoOp pre-condition).

The `ai-chat-filter` change (T-010) adds `LLMClientPort` to this
module — the application's seam to any LLM provider. The
infrastructure layer implements it (e.g. `MiniMaxLLMClient`);
the use case depends on the Protocol only, never on the concrete
client. A `FakeLLMClient` in the test layer satisfies the Protocol
structurally so the use case can be unit-tested without invoking
a real LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NamedTuple, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

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


# ---------------------------------------------------------------------------
# LLM intent extraction (REQ-CHAT-INT-001, REQ-LLM-SEC-002,
# `chat-filter-2stage` change T-002)
#
# `Intent` is the structured value object the stage-1 LLM call
# returns. It is the PORT'S CONTRACT — defined in the application
# layer so the use case (which lives in `application/`) can import
# it without depending on infrastructure. The Pydantic-strict
# parser in `infrastructure/llm/_intent_parser.py` imports the
# class from here (infrastructure → application is fine; the
# reverse is forbidden by the dependency rule).
#
# The class uses `model_config = ConfigDict(extra="forbid")` so a
# model that returns an unknown field (e.g. `salary_range`) raises
# `pydantic.ValidationError`, which the parser catches and re-raises
# as `LLMResponseParseError` (REQ-LLM-SEC-002).
#
# The 7 fields are: `q`, `location`, `experience_years`, `remote`,
# `employment_type`, `confidence` (required), `notes` (optional
# escape hatch for unstructured intent).
# ---------------------------------------------------------------------------


class Intent(BaseModel):
    """The 7-field structured intent extracted from a user message.

    Pydantic `extra="forbid"` rejects unknown fields (REQ-LLM-SEC-002):
    a model that returns `salary_range` (not in the schema) raises
    `pydantic.ValidationError`, which the parser catches and re-raises
    as `LLMResponseParseError` so the `IntentExtractor` can decide
    between retry-once and raise-to-use-case.

    `experience_years: int | None` does NOT coerce strings — the
    prompt tells the model to return a number or `null`, and
    Pydantic's `int` type rejects `"2-3"` at validation time.

    `confidence: float = Field(ge=0.0, le=1.0)` is bounded in both
    directions. A model that returns `confidence: 1.5` (over-confident)
    or `confidence: -0.1` (nonsensical) is rejected. The use case
    reads `confidence` to decide between 2-stage and v1-fallback
    (REQ-CHAT-INT-004) — an out-of-range value would silently
    mis-route the request.

    `notes: str | None = None` is the unstructured intent escape
    hatch. The LLM may put information the 6 typed fields cannot
    capture (salary range, visa sponsorship, company size) in
    `notes`; the use case does not act on `notes` directly (stage
    3 does not see it), but ops can log it for visibility.

    The model is intentionally narrow (6 typed fields + `notes`)
    to make the prompt and the schema both concise. Future
    changes can add fields; the `extra="forbid"` rule protects
    against silent schema drift.
    """

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    location: str | None = None
    experience_years: int | None = None
    remote: bool | None = None
    employment_type: (
        Literal["full_time", "part_time", "contract", "internship", "freelance"] | None
    ) = None
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


# ---------------------------------------------------------------------------
# LLM client (REQ-LLM-001, `ai-chat-filter` change T-010)
#
# `LLMClientPort` is the application layer's seam for "any LLM
# provider that can complete a chat-completion-style request". The
# concrete implementation lives in `infrastructure/llm/_client.py`
# (added in T-011) and conforms to the Protocol structurally — no
# explicit base-class inheritance is required.
#
# The Protocol is NOT `@runtime_checkable`. Structural conformance
# is enforced by mypy --strict at type-check time; the test layer
# uses a `FakeLLMClient` (or any class with a matching
# `async def complete(*, system, user) -> str` method) and the
# Protocol never runs `isinstance(...)` checks. This keeps the
# runtime cost zero and matches the existing pattern used by
# `JobSearchPort`, `CachePort`, and `RateLimitPort` in this file.
#
# The `system` and `user` parameters are keyword-only (the `*`)
# so the call site reads `llm.complete(system=..., user=...)` —
# the LLM API has exactly two message roles, and the order is
# semantically meaningful (system first, user second). A
# positional call would obscure that.
#
# The return type is `str` — the raw `choices[0].message.content`
# from the OpenAI-compatible response. The use case (T-013) feeds
# this string into the defensive parser (T-008); the parser
# tolerates markdown fences, trailing prose, and other model quirks.
# ---------------------------------------------------------------------------


class LLMClientPort(Protocol):
    """An LLM provider. Implementations live in `infrastructure/llm/`.

    Spec: REQ-LLM-001 — the use case depends on this Protocol; the
    concrete client is injected at composition-root time. A
    `FakeLLMClient` with the right method signature satisfies the
    Protocol structurally (mypy --strict enforces this at
    type-check time).
    """

    async def complete(self, *, system: str, user: str) -> str:
        """Complete a chat-completion request with a system + user message pair.

        Args:
            system: The system prompt (Spanish intent-filter rules,
                per REQ-LLM-004). Pre-built by the caller.
            user: The user message (typically a JSON-serialized
                intent + jobs list, per `_prompt.build_user_message`).

        Returns:
            The raw assistant message content as a string. May
            include markdown fences, trailing prose, or other
            model quirks — the defensive parser
            (`infrastructure.llm._parser.parse_llm_response`) is
            designed to handle them.

        Raises:
            LLMUnavailableError: on 5xx, timeout, 429, or MiniMax
                error codes 1002/1013 (after retry exhaustion) and
                1004/1008/1001 (no retry).
            LLMResponseParseError: NOT raised here — the parser
                raises it when the returned content cannot be
                extracted as a JSON object.
        """
        ...


# ---------------------------------------------------------------------------
# Intent extractor (REQ-CHAT-INT-001, REQ-CHAT-INT-004,
# `chat-filter-2stage` change T-008)
#
# `IntentExtractorPort` is the application layer's seam for "any
# stage-1 intent extractor". The concrete implementation lives in
# `infrastructure/llm/_intent.py` (the `IntentExtractor` class
# added in T-005 of PR1). The use case (T-008 of PR2) depends
# on the Protocol only, never on the concrete class.
#
# The Protocol is NOT `@runtime_checkable` (mirrors the
# `LLMClientPort` pattern in this file). Structural conformance
# is enforced at mypy --strict time. The `FakeIntentExtractor`
# in `tests/conftest.py` (PR1's T-006) is structurally
# compatible — its `async def extract(*, message: str) -> Intent`
# method matches the Protocol's signature exactly.
#
# The `*` keyword-only marker on `message` is intentional: the
# stage-1 extraction takes a single argument and the call site
# reads `extractor.extract(message=...)`. Keyword-only forces
# the caller to be explicit about what they're passing.
# ---------------------------------------------------------------------------


class IntentExtractorPort(Protocol):
    """A stage-1 intent extractor. Implementations live in `infrastructure/llm/`.

    Spec: REQ-CHAT-INT-001 — the use case (`FilterJobsByIntentUseCase`,
    PR2's T-008) depends on this Protocol; the concrete
    `IntentExtractor` is injected at composition-root time
    (PR2's T-009 in `app_factory.build_app()`). A
    `FakeIntentExtractor` (PR1's T-006, in `tests/conftest.py`)
    with the right method signature satisfies the Protocol
    structurally (mypy --strict enforces this at type-check
    time).
    """

    async def extract(self, *, message: str) -> Intent:
        """Extract a structured `Intent` from a free-form user message.

        Args:
            message: The user's message (pre-NFC-normalized by
                the route). May be empty or whitespace-only
                (the implementation short-circuits to
                `Intent(confidence=0.0)` in that case — no LLM
                call).

        Returns:
            The parsed `Intent` (7 typed fields per
            REQ-CHAT-INT-001). The use case reads `confidence`
            to decide between 2-stage (high-confidence) and
            v1 fallback (low-confidence, per REQ-CHAT-INT-004).

        Raises:
            LLMResponseParseError: on parse failure after retry
                exhaustion. The use case catches this and falls
                back to v1 (REQ-CHAT-INT-004).
            LLMUnavailableError: when the LLM provider is down
                (NOT caught here — propagates to the route
                which maps to HTTP 502).
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
