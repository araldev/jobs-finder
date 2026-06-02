"""`GET /jobs/indeed` route.

Spec: REQ-I-012, REQ-I-013, REQ-I-017. The route:
  1. Validates the query via the Pydantic `IndeedJobsQuery` schema.
  2. Resolves the use case from `request.app.state.indeed_use_case`
     (set by `app_factory.build_app`).
  3. Maps the validated query to a `SearchIndeedInput` dataclass.
  4. Calls the use case and maps the returned `list[Job]` to an
     `IndeedJobsResponse`.

The route is async, has zero `JobSearchPort`-shaped knowledge (it only
sees the use case), and lets the framework handle 422 (validation) and
the registered handler handle 502 (port failure).

The `SearchJobsUseCase` import is from the SOURCE-NEUTRAL module
`application/usecases/search_indeed_jobs.py`. The class was renamed
from the original `SearchIndeedJobsUseCase` to satisfy REQ-I-005
(the use case file MUST NOT contain the string "indeed"). The file
path provides the per-source binding for FastAPI dependency
injection; the class itself is source-agnostic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from jobs_finder.application.dto import SearchIndeedInput
from jobs_finder.application.usecases.search_indeed_jobs import SearchJobsUseCase
from jobs_finder.presentation.schemas import (
    IndeedJobsQuery,
    IndeedJobsResponse,
    to_response,
)

router = APIRouter()


def get_indeed_use_case(request: Request) -> SearchJobsUseCase:
    """Resolve the Indeed use case from `app.state.indeed_use_case`.

    `app_factory.build_app` is responsible for setting it. Tests build the
    app with `build_app(indeed_use_case=...)` so this dependency is always
    wired. Mirrors the LinkedIn `get_use_case` dependency in
    `presentation/routes/linkedin.py`.
    """
    use_case = getattr(request.app.state, "indeed_use_case", None)
    if use_case is None:
        raise RuntimeError(
            "app.state.indeed_use_case is not set; build the app via "
            "`build_app(indeed_use_case=...)` so the Indeed use case is wired."
        )
    return use_case  # type: ignore[no-any-return]


@router.get("/jobs/indeed", response_model=IndeedJobsResponse)
async def search_indeed(
    query: Annotated[IndeedJobsQuery, Query()],
    use_case: Annotated[SearchJobsUseCase, Depends(get_indeed_use_case)],
) -> IndeedJobsResponse:
    """Search Indeed for jobs matching the validated query."""
    jobs = await use_case.execute(
        SearchIndeedInput(
            keywords=query.keywords,
            location=query.location,
            limit=query.limit,
        )
    )
    return IndeedJobsResponse(jobs=[to_response(job) for job in jobs])
