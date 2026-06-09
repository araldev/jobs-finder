"""`GET /jobs/linkedin` route.

Spec: REQ-017..REQ-020, REQ-022, REQ-C-003 (X-Cache header). The route:
  1. Validates the query via the Pydantic `LinkedInJobsQuery` schema.
  2. Resolves the use case from `request.app.state.use_case` (set by
     `app_factory.build_app`).
  3. Calls the use case's `search(...)` method (the cached wrapper
     interface) which returns a `SearchResult(jobs, cache_status)`.
  4. Sets the `X-Cache: HIT|MISS` response header from
     `result.cache_status.value` (REQ-C-003).
  5. Maps the `result.jobs` to a `LinkedInJobsResponse`.

The route is async, has zero `JobSearchPort`-shaped knowledge (it only
sees the cached wrapper), and lets the framework handle 422
(validation) and the registered handler handle 502 (port failure).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.presentation.schemas import (
    LinkedInJobsQuery,
    LinkedInJobsResponse,
    to_response,
)

router = APIRouter()


def get_use_case(request: Request) -> CachedJobSearchUseCase:
    """Resolve the use case from `app.state.use_case`.

    `app_factory.build_app` is responsible for setting it. Tests build
    the app with `build_app(use_case=...)` so this dependency is
    always wired. The dependency type is `CachedJobSearchUseCase` (the
    public LinkedIn use case after the `cache-ttl` change); the raw
    use case is composed inside the cached wrapper by the composition
    root.
    """
    use_case = getattr(request.app.state, "use_case", None)
    if use_case is None:
        raise RuntimeError(
            "app.state.use_case is not set; build the app via "
            "`build_app(use_case=...)` so the use case is wired."
        )
    return use_case  # type: ignore[no-any-return]


@router.get("/jobs/linkedin", response_model=LinkedInJobsResponse)
async def search_linkedin(
    query: Annotated[LinkedInJobsQuery, Query()],
    use_case: Annotated[CachedJobSearchUseCase, Depends(get_use_case)],
    response: Response,
) -> LinkedInJobsResponse:
    """Search LinkedIn for jobs matching the validated query.

    Sets the `X-Cache: HIT|MISS` response header from the use case's
    `SearchResult.cache_status` (REQ-C-003). The header is set BEFORE
    the response body is serialized so it is always present, even on
    a 200 success.
    """
    result = await use_case.search(
        keywords=query.keywords,
        location=query.location,
        limit=query.limit,
    )
    response.headers["X-Cache"] = result.cache_status.value
    return LinkedInJobsResponse(jobs=[to_response(job) for job in result.jobs])
