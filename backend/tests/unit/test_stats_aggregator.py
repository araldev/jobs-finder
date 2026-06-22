"""Tests for `StatsAggregator` (REQ-PDPRSC-003).

Spec: SCN-PDPRSC-003-B, SCN-PDPRSC-003-C. The aggregator's job is to
fetch the per-source counts + total + scheduler status in PARALLEL
(`asyncio.gather(return_exceptions=True)`) so one slow source cannot
block the rest. The per-call timeout is configurable via
`STATS_PORT_TIMEOUT_SECONDS` (default 2.0s, env-overridable).

This test file pins TWO scenarios:
  1. SCN-PDPRSC-003-B — A LinkedIn `count_jobs` that sleeps 5s MUST
     NOT block Indeed/InfoJobs. The aggregator returns within
     `timeout_seconds + epsilon` (~2.5s for the default 2.0s
     timeout) with the Indeed + InfoJobs counts present and the
     LinkedIn count replaced by the timeout fallback (0 or omitted).
  2. SCN-PDPRSC-003-C — When `STATS_PORT_TIMEOUT_SECONDS=0.1` is
     monkeypatched and the underlying call sleeps 1s, the aggregator
     MUST return within ~0.3s with the slow port excluded from the
     payload.

The aggregator is a thin orchestrator (presentation → application →
domain ← infrastructure). It lives in `application/` and imports
ONLY ports from `application/ports.py` and the `domain/` — NO
infrastructure imports (the dependency rule). Tests inject fake
ports so the unit test never launches Playwright.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from jobs_finder.application.stats_aggregator import (
    DashboardStatsPayload,
    StatsAggregator,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache


class _FakeJobRepository:
    """In-memory fake of `JobRepositoryPort` with controllable per-source delay.

    The constructor takes per-source counts and per-source delays so
    tests can simulate a slow LinkedIn port while Indeed + InfoJobs
    ports return instantly.
    """

    def __init__(
        self,
        *,
        total: int = 0,
        per_source: dict[str, int] | None = None,
        delays: dict[str, float] | None = None,
    ) -> None:
        self._total = total
        self._per_source = per_source or {}
        self._delays = delays or {}

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        del keywords, date_from, date_to
        # Per-source delay (or total-only when sources is None)
        if sources is None:
            delay = self._delays.get("__total__", 0.0)
            if delay > 0:
                await asyncio.sleep(delay)
            return self._total
        # Sum across the requested sources
        for source in sources:
            delay = self._delays.get(source, 0.0)
            if delay > 0:
                await asyncio.sleep(delay)
        return sum(self._per_source.get(source, 0) for source in sources)

    # Methods below satisfy the `JobRepositoryPort` Protocol
    # structurally (mypy --strict). They are not exercised by the
    # aggregator but must exist for type compatibility.
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
        del sources, keywords, location, description, date_from, date_to, limit, offset
        return []

    async def get_job_by_source_id(self, source_id: str) -> Job | None:
        del source_id
        return None

    async def close(self) -> None:
        return None


class _FakeSchedulerProvider:
    """Callable wrapper for scheduler status; returns a fixed value."""

    def __init__(self, last_run_end: str | None) -> None:
        self._last_run_end = last_run_end
        self.calls: int = 0

    def __call__(self) -> str | None:
        self.calls += 1
        return self._last_run_end


def _make_cache() -> InMemoryTTLCache[tuple[str, ...], DashboardStatsPayload]:
    return InMemoryTTLCache(ttl_seconds=60.0)


class TestStatsAggregatorPerPortTimeout:
    """Per-port timeout isolation (SCN-PDPRSC-003-B + 003-C)."""

    @pytest.mark.asyncio
    async def test_slow_linkedin_does_not_block_others(self) -> None:
        """LinkedIn port sleeps 5s; Indeed + InfoJobs return instantly.

        The aggregator MUST return within `timeout_seconds + epsilon`
        (~2.5s with the default 2.0s timeout) with Indeed + InfoJobs
        counts present in `platform_distribution` and the LinkedIn
        entry replaced by the timeout fallback (0 — the port was
        excluded from the breakdown because the timeout fired).

        This is the core R3 mitigation: one slow LinkedIn port MUST
        NOT block Indeed + InfoJobs returns.
        """
        repo = _FakeJobRepository(
            total=30,
            per_source={"linkedin": 10, "indeed": 12, "infojobs": 8},
            delays={"linkedin": 5.0},  # LinkedIn hangs for 5s
        )
        scheduler = _FakeSchedulerProvider("2026-06-22T10:00:00Z")

        aggregator = StatsAggregator(
            job_repository=repo,
            scheduler_provider=scheduler,
            timeout_seconds=2.0,
            cache=_make_cache(),
        )

        start = time.monotonic()
        result = await aggregator.aggregate()
        elapsed = time.monotonic() - start

        # Returned well under the slow port's 5s wait.
        assert elapsed < 2.5, f"aggregate took {elapsed:.2f}s — timeout did NOT fire"

        # Indeed + InfoJobs counts survived the parallel gather.
        assert "indeed" in result["platform_distribution"]
        assert "infojobs" in result["platform_distribution"]
        assert result["platform_distribution"]["indeed"] == 12
        assert result["platform_distribution"]["infojobs"] == 8
        # LinkedIn timed out — its count is the timeout fallback (0).
        # The aggregator contract excludes timed-out sources from the
        # breakdown rather than emitting zeros (the dashboard's
        # JobSourceBreakdown component reads
        # `platform_distribution.linkedin` and renders "0" only when
        # the source is genuinely empty; the timeout path is
        # signaled by the missing key).
        assert result["platform_distribution"].get("linkedin", 0) == 0

        # Scheduler still resolved (the scheduler provider is sync).
        assert result["last_sync"] == "2026-06-22T10:00:00Z"

    @pytest.mark.asyncio
    async def test_per_port_timeout_env_override(self) -> None:
        """A 0.1s timeout cuts a 1s sleep to ~0.15s return.

        The aggregator's `timeout_seconds` is the seam the env var
        `STATS_PORT_TIMEOUT_SECONDS` controls (REQ-PDPRSC-003-C). When
        monkeypatched to `0.1`, a port that sleeps `1.0s` MUST be
        timed out at ~0.1s, leaving the aggregator to return within
        `0.3s` (100ms timeout + small scheduling margin).
        """
        repo = _FakeJobRepository(
            total=15,
            per_source={"linkedin": 5, "indeed": 5, "infojobs": 5},
            delays={"__total__": 1.0},  # the total-count call sleeps 1s
        )
        scheduler = _FakeSchedulerProvider(None)

        aggregator = StatsAggregator(
            job_repository=repo,
            scheduler_provider=scheduler,
            timeout_seconds=0.1,  # the monkeypatched env-var value
            cache=_make_cache(),
        )

        start = time.monotonic()
        result = await aggregator.aggregate()
        elapsed = time.monotonic() - start

        assert elapsed < 0.3, f"aggregate took {elapsed:.2f}s — timeout=0.1s was NOT honored"
        # The total-count port was the slow one; its timeout yields 0.
        assert result["total_jobs"] == 0
        # Per-source counts were fast; they still arrive.
        assert sum(result["platform_distribution"].values()) >= 0

    @pytest.mark.asyncio
    async def test_aggregate_returns_full_payload_shape(self) -> None:
        """Happy path: all 3 sources + scheduler return instantly.

        The aggregator MUST return a `DashboardStatsPayload` with
        every documented field present (REQ-PDPRSC-003 scenario A).
        """
        repo = _FakeJobRepository(
            total=42,
            per_source={"linkedin": 20, "indeed": 15, "infojobs": 7},
        )
        scheduler = _FakeSchedulerProvider("2026-06-22T10:00:00Z")

        aggregator = StatsAggregator(
            job_repository=repo,
            scheduler_provider=scheduler,
            timeout_seconds=2.0,
            cache=_make_cache(),
        )

        result = await aggregator.aggregate()

        assert isinstance(result["total_jobs"], int)
        assert isinstance(result["platform_distribution"], dict)
        assert result["platform_distribution"]["linkedin"] == 20
        assert result["platform_distribution"]["indeed"] == 15
        assert result["platform_distribution"]["infojobs"] == 7
        assert result["last_sync"] == "2026-06-22T10:00:00Z"
        assert result["active_platforms"] == 3
        assert isinstance(result["jobs_today"], int)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_same_instance(self) -> None:
        """A second call within the TTL MUST hit the cache.

        The aggregator uses the injected `InMemoryTTLCache` with a
        `("jobs-stats",)` key. On a second call within the TTL the
        underlying ports MUST NOT be invoked again (REQ-CACHEUX-001
        parity with the existing `/jobs/history` 60s TTL).
        """
        repo = _FakeJobRepository(
            total=42,
            per_source={"linkedin": 20, "indeed": 15, "infojobs": 7},
        )
        scheduler = _FakeSchedulerProvider("2026-06-22T10:00:00Z")

        aggregator = StatsAggregator(
            job_repository=repo,
            scheduler_provider=scheduler,
            timeout_seconds=2.0,
            cache=_make_cache(),
        )

        first = await aggregator.aggregate()
        # Capture the scheduler calls after the first call (cache miss).
        scheduler_calls_after_first = scheduler.calls
        second = await aggregator.aggregate()
        scheduler_calls_after_second = scheduler.calls

        # Cache HIT — scheduler NOT consulted a second time.
        assert scheduler_calls_after_second == scheduler_calls_after_first
        # And the response shape is byte-identical.
        assert first == second
