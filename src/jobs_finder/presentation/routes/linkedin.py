"""`GET /jobs/linkedin` route.

Spec: REQ-017..REQ-020, REQ-022. The route:
  1. Validates the query via the Pydantic `LinkedInJobsQuery` schema.
  2. Resolves the use case from `request.app.state.use_case` (set by
     `app_factory.build_app`).
  3. Maps the validated query to a `SearchLinkedInInput` dataclass.
  4. Calls the use case and maps the returned `list[Job]` to a
     `LinkedInJobsResponse`.

The route is async, has zero `JobSearchPort`-shaped knowledge (it only
sees the use case), and lets the framework handle 422 (validation) and
the registered handler handle 502 (port failure).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from jobs_finder.application.dto import SearchLinkedInInput
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.presentation.schemas import (
    LinkedInJobsQuery,
    LinkedInJobsResponse,
    to_response,
)

router = APIRouter()


def get_use_case(request: Request) -> SearchLinkedInJobsUseCase:
    """Resolve the use case from `app.state.use_case`.

    `app_factory.build_app` is responsible for setting it. Tests build the
    app with `build_app(use_case=...)` so this dependency is always wired.
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
    use_case: Annotated[SearchLinkedInJobsUseCase, Depends(get_use_case)],
) -> LinkedInJobsResponse:
    """Search LinkedIn for jobs matching the validated query."""
    jobs = await use_case.execute(
        SearchLinkedInInput(
            keywords=query.keywords,
            location=query.location,
            limit=query.limit,
        )
    )
    return LinkedInJobsResponse(jobs=[to_response(job) for job in jobs])
