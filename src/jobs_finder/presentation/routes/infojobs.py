"""`GET /jobs/infojobs` route.

Spec: REQ-J-005, REQ-J-006, REQ-C-003. The route:
  1. Validates the query via the Pydantic `InfoJobsJobsQuery` schema.
  2. Resolves the use case from `request.app.state.infojobs_use_case`
     (set by `app_factory.build_app`).
  3. Calls the use case's `search(...)` method (the cached wrapper
     interface) which returns a `SearchResult(jobs, cache_status)`.
  4. Sets the `X-Cache: HIT|MISS` response header from
     `result.cache_status.value` (REQ-C-003).
  5. Maps the `result.jobs` to an `InfoJobsJobsResponse`.

The route is async, has zero `JobSearchPort`-shaped knowledge (it only
sees the cached wrapper), and lets the framework handle 422
(validation) and the registered handler handle 502 (port failure).

The `SearchJobsUseCase` import is from the SOURCE-NEUTRAL module
`application/usecases/search_infojobs_jobs.py`. The class was named
generically (not `SearchInfoJobsJobsUseCase`) to satisfy REQ-J-004
(the use case file MUST NOT contain the string "infojobs"). The file
path provides the per-source binding for FastAPI dependency
injection; the class itself is source-agnostic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.presentation.schemas import (
    InfoJobsJobsQuery,
    InfoJobsJobsResponse,
    to_response,
)

router = APIRouter()


def get_infojobs_use_case(request: Request) -> CachedJobSearchUseCase:
    """Resolve the InfoJobs use case from `app.state.infojobs_use_case`.

    `app_factory.build_app` is responsible for setting it. Tests build the
    app with `build_app(infojobs_use_case=...)` so this dependency is always
    wired. Mirrors the `get_indeed_use_case` dependency in
    `presentation/routes/indeed.py`. The dependency type is
    `CachedJobSearchUseCase` (the public InfoJobs use case after the
    `cache-ttl` change).
    """
    use_case = getattr(request.app.state, "infojobs_use_case", None)
    if use_case is None:
        raise RuntimeError(
            "app.state.infojobs_use_case is not set; build the app via "
            "`build_app(infojobs_use_case=...)` so the InfoJobs use case is wired."
        )
    return use_case  # type: ignore[no-any-return]


@router.get("/jobs/infojobs", response_model=InfoJobsJobsResponse)
async def search_infojobs(
    query: Annotated[InfoJobsJobsQuery, Query()],
    use_case: Annotated[CachedJobSearchUseCase, Depends(get_infojobs_use_case)],
    response: Response,
) -> InfoJobsJobsResponse:
    """Search InfoJobs for jobs matching the validated query.

    Sets the `X-Cache: HIT|MISS` response header from the use case's
    `SearchResult.cache_status` (REQ-C-003).
    """
    result = await use_case.search(
        keywords=query.keywords,
        location=query.location,
        limit=query.limit,
    )
    response.headers["X-Cache"] = result.cache_status.value
    return InfoJobsJobsResponse(jobs=[to_response(job) for job in result.jobs])
