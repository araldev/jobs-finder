"""`GET /scheduler/status` route.

Spec: REQ-STATUS-002. Exposes the `BackgroundJobScheduler`'s runtime
state as a JSON endpoint. Gracefully degrades when the scheduler is
disabled (`SCHEDULER_ENABLED=false`): returns `enabled=False` with
default values, never crashes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.infrastructure.auth._jwt import UserState
from jobs_finder.infrastructure.scheduler import BackgroundJobScheduler
from jobs_finder.presentation.dependencies import get_current_user
from jobs_finder.presentation.schemas import SchedulerStatusResponse

router = APIRouter(tags=["scheduler"])


@router.get("/scheduler/status")
async def scheduler_status(
    request: Request,
    _user: UserState = Depends(get_current_user),  # noqa: B008
) -> SchedulerStatusResponse:
    """Return the scheduler's runtime state.

    Reads `app.state.scheduler` (may be `None` when scheduler is
    disabled). When `None`, returns graceful degradation response
    with `enabled=False`.

    Also reads `app.state.job_repository` to populate DB-level stats
    (`total_in_db`, `per_source`). When the repo is unavailable, those
    fields default to `0` / `{}`.
    """
    scheduler: BackgroundJobScheduler | None = getattr(request.app.state, "scheduler", None)

    if scheduler is None:
        return SchedulerStatusResponse(enabled=False)

    state = scheduler.state

    # Populate DB stats from the repository when available.
    repo: JobRepositoryPort | None = getattr(request.app.state, "job_repository", None)
    total_in_db = 0
    per_source: dict[str, int] = {}
    if repo is not None:
        total_in_db = await repo.count_jobs()
        for source in ("linkedin", "indeed", "infojobs"):
            count = await repo.count_jobs(sources=[source])
            if count > 0:
                per_source[source] = count

    return SchedulerStatusResponse(
        enabled=True,
        running=state.running,
        last_run_start=state.last_run_start,
        last_run_end=state.last_run_end,
        last_error=state.last_error,
        cycle_count=state.cycle_count,
        total_jobs_collected=state.total_jobs_collected,
        total_in_db=total_in_db,
        per_source=per_source,
        queries=scheduler._queries,
        min_interval_seconds=scheduler._min_interval,
        max_interval_seconds=scheduler._max_interval,
    )
