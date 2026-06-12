"""`GET /scheduler/status` route.

Spec: REQ-STATUS-002. Exposes the `BackgroundJobScheduler`'s runtime
state as a JSON endpoint. Gracefully degrades when the scheduler is
disabled (`SCHEDULER_ENABLED=false`): returns `enabled=False` with
default values, never crashes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from jobs_finder.infrastructure.scheduler import BackgroundJobScheduler
from jobs_finder.presentation.schemas import SchedulerStatusResponse

router = APIRouter(tags=["scheduler"])


@router.get("/scheduler/status")
async def scheduler_status(request: Request) -> SchedulerStatusResponse:
    """Return the scheduler's runtime state.

    Reads `app.state.scheduler` (may be `None` when scheduler is
    disabled). When `None`, returns graceful degradation response
    with `enabled=False`.
    """
    scheduler: BackgroundJobScheduler | None = getattr(request.app.state, "scheduler", None)

    if scheduler is None:
        return SchedulerStatusResponse(enabled=False)

    state = scheduler.state
    return SchedulerStatusResponse(
        enabled=True,
        running=state.running,
        last_run_start=state.last_run_start,
        last_run_end=state.last_run_end,
        last_error=state.last_error,
        cycle_count=state.cycle_count,
        total_jobs_collected=state.total_jobs_collected,
        # total_in_db and per_source require repo stats which aren't
        # available via `JobRepositoryPort` yet — default to 0 / {}.
        total_in_db=0,
        per_source={},
        queries=scheduler._queries,
        min_interval_seconds=scheduler._min_interval,
        max_interval_seconds=scheduler._max_interval,
    )
