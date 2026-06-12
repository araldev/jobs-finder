"""Background job scheduler — periodically scrapes all sources and persists results.

Spec: REQ-SCH-001..005. Uses `asyncio.Lock` to prevent overlapping runs and
sleeps `random.uniform(min_interval, max_interval)` between cycles. The
scheduler's `search_fn` is a `Callable[[str, str], Awaitable[list[Job]]]`
wired at composition-root time to `SearchAllSourcesUseCase.search(...)`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.domain.job import Job

_logger = logging.getLogger(__name__)


class BackgroundJobScheduler:
    """Periodically calls `search_fn`, persists to `repo`. asyncio.Task lifecycle.

    Constructor:
        search_fn: Callable[[str, str], Awaitable[list[Job]]]
            — the search function (typically a wrapped aggregator use case).
        repo: JobRepositoryPort — persistent storage for scraped jobs.
        queries: list[dict[str, str]] — each dict has "keywords" and "location".
        min_interval: float = 1500.0 — minimum sleep between cycles (seconds).
        max_interval: float = 2100.0 — maximum sleep between cycles (seconds).

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
    ) -> None:
        self._search_fn: Callable[[str, str], Awaitable[list[Job]]] = search_fn
        self._repo: JobRepositoryPort = repo
        self._queries: list[dict[str, str]] = queries
        self._min_interval: float = min_interval
        self._max_interval: float = max_interval
        self._task: asyncio.Task[Any] | None = None
        self._lock: asyncio.Lock = asyncio.Lock()

    def start(self) -> None:
        """Create `asyncio.create_task(self._loop())`. Fire-and-forget."""
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background task and catch `CancelledError`. Idempotent."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        """Lock-protected infinite loop with `random.uniform(min, max)` sleep.

        Each cycle:
          1. Checks the lock — if held, logs a WARNING and skips this cycle.
          2. Acquires the lock and iterates all configured queries.
          3. Calls `search_fn(keywords, location)` for each query.
          4. Upserts ALL accumulated jobs to the repo with `source="aggregator"`
             and the LAST query as the query_snapshot.
          5. Sleeps `random.uniform(min_interval, max_interval)` seconds.
        """
        while True:
            if self._lock.locked():
                _logger.warning(
                    "BackgroundJobScheduler: overlapping run detected — skipping cycle"
                )
                await asyncio.sleep(random.uniform(self._min_interval, self._max_interval))
                continue

            async with self._lock:
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
                        all_jobs, source="aggregator", query_snapshot=last_query,
                    )

                _logger.info(
                    "BackgroundJobScheduler: cycle complete — %d jobs collected",
                    len(all_jobs),
                )

            await asyncio.sleep(random.uniform(self._min_interval, self._max_interval))
