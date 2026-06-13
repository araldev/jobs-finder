"""`GET /jobs/history` route.

Spec: REQ-HIST-002. Exposes the historical job query endpoint with
pagination and filtering by source, keywords, and date range. Gracefully
degrades when the repository is unavailable (no DB_PATH configured).

The route reads the repository from `app.state.job_repository` (set by
`app_factory.build_app` during the lifespan startup). When the repository
is `None`, returns an empty result set (no crash).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import HttpUrl

from jobs_finder.presentation.schemas import (
    HistoricalJobResponse,
    JobsHistoryQuery,
    JobsHistoryResponse,
)

router = APIRouter(tags=["jobs"])


@router.get("/jobs/history")
async def jobs_history(
    query: Annotated[JobsHistoryQuery, Query()],
    request: Request,
) -> JobsHistoryResponse:
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
    """
    repo = getattr(request.app.state, "job_repository", None)
    if repo is None:
        return JobsHistoryResponse(items=[], total=0, limit=query.limit, offset=query.offset)

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
    return JobsHistoryResponse(items=items, total=total, limit=query.limit, offset=query.offset)


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
