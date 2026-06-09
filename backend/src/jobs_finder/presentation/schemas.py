"""Pydantic schemas at the API edge.

Spec: REQ-009, REQ-017, REQ-I-012, REQ-I-013, REQ-J-001..REQ-J-006,
REQ-A-001..REQ-A-006.
Pydantic lives ONLY at this boundary; the application layer uses plain
dataclasses (`SearchLinkedInInput`, `SearchIndeedInput`,
`SearchInfoJobsInput`). The route handler is the only place where
Pydantic models are constructed from raw user input and where domain
objects (`Job`) are mapped back into API responses (`JobResponse`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from jobs_finder.domain.job import Job


class LinkedInJobsQuery(BaseModel):
    """Validated query parameters for `GET /jobs/linkedin`.

    Spec: REQ-009, REQ-017. The default `limit=20` lives ONLY here — the
    application's `SearchLinkedInInput` does not redefine it (it accepts
    the validated value the route forwards).
    """

    keywords: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)


class IndeedJobsQuery(BaseModel):
    """Validated query parameters for `GET /jobs/indeed`.

    Spec: REQ-I-012, REQ-I-013. The default `limit=20` lives ONLY here
    — the application's `SearchIndeedInput` does not redefine it. The
    field set is identical to `LinkedInJobsQuery`; the per-source
    wrapper is intentional (REQ-I-012) so the source name is part of
    the API contract and a future refactor can consolidate.
    """

    keywords: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)


class InfoJobsJobsQuery(BaseModel):
    """Validated query parameters for `GET /jobs/infojobs`.

    Spec: REQ-J-005, REQ-J-006. The field set is identical to the
    LinkedIn / Indeed query schemas; the per-source wrapper is
    intentional so the source name is part of the API contract and
    a future refactor can consolidate. The default `limit=20` lives
    ONLY here — the application's `SearchInfoJobsInput` does not
    redefine it.
    """

    keywords: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)


class JobResponse(BaseModel):
    """One job in the API response.

    Spec: REQ-017, REQ-I-012, REQ-J-005. Six documented fields
    plus an OPTIONAL `description: str | None` (added in the
    `ai-chat-filter` change so the chat endpoint can return the
    description the LLM filtered on). `posted_at` is nullable at
    the API contract boundary; the `Job` domain object currently
    requires it, so the conversion is one-way.

    The `description` field defaults to `None` so the existing
    API consumers (`/jobs`, `/jobs/linkedin`, etc.) keep working
    unchanged: pre-existing tests do NOT need to update because
    `None` is the Pydantic default. A test pins the backward-
    compat behavior in `test_chat_route.py`.
    """

    id: str
    title: str
    company: str
    location: str
    url: HttpUrl
    description: str | None = None
    posted_at: datetime | None = None


class LinkedInJobsResponse(BaseModel):
    """`GET /jobs/linkedin` response shape.

    Spec: REQ-017. The body is `{"jobs": [...]}`, never a bare list, so
    the contract is extensible (clients can ignore unknown top-level
    keys added in future changes).
    """

    jobs: list[JobResponse]


class IndeedJobsResponse(BaseModel):
    """`GET /jobs/indeed` response shape.

    Spec: REQ-I-012. Mirrors `LinkedInJobsResponse`; the wrapper is
    per-source so the source name is part of the contract. Both
    wrappers share the same source-agnostic `JobResponse` for the job
    items.
    """

    jobs: list[JobResponse]


class InfoJobsJobsResponse(BaseModel):
    """`GET /jobs/infojobs` response shape.

    Spec: REQ-J-005. Mirrors `IndeedJobsResponse` and
    `LinkedInJobsResponse`; the wrapper is per-source so the source
    name is part of the contract. All three wrappers share the same
    source-agnostic `JobResponse` for the job items — the per-source
    marker is at the QUERY (input) and RESPONSE (output wrapper)
    levels, not at the individual job item level.
    """

    jobs: list[JobResponse]


def to_response(job: Job) -> JobResponse:
    """Convert a `Job` value object into a `JobResponse` for the API.

    `Job.posted_at` is currently a required `datetime`; the API contract
    types it as `datetime | None`. A non-None `datetime` is a valid
    `datetime | None`, so the conversion is loss-free. Shared by all
    three route handlers (LinkedIn + Indeed + InfoJobs) AND the chat
    route (T-014 of `ai-chat-filter`) — a future refactor can colocate
    this helper if the duplication bothers.

    The `description` field is forwarded from `Job.description`
    (added in T-001 of `ai-chat-filter`, PR1 SUGGESTION #2). The
    `description` is `None` for sources where the parser did not
    extract one (e.g. LinkedIn until the D1 real-DOM capture lands).
    The Pydantic default is also `None`, so a `Job` with
    `description=None` round-trips to `"description": null` in
    the JSON response — the chat endpoint's LLM caller can rely
    on this to distinguish "no description parsed" from "explicitly
    empty description".
    """
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        url=HttpUrl(job.url),
        description=job.description,
        posted_at=job.posted_at,
    )


# ---------------------------------------------------------------------------
# Aggregator schemas (REQ-A-001..REQ-A-006, T-002)
#
# The aggregator is a thin composition layer over the 3 per-source routes.
# It accepts a comma-separated `sources` query parameter (default = all 3
# sources), invokes the selected cached use cases in parallel via
# `asyncio.gather`, deduplicates by `(title, company, location)`, and
# returns a single aggregated `list[AggregatedJobResponse]`. The
# `sources` field on each item names the source(s) where the job appeared
# (sorted in source-priority order: LinkedIn > Indeed > InfoJobs).
# ---------------------------------------------------------------------------


# Source names accepted by the aggregator. Used by the route to
# validate the `sources` query parameter.
AGGREGATOR_SOURCES: frozenset[str] = frozenset({"linkedin", "indeed", "infojobs"})


class AggregatedJobsQuery(BaseModel):
    """Validated query parameters for `GET /jobs`.

    Spec: REQ-A-001. The `sources` parameter is a comma-separated
    string (default `"linkedin,indeed,infojobs"`) — the route
    splits, strips, dedupes, and validates each token against
    `AGGREGATOR_SOURCES` before invoking the use case. The Pydantic
    schema intentionally only validates the `str` shape; the
    per-token validation lives in the route handler so the 422
    body shape is the route's `HTTPException` shape (not the
    Pydantic `RequestValidationError` shape).
    """

    q: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)
    sources: str = Field(
        "linkedin,indeed,infojobs",
        description=(
            "Comma-separated subset of {linkedin, indeed, infojobs}; unknown tokens return 422."
        ),
    )


# Source-name literal type used by `AggregatedJobResponse.sources`.
# Mirrors `AGGREGATOR_SOURCES` for static type checking; the
# `AGGREGATOR_SOURCES` constant is the runtime source of truth.
_SourceName = Literal["linkedin", "indeed", "infojobs"]


class AggregatedJobResponse(BaseModel):
    """One job in the aggregated response.

    Spec: REQ-A-005. Extends `JobResponse` with a `sources` field
    listing the source names where the job appeared. The
    `sources` list is sorted in source-priority order
    (LinkedIn > Indeed > InfoJobs) and is always non-empty
    (a job from 0 sources is impossible by construction).

    The `description` field is forwarded from `Job.description`
    (PR1 SUGGESTION #2). It is `None` for sources where the
    parser did not extract one. Mirrors the `JobResponse` field
    set so the chat endpoint and the `/jobs` endpoint return
    the same per-job shape (modulo `sources`).
    """

    id: str
    title: str
    company: str
    location: str
    url: HttpUrl
    description: str | None = None
    posted_at: datetime | None = None
    sources: list[_SourceName]


class AggregatedJobsResponse(BaseModel):
    """`GET /jobs` response shape.

    Spec: REQ-A-001. The body is `{"jobs": [...]}`, never a bare
    list, so the contract is extensible (clients can ignore
    unknown top-level keys added in future changes).
    """

    jobs: list[AggregatedJobResponse]


# ---------------------------------------------------------------------------
# Rate-limit response (REQ-RL-010, rate-limiting change)
#
# The 429 body shape is `{"detail": "rate limit exceeded", "request_id": "..."}` —
# the SAME shape as the existing 502 body (`UPSTREAM_UNAVAILABLE_DETAIL`),
# differing only in the `detail` string. The `request_id` correlates with the
# `X-Request-Id` response header (set by `RequestIdMiddleware`).
# ---------------------------------------------------------------------------


class RateLimitedResponse(BaseModel):
    """`429 Too Many Requests` body shape (rate-limiting middleware).

    Spec: REQ-RL-010. The body has exactly two string fields: the
    literal `"rate limit exceeded"` detail, and the request id
    (echoed from the `X-Request-Id` response header so a curl
    with the id visible can correlate the body with the headers).
    """

    detail: str
    request_id: str


# ---------------------------------------------------------------------------
# Chat filter schemas (REQ-CHAT-001, T-014 of `ai-chat-filter`)
#
# The chat endpoint accepts a single `message` field and returns
# a `ChatResponse` with the filtered jobs, the LLM's Spanish
# explanation, and the `total_considered` / `total_matched` counts.
#
# The `message` field has NO `max_length` constraint at the
# Pydantic layer — the explicit cap is enforced in the route
# handler (with a 400 + descriptive `detail`) so the rejection
# body shape is the route's `HTTPException` shape (not Pydantic's
# `RequestValidationError` shape). This mirrors the `sources`
# validation pattern in `aggregator.py:78-106`.
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """`POST /jobs/chat` body.

    Spec: REQ-CHAT-001. A single `message` field — the user's
    natural-language intent. The explicit length cap is enforced
    in the route handler (with a 400) so the rejection body
    matches the route's `HTTPException` shape.
    """

    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """`POST /jobs/chat` response.

    Spec: REQ-CHAT-001, REQ-CHAT-INT-004 (`chat-filter-2stage`).
    The body has 5 top-level fields:

      - `jobs`: the filtered `Job` instances in the aggregator's
        order. Each item is the same `JobResponse` shape used by
        `/jobs/linkedin` / `/jobs/indeed` / `/jobs/infojobs` so
        clients can reuse their per-job renderers.
      - `explanation`: the LLM's Spanish explanation (always
        present, even when the list is empty — REQ-LLM-004).
      - `total_considered`: how many jobs the LLM saw (the
        aggregator's count, before filtering).
      - `total_matched`: how many jobs made it through the filter.
      - `used_fallback`: `True` when the v1 single-stage path
        served the request (low confidence, stage-1 parse
        failure, `intent_extraction_enabled=False`, or no
        `intent_extractor` injected). `False` when the 2-stage
        path ran. Default `False` keeps the contract
        backward-compatible with the v1 `ChatResponse` (the
        field is new in the `chat-filter-2stage` change;
        pre-existing clients that ignore unknown fields are
        unaffected). The Pydantic `bool` type rejects
        non-booleans (defensive — the use case's
        `FilteredJobsResult.used_fallback` is `bool`).
    """

    jobs: list[JobResponse]
    explanation: str
    total_considered: int
    total_matched: int
    used_fallback: bool = False
