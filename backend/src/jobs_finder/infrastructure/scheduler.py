"""Background job scheduler — periodically scrapes all sources and persists results.

Spec: REQ-SCH-001..005. Uses `asyncio.Lock` to prevent overlapping runs and
sleeps `random.uniform(min_interval, max_interval)` between cycles. The
scheduler's `search_fn` is a `Callable[[str, str], Awaitable[list[Job]]]`
wired at composition-root time to `SearchAllSourcesUseCase.search(...)`.

`scheduler-retention-history` adds `retention_days` param (REQ-SCH-001 MODIFIED).
When > 0, calls `repo.delete_older_than(days=retention_days, limit=1000)`
after each upsert batch (REQ-RET-002).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.domain.job import Job

_logger = logging.getLogger(__name__)

# Madrid business hours: 09:00 (inclusive) to 22:00 (exclusive)
_MADRID_ACTIVE_HOUR_START = 9
_MADRID_ACTIVE_HOUR_END = 22


def _get_madrid_time() -> datetime:
    """Return current time in the Europe/Madrid timezone."""
    return datetime.now(ZoneInfo("Europe/Madrid"))


def _is_within_active_hours() -> bool:
    """Return True if current Madrid time is between 09:00 and 22:00."""
    madrid_now = _get_madrid_time()
    return _MADRID_ACTIVE_HOUR_START <= madrid_now.hour < _MADRID_ACTIVE_HOUR_END


@dataclass
class SchedulerState:
    """Runtime state of `BackgroundJobScheduler`.

    Updated at each cycle boundary. Returned by the `state` property
    and surfaced by `GET /scheduler/status` (REQ-STATUS-001).
    """

    running: bool = False
    last_run_start: datetime | None = None
    last_run_end: datetime | None = None
    last_error: str | None = None
    cycle_count: int = 0
    total_jobs_collected: int = 0


class BackgroundJobScheduler:
    """Periodically calls `search_fn`, persists to `repo`. asyncio.Task lifecycle.

    Constructor:
        search_fn: Callable[[str, str], Awaitable[list[Job]]]
            — the search function (typically a wrapped aggregator use case).
        repo: JobRepositoryPort — persistent storage for scraped jobs.
        queries: list[dict[str, str]] — each dict has "keywords" and "location".
        min_interval: float = 1500.0 — minimum sleep between cycles (seconds).
        max_interval: float = 2100.0 — maximum sleep between cycles (seconds).
        retention_days: int = 0 — TTL in days. `0` (default) means
            "never delete". When > 0, `delete_older_than` runs after
            each upsert batch (REQ-RET-001, REQ-RET-002).

    Usage:
        scheduler = BackgroundJobScheduler(search_fn=fn, repo=repo, queries=[...])
        scheduler.start()   # fire-and-forget: creates asyncio.Task
        await scheduler.stop()  # cancels task gracefully
    """

    def __init__(
        self,
        search_fn: Callable[[str, str], Awaitable[list[Job]]],
        repo: JobRepositoryPort,
        queries: list[dict[str, str]],
        min_interval: float = 1500.0,
        max_interval: float = 2100.0,
        retention_days: int = 0,
    ) -> None:
        self._search_fn: Callable[[str, str], Awaitable[list[Job]]] = search_fn
        self._repo: JobRepositoryPort = repo
        self._queries: list[dict[str, str]] = queries
        self._min_interval: float = min_interval
        self._max_interval: float = max_interval
        self._retention_days: int = retention_days
        self._task: asyncio.Task[Any] | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._state: SchedulerState = SchedulerState()

    @property
    def state(self) -> SchedulerState:
        """Read-only view of the scheduler's runtime state."""
        return self._state

    def start(self) -> None:
        """Create `asyncio.create_task(self._loop())`. Fire-and-forget."""
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background task and catch `CancelledError`. Idempotent.

        Also updates the scheduler state to reflect that the scheduler
        has stopped (`running=False`, `last_run_end=now`).
        """
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            self._state.running = False
            self._state.last_run_end = datetime.now(UTC)

    async def _loop(self) -> None:
        """Lock-protected infinite loop with work-hours gate and `random.uniform(min, max)` sleep.

        Each cycle:
          1. Guards: waits until Madrid time is within 09:00–22:00 (sleeps 300s otherwise).
          2. Checks the lock — if held, logs a WARNING and skips this cycle.
          3. Acquires the lock and iterates all configured queries.
          4. Calls `search_fn(keywords, location)` for each query.
          5. Upserts ALL accumulated jobs to the repo with `source="aggregator"`
             and the LAST query as the query_snapshot.
          6. Sleeps `random.uniform(min_interval, max_interval)` seconds.
        """
        while True:
            # Guard: wait until we're within Madrid business hours (09:00-22:00)
            while not _is_within_active_hours():
                await asyncio.sleep(300)  # 5 minutes

            if self._lock.locked():
                _logger.warning("BackgroundJobScheduler: overlapping run detected — skipping cycle")
                await asyncio.sleep(random.uniform(self._min_interval, self._max_interval))
                continue

            async with self._lock:
                try:
                    self._state.running = True
                    self._state.last_run_start = datetime.now(UTC)

                    all_jobs: list[Job] = []
                    last_query: dict[str, str] = {}
                    for query in self._queries:
                        keywords = query["keywords"]
                        location = query["location"]
                        batch = await self._search_fn(keywords, location)
                        all_jobs.extend(batch)
                        last_query = query

                    if all_jobs:
                        await self._repo.upsert_jobs(
                            all_jobs,
                            query_snapshot=last_query,
                        )

                    # REQ-RET-002: run retention inline after upsert, inside
                    # the same lock acquisition, when retention_days > 0.
                    if self._retention_days > 0:
                        deleted = await self._repo.delete_older_than(
                            days=self._retention_days,
                            limit=1000,
                        )
                        if deleted > 0:
                            _logger.info(
                                "BackgroundJobScheduler: retention deleted %d old jobs",
                                deleted,
                            )

                    self._state.cycle_count += 1
                    self._state.total_jobs_collected += len(all_jobs)

                    _logger.info(
                        "BackgroundJobScheduler: cycle complete — %d jobs collected",
                        len(all_jobs),
                    )
                except Exception:
                    self._state.last_error = traceback.format_exc()
                    _logger.exception("BackgroundJobScheduler: cycle failed")
                finally:
                    self._state.running = False
                    self._state.last_run_end = datetime.now(UTC)

            await asyncio.sleep(random.uniform(self._min_interval, self._max_interval))
