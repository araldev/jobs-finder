"""`GET /jobs/infojobs` route.

Spec: REQ-J-005, REQ-J-006. The route:
  1. Validates the query via the Pydantic `InfoJobsJobsQuery` schema.
  2. Resolves the use case from `request.app.state.infojobs_use_case`
     (set by `app_factory.build_app`).
  3. Maps the validated query to a `SearchInfoJobsInput` dataclass.
  4. Calls the use case and maps the returned `list[Job]` to an
     `InfoJobsJobsResponse`.

The route is async, has zero `JobSearchPort`-shaped knowledge (it only
sees the use case), and lets the framework handle 422 (validation) and
the registered handler handle 502 (port failure).

The `SearchJobsUseCase` import is from the SOURCE-NEUTRAL module
`application/usecases/search_infojobs_jobs.py`. The class was named
generically (not `SearchInfoJobsJobsUseCase`) to satisfy REQ-J-004
(the use case file MUST NOT contain the string "infojobs"). The file
path provides the per-source binding for FastAPI dependency
injection; the class itself is source-agnostic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from jobs_finder.application.dto import SearchInfoJobsInput
from jobs_finder.application.usecases.search_infojobs_jobs import SearchJobsUseCase
from jobs_finder.presentation.schemas import (
    InfoJobsJobsQuery,
    InfoJobsJobsResponse,
    to_response,
)

router = APIRouter()


def get_infojobs_use_case(request: Request) -> SearchJobsUseCase:
    """Resolve the InfoJobs use case from `app.state.infojobs_use_case`.

    `app_factory.build_app` is responsible for setting it. Tests build the
    app with `build_app(infojobs_use_case=...)` so this dependency is always
    wired. Mirrors the `get_indeed_use_case` dependency in
    `presentation/routes/indeed.py`.
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
    use_case: Annotated[SearchJobsUseCase, Depends(get_infojobs_use_case)],
) -> InfoJobsJobsResponse:
    """Search InfoJobs for jobs matching the validated query."""
    jobs = await use_case.execute(
        SearchInfoJobsInput(
            keywords=query.keywords,
            location=query.location,
            limit=query.limit,
        )
    )
    return InfoJobsJobsResponse(jobs=[to_response(job) for job in jobs])
