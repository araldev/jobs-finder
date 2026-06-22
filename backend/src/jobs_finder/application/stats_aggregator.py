"""`StatsAggregator` — orchestrate the 3 per-source counts + scheduler
status in PARALLEL with per-call timeout + TTL cache.

Spec: REQ-PDPRSC-003 (Family C of `perf-dashboard-rsc-migration`).
The dashboard renders 5 fields from this payload:

  - `total_jobs`        (int)            — all jobs across the 3 sources
  - `jobs_today`        (int)            — jobs posted today (UTC)
  - `active_platforms`  (int)            — count of sources with `count > 0`
  - `last_sync`         (str | None)     — scheduler's last `last_run_end`
  - `platform_distribution` (dict[str, int]) — per-source counts

The previous `/api/stats` route handler did 6 fetches in 3
`Promise.all` chains (~600ms TTFB on cache miss). The new endpoint
fetches everything in ONE `asyncio.gather` with a per-call timeout
(`STATS_PORT_TIMEOUT_SECONDS`, default 2.0s) so a slow LinkedIn port
(R3 mitigation per proposal #615) cannot block Indeed / InfoJobs.

The module depends ONLY on `application/ports.py` and `domain/`
(the `CachePort` Protocol is the seam for any cache
implementation). The dependency rule
`presentation → application → domain ← infrastructure` is preserved:
the `InMemoryTTLCache` (or future Redis / Memcached) is ctor-
injected by the composition root (`app_factory.build_app`); this
module never imports the concrete cache class.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from jobs_finder.application.ports import CachePort, JobRepositoryPort

_logger = logging.getLogger(__name__)


class DashboardStatsPayload(TypedDict):
    """The wire shape returned by `StatsAggregator.aggregate()`.

    The fields mirror `frontend/src/types/stats.ts` and the
    `DashboardStatsResponse` Pydantic model at the API edge. A
    drift between the 3 layers surfaces as a 422 from Pydantic
    (the route handler validates against the schema).
    """

    total_jobs: int
    jobs_today: int
    active_platforms: int
    last_sync: str | None
    platform_distribution: dict[str, int]


@dataclass(frozen=True, slots=True)
class _SourceResult:
    """The result of one per-source `count_jobs` invocation.

    Internal contract only — NOT exposed to the route handler.
    `count == 0` signals either "no jobs for this source" OR
    "timed out" — the aggregator uses the boolean `timed_out`
    to distinguish so the dashboard can show a graceful
    degradation (the source disappears from the breakdown
    instead of reporting `0`).
    """

    source: str
    count: int
    timed_out: bool


def _today_utc_date_string() -> str:
    """Return today's UTC date as `YYYY-MM-DD`.

    The aggregator filters `count_jobs(sources, date_from=today)`
    to compute `jobs_today`. The date string is computed at
    `aggregate()` call time so cache hits always reflect the
    time the request was made (the route handler is responsible
    for cache invalidation if a same-day shift matters).
    """
    return datetime.now(UTC).date().isoformat()


class StatsAggregator:
    """Parallel per-source counter with per-call timeout + TTL cache.

    Constructor-injected dependencies:
      - `job_repository`: `JobRepositoryPort` for `count_jobs`.
      - `scheduler_provider`: sync callable returning the
        scheduler's `last_run_end` (a `str | None`). The callable
        is sync because the scheduler exposes its state as a
        plain attribute (the route handler reads it from
        `app.state.scheduler`).
      - `timeout_seconds`: per-call timeout (default 2.0s, matches
        `STATS_PORT_TIMEOUT_SECONDS`). When a port call exceeds
        this budget, the source is excluded from
        `platform_distribution` and the total count skips it.
      - `cache`: any `CachePort[tuple[str, ...], DashboardStatsPayload]`.
        The composition root wires the concrete
        `InMemoryTTLCache` (or future Redis cache) via
        `build_cache(settings)` so the operator's
        `CACHE_TTL_SECONDS` env var applies to stats as well.

    The aggregator MUST NOT import infrastructure concrete
    implementations; the dependency rule is enforced by the
    `CachePort` Protocol seam.
    """

    def __init__(
        self,
        *,
        job_repository: JobRepositoryPort,
        scheduler_provider: Callable[[], str | None],
        timeout_seconds: float = 2.0,
        cache: CachePort[tuple[str, ...], DashboardStatsPayload],
    ) -> None:
        self._repo = job_repository
        self._scheduler_provider = scheduler_provider
        self._timeout = timeout_seconds
        self._cache = cache

    @staticmethod
    def cache_key() -> tuple[str, ...]:
        """The single, fixed cache key for the stats payload.

        The endpoint is unauthenticated today (the per-source
        routes are public per AGENTS.md) so one cache entry
        covers all callers.
        """
        return ("jobs-stats",)

    async def _count_with_timeout(
        self,
        source: str,
    ) -> _SourceResult:
        """Call `repo.count_jobs(sources=[source])` with a timeout.

        Returns a `_SourceResult` with `timed_out=True` on
        `asyncio.TimeoutError` so the aggregator excludes the
        source from the breakdown (the dashboard's graceful
        degradation path). Non-timeout exceptions propagate
        (programming bugs should not be silently swallowed).
        """
        try:
            count = await asyncio.wait_for(
                self._repo.count_jobs(sources=[source]),
                timeout=self._timeout,
            )
        except TimeoutError:
            _logger.warning(
                "stats: %s count_jobs exceeded timeout=%.2fs",
                source,
                self._timeout,
            )
            return _SourceResult(source=source, count=0, timed_out=True)
        return _SourceResult(source=source, count=int(count), timed_out=False)

    async def _total_with_timeout(self) -> int:
        """Call `repo.count_jobs()` (all sources) with a timeout.

        Returns 0 on timeout (the dashboard's graceful
        degradation for the `total_jobs` field is "show 0").
        """
        try:
            total = await asyncio.wait_for(
                self._repo.count_jobs(),
                timeout=self._timeout,
            )
        except TimeoutError:
            _logger.warning(
                "stats: total count_jobs exceeded timeout=%.2fs",
                self._timeout,
            )
            return 0
        return int(total)

    async def _jobs_today_with_timeout(self) -> int:
        """Call `repo.count_jobs(date_from=today)` with a timeout.

        Returns 0 on timeout. The `date_from` filter is the
        canonical `JobRepositoryPort.count_jobs` shape.
        """
        today = _today_utc_date_string()
        try:
            count = await asyncio.wait_for(
                self._repo.count_jobs(date_from=today),
                timeout=self._timeout,
            )
        except TimeoutError:
            _logger.warning(
                "stats: jobs_today count_jobs exceeded timeout=%.2fs",
                self._timeout,
            )
            return 0
        return int(count)

    async def aggregate(self) -> DashboardStatsPayload:
        """Return the consolidated stats payload.

        Flow:
          1. Cache HIT — return immediately.
          2. Cache MISS — fan-out to:
              - 3 per-source `count_jobs` calls (LinkedIn, Indeed,
                InfoJobs) — each wrapped in `asyncio.wait_for`
                with `timeout=self._timeout` so one slow port
                cannot block the others.
              - 1 `count_jobs()` (total) — same timeout.
              - 1 `count_jobs(date_from=today)` — same timeout.
              - 1 sync `scheduler_provider()` call.
             Each `wait_for` already isolates the per-call
             failure mode (timeout → fallback). Non-timeout
             exceptions propagate so a programming bug surfaces
             as a 500 (not a silent partial).
          3. Build the payload.
          4. Cache SET — keyed by `("jobs-stats",)` with TTL.
          5. Return.
        """
        cached = await self._cache.get(self.cache_key())
        if cached is not None:
            return cached

        # Fan out — each call is independently timeout-bounded.
        linkedin, indeed, infojobs, total, jobs_today = await asyncio.gather(
            self._count_with_timeout("linkedin"),
            self._count_with_timeout("indeed"),
            self._count_with_timeout("infojobs"),
            self._total_with_timeout(),
            self._jobs_today_with_timeout(),
        )

        # The scheduler provider is sync — call it inline (no I/O).
        last_sync = self._scheduler_provider()

        # Build the per-source breakdown. A timed-out source is
        # excluded (the dashboard shows it as missing rather than
        # as `0` — the `0` is reserved for "genuinely empty").
        platform_distribution: dict[str, int] = {}
        for result in (linkedin, indeed, infojobs):
            if not result.timed_out:
                platform_distribution[result.source] = result.count

        payload: DashboardStatsPayload = {
            "total_jobs": total,
            "jobs_today": jobs_today,
            "active_platforms": sum(1 for v in platform_distribution.values() if v > 0),
            "last_sync": last_sync,
            "platform_distribution": platform_distribution,
        }

        await self._cache.set(self.cache_key(), payload)
        return payload


__all__ = [
    "DashboardStatsPayload",
    "StatsAggregator",
]
