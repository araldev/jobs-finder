"""`GET /jobs` aggregator route.

Spec: REQ-A-001..REQ-A-006.

The aggregator is a thin composition layer over the 3 per-source
routes (`/jobs/linkedin`, `/jobs/indeed`, `/jobs/infojobs`). The
route:

  1. Validates the query via the Pydantic `AggregatedJobsQuery` schema.
  2. Splits, strips, dedupes, and validates the `sources` query param
     against `AGGREGATOR_SOURCES`. Unknown tokens return 422 with a
     descriptive `detail` (the route's `HTTPException` shape, NOT
     the Pydantic `RequestValidationError` shape — the per-token
     validation is a route concern, not a Pydantic concern).
  3. Resolves the use case from `request.app.state.aggregator_use_case`
     (set by `app_factory.build_app`).
  4. Calls the use case's `search(...)` method which returns an
     `AggregatedResult(jobs, per_source, cache_statuses)`. The
     `SearchAllSourcesUseCase` invokes the 3 cached use cases in
     parallel via `asyncio.gather` and dedupes by
     `(title, company, location)`.
  5. Maps the `AggregatedResult.jobs` (list of `AggregatedJob`) to
     `AggregatedJobsResponse.jobs` (list of `AggregatedJobResponse`
     with `id`, `title`, `company`, `location`, `url`, `posted_at`,
     `sources`).
  6. (T-003) Sets the `X-Cache` (joined per-source), `X-Aggregator-Sources`,
     and `X-Aggregator-Errors` response headers from the result's
     `cache_statuses` and `per_source`. Absent for `X-Aggregator-Errors`
     when all sources succeed.

The route is async, has zero `JobSearchPort`-shaped knowledge (it
only sees the `SearchAllSourcesUseCase` orchestrator), and lets the
registered handler handle 502 (port failure) and 500 (programming
bug) per the per-source error isolation contract (REQ-A-003).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import HttpUrl

from jobs_finder.application.aggregator import (
    SOURCE_PRIORITY,
    AggregatedResult,
    SearchAllSourcesUseCase,
)
from jobs_finder.presentation.schemas import (
    AGGREGATOR_SOURCES,
    AggregatedJobResponse,
    AggregatedJobsQuery,
    AggregatedJobsResponse,
)

router = APIRouter()


def get_aggregator_use_case(request: Request) -> SearchAllSourcesUseCase:
    """Resolve the aggregator use case from `app.state.aggregator_use_case`.

    `app_factory.build_app` is responsible for setting it. The
    default branch builds the aggregator from the 3 cached use
    cases passed to `build_app`; tests can override via
    `build_app(aggregator_use_case=...)` to inject a custom
    orchestrator.
    """
    use_case = getattr(request.app.state, "aggregator_use_case", None)
    if use_case is None:
        raise RuntimeError(
            "app.state.aggregator_use_case is not set; build the app via "
            "`build_app(aggregator_use_case=...)` (or let the default "
            "branch construct one from the 3 per-source use cases)."
        )
    return use_case  # type: ignore[no-any-return]


def _parse_sources(sources: str) -> list[str]:
    """Split, strip, dedup, and validate the `sources` query param.

    Returns the source list in iteration order (the order the
    caller provided). Returns an empty list if the input is empty
    after stripping. Raises `HTTPException(422)` for unknown tokens
    OR an empty result.
    """
    # Split by `,`, strip, filter empty.
    tokens = [s.strip() for s in sources.split(",") if s.strip()]
    # Dedupe while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            deduped.append(token)
    if not deduped:
        raise HTTPException(
            status_code=422,
            detail=(f"at least one source must be provided; valid: {sorted(AGGREGATOR_SOURCES)}"),
        )
    unknown = set(deduped) - AGGREGATOR_SOURCES
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(f"unknown sources: {sorted(unknown)}; valid: {sorted(AGGREGATOR_SOURCES)}"),
        )
    return deduped


def _to_aggregated_response(result: AggregatedResult) -> AggregatedJobsResponse:
    """Map the use case's `AggregatedResult` to the API response.

    Each `AggregatedJob` becomes an `AggregatedJobResponse` with the
    6 documented `JobResponse` fields + the `sources` list. The
    `sources` list is in source-priority order because the use
    case's `gather` is ordered by `SOURCE_PRIORITY`.
    """
    return AggregatedJobsResponse(
        jobs=[
            AggregatedJobResponse(
                id=agg.job.id,
                title=agg.job.title,
                company=agg.job.company,
                location=agg.job.location,
                url=HttpUrl(agg.job.url),
                posted_at=agg.job.posted_at,
                sources=agg.sources,  # type: ignore[arg-type]
            )
            for agg in result.jobs
        ]
    )


@router.get("/jobs", response_model=AggregatedJobsResponse)
async def aggregate_jobs(
    query: Annotated[AggregatedJobsQuery, Query()],
    use_case: Annotated[SearchAllSourcesUseCase, Depends(get_aggregator_use_case)],
    response: Response,
) -> AggregatedJobsResponse:
    """Aggregate jobs from the queried sources, deduped.

    The headers (`X-Cache` joined per-source, `X-Aggregator-Sources`,
    `X-Aggregator-Errors`) are set in T-003's commit. T-002 ships
    the body-only contract so the route can be exercised end-to-end
    before the header logic is layered on top.
    """
    source_list = _parse_sources(query.sources)

    result = await use_case.search(
        keywords=query.q,
        location=query.location,
        limit=query.limit,
        sources=source_list,
    )

    # T-003 (REQ-A-006): per-source observability headers. The route
    # is the composition root for the 3 sources' cache statuses + the
    # errored-source list. The order in the joined `X-Cache` and
    # `X-Aggregator-Sources` headers is the same `source_list` order
    # the caller provided (NOT necessarily source-priority order);
    # this matches the user's mental model — they asked for
    # `sources=linkedin,infojobs` and the headers reflect that
    # exact order. The route uses `result.per_source` to look up
    # the cache status and errored flag for each requested source.
    response.headers["X-Cache"] = ",".join(result.cache_statuses[s] for s in source_list)
    response.headers["X-Aggregator-Sources"] = ",".join(source_list)

    # `X-Aggregator-Errors` is absent when all sources succeed; it
    # is set to the comma-separated list of errored sources (in the
    # caller's order) when at least one fails. The list preserves
    # caller order so the client can map the errored-source names
    # back to its own request semantics.
    errored = [s for s in source_list if not result.per_source[s].succeeded]
    if errored:
        response.headers["X-Aggregator-Errors"] = ",".join(errored)

    return _to_aggregated_response(result)


# Re-exported so T-003 can join cache statuses in source-priority
# order without re-declaring the priority tuple (the constant lives
# in the application layer; the route re-exports it for header
# composition).
__all__ = ["router", "get_aggregator_use_case", "SOURCE_PRIORITY"]
