"""Pydantic schemas at the API edge.

Spec: REQ-009, REQ-017, REQ-I-012, REQ-I-013.
Pydantic lives ONLY at this boundary; the application layer uses plain
dataclasses (`SearchLinkedInInput`, `SearchIndeedInput`). The route
handler is the only place where Pydantic models are constructed from
raw user input and where domain objects (`Job`) are mapped back into
API responses (`JobResponse`).
"""

from __future__ import annotations

from datetime import datetime

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


class JobResponse(BaseModel):
    """One job in the API response.

    Spec: REQ-017, REQ-I-012. Exactly the six documented fields, no
    more, no less. `posted_at` is nullable at the API contract boundary;
    the `Job` domain object currently requires it, so the conversion is
    one-way.
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


def to_response(job: Job) -> JobResponse:
    """Convert a `Job` value object into a `JobResponse` for the API.

    `Job.posted_at` is currently a required `datetime`; the API contract
    types it as `datetime | None`. A non-None `datetime` is a valid
    `datetime | None`, so the conversion is loss-free. Shared by both
    the LinkedIn and Indeed route handlers — a future refactor can
    colocate this helper if the duplication bothers.
    """
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        url=HttpUrl(job.url),
        posted_at=job.posted_at,
    )
