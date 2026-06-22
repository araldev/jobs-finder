"""`GET /jobs/history` route.

Spec: REQ-HIST-002, REQ-CACHEUX-002. Exposes the historical job
query endpoint with pagination and filtering by source, keywords,
and date range. Gracefully degrades when the repository is
unavailable (no DB_PATH configured).

The route reads the repository from `app.state.job_repository`
(set by `app_factory.build_app` during the lifespan startup).
When the repository is `None`, returns an empty result set
(no crash).

REQ-CACHEUX-002: BOTH endpoints in this file set
`Cache-Control: public, max-age=60` on 200 AND 404 responses.
The header is NOT set on 500 (FastAPI's default error handler
returns no header → browser does not cache 500s). Per design OQ1,
the value is exactly `public, max-age=60` — NO `s-maxage`, NO
`stale-while-revalidate` because no CDN is deployed (those
directives are no-ops without a CDN; emitting them would be
misleading documentation).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import HttpUrl
from starlette.responses import JSONResponse

from jobs_finder.presentation.schemas import (
    HistoricalJobResponse,
    JobsHistoryQuery,
    JobsHistoryResponse,
)

router = APIRouter(tags=["jobs"])


# REQ-CACHEUX-002: exact Cache-Control value mandated by design OQ1.
# Browser-only (no CDN deployed). Negative cache on 404 is intentional
# and bounded by max-age=60s.
_CACHE_CONTROL_HEADER = "public, max-age=60"


def _cache_control_json(
    content: object,
    status_code: int = 200,
) -> JSONResponse:
    """Build a `JSONResponse` carrying the Cache-Control header.

    Centralizes the directive literal so the 200/404 paths stay
    consistent (REFACTOR opportunity per spec) and the value lives
    in exactly one place.
    """
    return JSONResponse(
        content=content,
        status_code=status_code,
        headers={"Cache-Control": _CACHE_CONTROL_HEADER},
    )


@router.get("/jobs/history")
async def jobs_history(
    query: Annotated[JobsHistoryQuery, Query()],
    request: Request,
) -> JSONResponse:
    """Return paginated job history with optional filters.

    Query parameters:
        sources: Comma-separated list of sources (default: all 3).
        keywords: Optional string to match against title or company.
        date_from: Optional ISO date for `posted_at >=` filter.
        date_to: Optional ISO date for `posted_at <=` filter.
        limit: Max results (default 50, max 200).
        offset: Pagination offset (default 0).

    Returns:
        200 with `JobsHistoryResponse` containing `items`, `total`,
        `limit`, and `offset`. An empty result set is returned when the
        repository is not available (no `DB_PATH` configured).

    Side effect:
        Response carries `Cache-Control: public, max-age=60`
        (REQ-CACHEUX-002).
    """
    repo = getattr(request.app.state, "job_repository", None)
    if repo is None:
        return _cache_control_json(
            JobsHistoryResponse(
                items=[], total=0, limit=query.limit, offset=query.offset
            ).model_dump(mode="json"),
            status_code=200,
        )

    # Parse comma-separated sources into list (or None for all)
    source_list: list[str] | None = [
        s.strip() for s in query.sources.split(",") if s.strip()
    ] or None

    jobs = await repo.search_jobs_history(
        sources=source_list,
        keywords=query.keywords,
        location=query.location,
        description=query.description,
        date_from=query.date_from,
        date_to=query.date_to,
        limit=query.limit,
        offset=query.offset,
    )
    total = await repo.count_jobs(
        sources=source_list,
        keywords=query.keywords,
        location=query.location,
        description=query.description,
        date_from=query.date_from,
        date_to=query.date_to,
    )

    items = [_to_history_response(job) for job in jobs]
    body = JobsHistoryResponse(items=items, total=total, limit=query.limit, offset=query.offset)
    return _cache_control_json(body.model_dump(mode="json"), status_code=200)


@router.get("/jobs/history/by-id/{source_id}")
async def jobs_history_by_id(
    source_id: str,
    request: Request,
) -> JSONResponse:
    """Return a single job by its source_id.

    This is a direct lookup endpoint (not paginated) used by the
    frontend to resolve job detail pages. Returns 404 if the job
    is not found.

    Both 200 AND 404 responses carry `Cache-Control: public, max-age=60`
    (REQ-CACHEUX-002 — negative cache on 404 is bounded by 60s).
    The 404 case returns a JSON body matching FastAPI's default
    `{"detail": "..."}` shape with the Cache-Control header attached
    via `headers=` on the JSONResponse.
    """
    repo = getattr(request.app.state, "job_repository", None)
    if repo is None:
        return _cache_control_json(
            {"detail": "Job not found"},
            status_code=404,
        )

    job = await repo.get_job_by_source_id(source_id)
    if job is None:
        return _cache_control_json(
            {"detail": "Job not found"},
            status_code=404,
        )

    return _cache_control_json(
        _to_history_response(job).model_dump(mode="json"),
        status_code=200,
    )


def _to_history_response(job: object) -> HistoricalJobResponse:
    """Convert a search result to `HistoricalJobResponse`.

    The extra DB metadata fields (`source`, `first_seen_at`,
    `last_seen_at`, `query_snapshot`) are populated from the
    `HistoryJobRow` dataclass when available, or default to `None`
    for backward compat with `Job` domain objects.
    """
    # Check if this is a HistoryJobRow or HistoryJobRow-shaped object
    source: str | None = getattr(job, "source", None)
    first_seen_at: str | None = getattr(job, "first_seen_at", None)
    last_seen_at: str | None = getattr(job, "last_seen_at", None)
    query_snapshot: str | None = getattr(job, "query_snapshot", None)

    return HistoricalJobResponse(
        id=str(getattr(job, "id", "")),
        source=source,
        title=str(getattr(job, "title", "")),
        company=str(getattr(job, "company", "")),
        location=str(getattr(job, "location", "")),
        url=HttpUrl(str(getattr(job, "url", ""))),
        description=getattr(job, "description", None),
        posted_at=getattr(job, "posted_at", None),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        query_snapshot=query_snapshot,
    )
