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

    Spec: REQ-017, REQ-I-012, REQ-J-005. Exactly the six documented
    fields, no more, no less. `posted_at` is nullable at the API
    contract boundary; the `Job` domain object currently requires it,
    so the conversion is one-way.
    """

    id: str
    title: str
    company: str
    location: str
    url: HttpUrl
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
    three route handlers (LinkedIn + Indeed + InfoJobs) — a future
    refactor can colocate this helper if the duplication bothers.
    """
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        url=HttpUrl(job.url),
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
    """

    id: str
    title: str
    company: str
    location: str
    url: HttpUrl
    posted_at: datetime | None = None
    sources: list[_SourceName]


class AggregatedJobsResponse(BaseModel):
    """`GET /jobs` response shape.

    Spec: REQ-A-001. The body is `{"jobs": [...]}`, never a bare
    list, so the contract is extensible (clients can ignore
    unknown top-level keys added in future changes).
    """

    jobs: list[AggregatedJobResponse]
