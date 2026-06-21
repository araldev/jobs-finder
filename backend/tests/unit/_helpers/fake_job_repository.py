"""Fake `JobRepositoryPort` for tests.

Mirrors the old `FakeAggregator` shape: a simple value-holder
that records every call to `search_jobs_history(...)` and
returns a canned list of `Job`s (or raises a canned exception).
Other `JobRepositoryPort` methods are stubbed out — the
chat-filter use case only ever calls `search_jobs_history`.

The chat-filter use case (`FilterJobsByIntentUseCase`) no longer
calls the aggregator for the stage-2 job query. Instead it
queries this repository (populated by the scheduler). The fake
mirrors the SQLite-backed `SqliteJobRepository`'s public
contract so tests can swap one for the other without touching
the use case.
"""

from __future__ import annotations

from typing import Any

from jobs_finder.domain.job import Job


class FakeJobRepository:
    def __init__(self, jobs: list[Job] | None = None, error: Exception | None = None) -> None:
        self._jobs = jobs if jobs is not None else []
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def search_jobs_history(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        location: str | None = None,
        description: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        del description, date_from, date_to, offset
        self.calls.append(
            {
                "keywords": keywords,
                "location": location,
                "sources": sources,
                "limit": limit,
            }
        )
        if self._error is not None:
            raise self._error
        return list(self._jobs)

    async def upsert_jobs(
        self,
        jobs: list[Job],
        query_snapshot: dict[str, str],
    ) -> int:
        del jobs, query_snapshot
        return 0

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        del keywords, sources, limit, offset
        return []

    async def delete_older_than(self, *, days: int, limit: int = 1000) -> int:
        del days, limit
        return 0

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        del sources, keywords, date_from, date_to
        return 0

    async def get_job_by_source_id(self, source_id: str) -> Job | None:
        del source_id
        return None

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> FakeJobRepository:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None
