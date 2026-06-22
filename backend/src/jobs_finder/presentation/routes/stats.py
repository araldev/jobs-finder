"""`GET /jobs/stats` route.

Spec: REQ-PDPRSC-003 (Family C of `perf-dashboard-rsc-migration`).
A single FastAPI endpoint that returns the consolidated dashboard
stats payload in ONE HTTP call. The previous `/api/stats` route
handler did 6 fetches in 3 waterfall chains (~600ms TTFB on cache
miss); this endpoint collapses them to 1 outbound fetch via the
`StatsAggregator` in `application/stats_aggregator.py`.

The aggregator is resolved from `request.app.state.stats_aggregator`
(set by `app_factory.build_app()`). The route handler is thin: it
delegates the actual work to the aggregator and serializes the
result to the `DashboardStatsResponse` Pydantic model.

On any exception the route returns a graceful-degradation payload
(`total_jobs: 0`, empty `platform_distribution`, `last_sync: null`)
so a transient aggregator failure does NOT 500 the dashboard. The
shape mirrors the route's success response so the frontend
`useStats` consumer can render the same UI in both paths.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from jobs_finder.application.stats_aggregator import (
    DashboardStatsPayload,
    StatsAggregator,
)
from jobs_finder.presentation.schemas import DashboardStatsResponse

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


@router.get("/jobs/stats", response_model=DashboardStatsResponse)
async def jobs_stats(request: Request) -> Any:
    """Return the consolidated dashboard stats in one call.

    Reads the `StatsAggregator` from `app.state.stats_aggregator`
    (set by `app_factory.build_app()`). On aggregator failure
    (timeout, transient DB error, etc.) returns the graceful-
    degradation payload so the dashboard renders zeros + an
    empty breakdown instead of a hard 500.
    """
    aggregator: StatsAggregator | None = getattr(request.app.state, "stats_aggregator", None)
    if aggregator is None:
        _logger.warning("GET /jobs/stats: app.state.stats_aggregator is None")
        return JSONResponse(
            content=DashboardStatsResponse(
                total_jobs=0,
                jobs_today=0,
                active_platforms=0,
                last_sync=None,
                platform_distribution={},
            ).model_dump(mode="json"),
            status_code=200,
        )

    try:
        payload: DashboardStatsPayload = await aggregator.aggregate()
    except Exception as exc:
        # Graceful degradation — the dashboard's `useStats`
        # consumer renders an EmptyState on `total_jobs == 0`
        # rather than a hard error toast.
        _logger.warning("GET /jobs/stats: aggregator raised %r", exc)
        return JSONResponse(
            content=DashboardStatsResponse(
                total_jobs=0,
                jobs_today=0,
                active_platforms=0,
                last_sync=None,
                platform_distribution={},
            ).model_dump(mode="json"),
            status_code=200,
        )

    return JSONResponse(
        content=DashboardStatsResponse(
            total_jobs=payload["total_jobs"],
            jobs_today=payload["jobs_today"],
            active_platforms=payload["active_platforms"],
            last_sync=payload["last_sync"],
            platform_distribution=payload["platform_distribution"],
        ).model_dump(mode="json"),
        status_code=200,
    )
