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

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, NamedTuple, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from jobs_finder.domain.job import Job

K_co = TypeVar("K_co", contravariant=True)  # noqa: PLC0105
V = TypeVar("V")


class JobSearchPort(Protocol):
    """A job-search source. Implementations live in `infrastructure/`.

    The default value on `limit` is duplicated in the Pydantic schema at the
    presentation boundary; the application trusts the caller to pass an
    already-validated value.

    The 4th `geo_id: int | None = None` kwarg (added in
    `fix-linkedin-geoid` change, REQ-LOC-GEO-001) is the
    LinkedIn-specific numeric `geoId` the resolver returned
    for `location`. The aggregator forwards the kwarg ONLY
    to the LinkedIn port (per `SearchAllSourcesUseCase.search`
    dispatch); Indeed + InfoJobs port implementations ignore
    it. The default `None` preserves backward compat for
    callers that pre-date the change — the existing
    `JobSearchPort` consumers (the per-source use cases, the
    `CachedJobSearchUseCase` wrapper) keep working without
    any signature changes at their call site.
    """

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
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

    The 5th `geo_id: int | None = None` field (added in
    `fix-linkedin-geoid`) is the LinkedIn-specific `geoId=`
    value (a `int`) the resolver returned for `location`. A
    query with `location="Madrid", geo_id=103374081` (resolved)
    is byte-distinct from `location="Madrid", geo_id=None` (not
    resolved) — they return different jobs, so a cache HIT on
    one would silently corrupt the other. The field is `None`
    for the other 2 sources (Indeed + InfoJobs accept
    `location=` strings; they don't need a `geoId=`).

    The 6th `query_tokens: tuple[str, ...] = ()` field (added
    in `backend-scraper-query-tuning`, REQ-CACHE-001) is the
    normalized query tokens used by the InfoJobs filter and
    the opt-in `keyword_score` sort. The default `()`
    preserves backward compat: a v1 caller that constructs
    the key with 5 positional args gets a key with
    `query_tokens=()`. A pre-WU2 query with `query_tokens=()`
    is byte-distinct from the same query with
    `query_tokens=("react",)` (different cache entries,
    different jobs). The `query_tokens` value is NORMALIZED
    (lowercased, sorted, deduped) at the cache-wrapper
    boundary so a `set` passed by the caller becomes a
    canonical `tuple`.

    Tuple equality and hashing are exact for `NamedTuple`, so
    there is no key collision risk.
    """

    source: str
    keywords: str
    location: str
    limit: int
    geo_id: int | None = None
    query_tokens: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Location resolver (REQ-LOC-GEO-001, `fix-linkedin-geoid` change)
#
# `LocationResolverPort` is the application layer's seam for "any
# location-to-geoId translator". The concrete implementation
# `HardcodedLocationResolver` lives in
# `infrastructure/location/hardcoded_resolver.py` (a 34-entry
# hardcoded dict sourced from `tests/fixtures/linkedin_geo_ids.csv`).
# The use case (`FilterJobsByIntentUseCase._execute_2stage`) depends
# on the Protocol only, never on the concrete class.
#
# The Protocol is NOT `@runtime_checkable` (mirrors the
# `JobSearchPort`, `LLMClientPort`, and `IntentExtractorPort`
# patterns in this file). Structural conformance is enforced at
# mypy --strict time. A `FakeLocationResolver` (test double) with
# the right `def resolve(self, location: str) -> int | None` method
# satisfies the Protocol structurally.
#
# The single method `resolve(location)` is intentionally NOT
# `async` — the resolver is a pure in-process dict lookup with
# no I/O. The use case calls it directly without `await`; the
# 2-stage path's "stage 2" still makes ONE real network call
# (the aggregator scrape), but the resolver adds zero latency.
#
# The return type is `int | None`:
#   - `int`: a captured LinkedIn `geoId` (e.g. `103374081`).
#   - `None`: the input could not be resolved (unknown / country-
#     level / País Vasco / Canarias / empty). The use case logs
#     a WARNING and proceeds with `geo_id=None`; the LinkedIn
#     scraper falls back to the (broken) `?location=<str>` path
#     — a strict improvement over today's 100%-broken behavior.
# ---------------------------------------------------------------------------


class LocationResolverPort(Protocol):
    """A location-to-geoId translator. Implementations live in `infrastructure/location/`.

    Spec: REQ-LOC-GEO-001 — the use case
    (`FilterJobsByIntentUseCase._execute_2stage`) depends on
    this Protocol; the concrete `HardcodedLocationResolver`
    is injected at composition-root time (`app_factory.build_app`).
    A `FakeLocationResolver` with the right method signature
    satisfies the Protocol structurally (mypy --strict
    enforces this at type-check time).

    The v1 implementation is a pure in-process dict lookup; a
    future `HybridLocationResolver` (a follow-up change) will
    add a geocoding API fallback for inputs the hardcoded dict
    cannot resolve. The Protocol is the seam; the future change
    is local to `infrastructure/location/`.
    """

    def resolve(self, location: str) -> int | None:
        """Translate a free-form `location` string into a LinkedIn `geoId`.

        Args:
            location: The free-form location string (e.g.
                `"Madrid"`, `"Cataluña"`, `"cdmx"`). May be
                empty (the v1 chat-filter path passes
                `location=""`); an empty string short-circuits
                to `None` without a WARNING log (the canonical
                "no location specified" sentinel).

        Returns:
            The LinkedIn `geoId` (a `int`) on a successful
            match, OR `None` on a miss (unknown / country-
            level / País Vasco / Canarias / empty). A WARNING
            is logged on every miss except the empty-string
            path (the WARNING is observable for ops to spot
            stale geographic intent and re-run the capture
            script).
        """

    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
        """Translate a free-form `location` string into an InfoJobs `(province_id, country_id)`.

        Spec: REQ-PROV-001 (the 12 scenarios).

        The InfoJobs scraper consumes the tuple to build the
        `?provinceIds=<id>&countryIds=<id>` query params that
        narrow the SERP to the user's region. The tuple
        semantics:

            - `(province_id, country_id)` — both `int`,
              both required for the canonical "specific
              city" case (e.g. Málaga → `(34, 17)`).
            - `(None, country_id)` — country-only; the
              scraper emits `?countryIds=17` only
              (no `provinceIds`). This is the canonical
              "Remote" / "España" / "teletrabajo" sentinel.
            - `(province_id, None)` — reserved for
              future "province without country" cases
              (not used in v1; the InfoJobs dict always
              carries the country).
            - `(None, None)` — the unmapped / empty
              sentinel; the scraper omits BOTH
              `provinceIds` AND `countryIds` and falls
              back to the v1 `?l=<str>` path. A WARNING
              is logged on the `(None, None)` miss
              (EXCEPT the empty-string path, which is
              silent — same as `resolve()`).

        Args:
            location: The free-form location string (e.g.
                `"Málaga"`, `"Madrid"`, `"Remote"`,
                `"teletrabajo"`). May be empty (the
                aggregator passes `""`); an empty string
                short-circuits to `(None, None)` WITHOUT
                a WARNING log (the canonical "no location
                specified" sentinel).

        Returns:
            A `(province_id, country_id)` tuple. The
            4-tuple shape is the full domain; the scraper
            tests every combination. On a miss (unmapped
            city, country-level, empty), returns
            `(None, None)` — the InfoJobs scraper then
            falls back to the v1 `?l=<str>` URL formula
            (graceful degradation, no 500).
        """

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:
        """Translate `location` into a `(city, province, country)` triplet.

        Spec: `backend-linkedin-location-fallback`
        REQ-STR-LOC-001. This is the structured-location
        counterpart to `resolve()`: for cities that have a
        captured `geoId`, `resolve()` returns the int; for
        cities that are NOT in the geoId dict but ARE in the
        structured triplet dict (10 cities in
        `_STRUCTURED_MAPPING`), `resolve_structured()` returns
        the triplet. The LinkedIn scraper uses the triplet
        in `?location=<city>,<province>,<country>` (URL-
        encoded) — LinkedIn's fuzzy match handles the
        structured form better than the raw string.

        The two methods are independent: a city can have one,
        both, or neither mapping. The consumer (the LinkedIn
        scraper) decides the priority; the resolver exposes
        both shapes.

        Args:
            location: The free-form location string (e.g.
                `"Antequera"`, `"Cadiz"`). May be empty (the
                v1 chat-filter path passes `location=""`);
                an empty string short-circuits to `None`
                without any log (same as `resolve()`).

        Returns:
            A 3-tuple `(city, province, country)` in Title
            Case with tildes (NFC) on a successful match, OR
            `None` on a miss (unknown / country-level /
            CCAA-level / empty). No WARNING log is emitted
            on miss (the structured semantic is different
            from `resolve()`: it's an OPT-IN alternative
            URL shape, not a fallback for the geoId path).
        """


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
# Job repository (background-scheduler-persistence change)
#
# `JobRepositoryPort` is the application layer's seam for "any
# persistent job storage". The infrastructure layer
# (`infrastructure/persistence/sqlite_job_repository.py`)
# implements it; the background scheduler depends on the
# Protocol only, never on the concrete class.
#
# The Protocol is NOT `@runtime_checkable` (mirrors the
# `JobSearchPort`, `CachePort`, and `RateLimitPort` patterns
# in this file). Structural conformance is enforced at
# mypy --strict time. A fake repository with the right method
# signatures satisfies the Protocol structurally.
# ---------------------------------------------------------------------------


class JobRepositoryPort(Protocol):
    """Persistent job storage. No @runtime_checkable — structural only.

    Spec: REQ-DB-001 (MODIFIED). Five async methods: upsert_jobs,
    search_jobs, delete_older_than, search_jobs_history, count_jobs,
    close (idempotent). Structural subtyping only.
    """

    async def upsert_jobs(
        self,
        jobs: list[Job],
        query_snapshot: dict[str, str],
    ) -> int:
        """Upsert via ON CONFLICT(source, source_id) DO UPDATE. Returns row count."""
        ...

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """SELECT with optional WHERE filters on keywords and source."""
        ...

    async def delete_older_than(
        self,
        *,
        days: int,
        limit: int = 1000,
    ) -> int:
        """Delete rows with `last_seen_at` older than `days`. Returns deleted count.

        Args:
            days: Delete rows where `last_seen_at < now - days`.
            limit: Maximum rows to delete (default 1000).

        Returns:
            The number of deleted rows.
        """
        ...

    async def search_jobs_history(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        location: str | None = None,
        description: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """Search job history with optional filters: source, keyword, location, description, date range.

        Args:
            sources: Optional list of source names to filter by.
            keywords: Optional string to match against title or company.
            location: Optional string to match against location field.
            description: Optional string to match against description field.
            date_from: Optional ISO date string (inclusive) for `posted_at >=`.
            date_to: Optional ISO date string (inclusive) for `posted_at <=`.
            limit: Max results to return (default 50).
            offset: Number of results to skip for pagination.

        Returns:
            Matching `Job` domain objects ordered by `posted_at DESC`.
        """
        ...

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """Count jobs matching the given filters.

        Args:
            sources: Optional list of source names to filter by.
            keywords: Optional string to match against title or company.
            date_from: Optional ISO date string (inclusive) for `posted_at >=`.
            date_to: Optional ISO date string (inclusive) for `posted_at <=`.

        Returns:
            The count of matching rows.
        """
        ...

    async def get_job_by_source_id(self, source_id: str) -> Job | None:
        """Return a single job by its source_id, or None if not found.

        The ``source_id`` is the job ID as it appears in API responses
        (e.g. ``"4428834914"``).  This is NOT the auto-increment
        integer primary key.
        """
        ...

    async def close(self) -> None:
        """Close the DB connection. Idempotent."""
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

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        """Stream-complete a chat-completion request, yielding one string per token.

        Spec: `chat-streaming` REQ-LLM-001 (streaming). The
        streaming counterpart of `complete(...)`: the caller
        iterates the returned async iterator and receives one
        `str` per LLM token (verbatim `choices[0].delta.content`
        from the OpenAI-compatible stream).

        The v1 chat endpoint (POST /jobs/chat) continues to
        use `complete(...)` — `stream_complete` is the seam
        for the new POST /jobs/chat/stream endpoint. The two
        methods are NOT mutually exclusive: the concrete
        `MiniMaxLLMClient` implements BOTH, and the use
        case's `stream_execute` (added in T-006) is the
        only application-layer caller of `stream_complete`.

        Args:
            system: The system prompt (same as `complete`).
            user: The user message (same as `complete`).

        Yields:
            One `str` per LLM token. Empty `delta.content`
            values are SKIPPED (the implementation MUST NOT
            yield empty strings — the consumer would push a
            useless `event: text\\ndata: {"delta": ""}\\n\\n`
            to the SSE stream).

        Raises:
            LLMStreamError: on non-200 status, malformed SSE,
                or protocol drift. Raised from the client
                implementation (e.g. `MiniMaxLLMClient.
                stream_complete`).
            LLMRequestTimeoutError: on `httpx.TimeoutException`
                mid-stream. NO retry — the upstream request
                is allowed to complete in the background.
            LLMUnavailableError: NOT raised here directly
                (the parent class is a fallback for code
                paths that haven't migrated to the
                streaming-specific subclasses).
        """
        yield ""  # pragma: no cover — Protocol stub


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


class LinkedInAuthCookiePort(Protocol):
    """Returns the operator's `li_at` session cookie (masked), or `None`.

    Spec: REQ-LA-COOKIE-001 (Protocol shape). The single sync method
    `cookie()` returns a `pydantic.SecretStr` for log-masking
    (REQ-LA-COOKIE-003) or `None` when the operator has not
    configured a cookie (REQ-LA-COOKIE-002 — soft mode, preserves
    v1 zero-config boot). The Protocol is intentionally minimal:
    no set/refresh/clear, no async — the value is loaded from
    `Settings` at process start and never mutates.

    Mirrors the v1 `LocationResolverPort` precedent: a sync, single-
    method, structural Protocol with no `@runtime_checkable`. The
    application layer declares the contract; the infrastructure
    layer (`EnvLinkedInAuthCookieAdapter`) and the test layer
    (`FakeLinkedInAuthCookiePort`) both satisfy it structurally
    so the scraper can be unit-tested with no `Settings` ctor and
    no env-var mutation.
    """

    def cookie(self) -> SecretStr | None: ...


class LinkedInAuthCookiesPort(Protocol):
    """Returns the operator's N LinkedIn cookies (masked), or `None`.

    Spec: REQ-LST-COOKIE-001 (Protocol shape). The single sync
    method `cookies()` returns a `list[tuple[str, SecretStr]]` of
    `(cookie_name, masked_value)` pairs in the canonical
    LinkedIn-session order (`li_at → JSESSIONID → bcookie → li_gc`),
    or `None` when ALL cookies are unset (REQ-LST-COOKIE-002 — the
    soft-mode sentinel; preserves v1 zero-config boot). The
    Protocol is intentionally minimal: no set/refresh/clear, no
    async — the values are loaded from `Settings` at process
    start and never mutate.

    Plural successor to the v1 singular `LinkedInAuthCookiePort`
    (kept for backward compat; the v1 adapter is byte-identical and
    the 35 v1 tests still construct it directly). The v1 adapter
    satisfies the singular Protocol but NOT this plural Protocol
    (it has `cookie()`, not `cookies()`); the production wire in
    `app_factory.build_app()` now uses the plural
    `MultiEnvLinkedInAuthCookiesAdapter` (4 fields) and the v1
    `auth_cookie=None` slot is preserved explicitly so the v1
    integration tests stay green.

    Mirrors the v1 `LinkedInAuthCookiePort` precedent: a sync,
    single-method, structural Protocol with no
    `@runtime_checkable`. The application layer declares the
    contract; the infrastructure layer
    (`MultiEnvLinkedInAuthCookiesAdapter`) and the test layer
    (`FakeLinkedInAuthCookiesPort`) both satisfy it
    structurally so the scraper can be unit-tested with no
    `Settings` ctor and no env-var mutation.
    """

    def cookies(self) -> list[tuple[str, SecretStr]] | None: ...
