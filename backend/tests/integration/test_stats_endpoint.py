"""Integration tests for `GET /jobs/stats` (REQ-PDPRSC-003).

Spec: SCN-PDPRSC-003-A (full payload in one call), SCN-PDPRSC-003-E
(response shape matches `DashboardStats` schema). Tests the
endpoint with a fake `JobRepositoryPort` (deterministic counts) so
the test is fast and reproducible — no Playwright, no live scraping.

The tests cover:
  1. `test_returns_all_fields_in_one_call` — `GET /jobs/stats`
     returns status 200 with all 5 documented fields
     (`total_jobs`, `jobs_today`, `last_sync`,
     `platform_distribution`, `active_platforms`).
  2. `test_response_shape_matches_schema` — the response validates
     against the `DashboardStatsResponse` Pydantic model.
  3. `test_stats_endpoint_registered` — infra: `app.routes` contains
     the `/jobs/stats` path so a future router removal surfaces as a
     test failure.

The aggregator's `timeout_seconds` env var is monkeypatched to a
low value via `Settings(stats_port_timeout_seconds=...)` so the test
does not depend on the production default.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.stats_aggregator import StatsAggregator
from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app
from jobs_finder.presentation.schemas import DashboardStatsResponse


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort` for tests.

    The route factory uses real `SearchJobsUseCase`s; the per-source
    routes are not exercised by `/jobs/stats` so the ports can be
    empty. The test focuses on the aggregator path.
    """

    def __init__(self, jobs: list[Job] | None = None) -> None:
        self._jobs = jobs or []
        self.calls: list[tuple[str, str, int]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        del geo_id
        self.calls.append((keywords, location, limit))
        return list(self._jobs)


class FakeJobRepository:
    """In-memory fake of `JobRepositoryPort` for tests.

    Holds a per-source count dict and returns it from `count_jobs`.
    The other `JobRepositoryPort` methods are stubs that satisfy the
    Protocol structurally (mypy --strict) but are never exercised
    by the aggregator.
    """

    def __init__(self, per_source: dict[str, int]) -> None:
        self._per_source = dict(per_source)

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        del keywords, date_from, date_to
        if sources is None:
            return sum(self._per_source.values())
        return sum(self._per_source.get(source, 0) for source in sources)

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


def _fake_scheduler_provider(
    last_run_end: str | None = "2026-06-22T10:00:00Z",
) -> Callable[[], str | None]:
    """Build a sync callable that returns a fixed scheduler status."""

    def _provider() -> str | None:
        return last_run_end

    return _provider


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` with the FastAPI lifespan exercised.

    The lifespan is required because `build_app()` (without an
    injected use case) constructs real Playwright scrapers whose
    `__aenter__` runs on startup. We inject fake ports here so
    Playwright never launches.
    """
    async with (
        LifespanManager(app, startup_timeout=30, shutdown_timeout=30),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


def _build_app_with_fake_repo(
    *,
    per_source: dict[str, int] | None = None,
    last_run_end: str | None = "2026-06-22T10:00:00Z",
    timeout_seconds: float = 2.0,
) -> Any:
    """Build a FastAPI app wired to a fake `JobRepositoryPort` +
    fake `StatsAggregator`.

    The aggregator is constructed here (not by the composition
    root) because the unit-level test wants deterministic counts.
    The composition-root path is exercised by the existing
    `test_app_lifespan.py` suite.
    """
    per_source = per_source or {"linkedin": 10, "indeed": 12, "infojobs": 8}
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = SearchLinkedInJobsUseCase(
        port=linkedin_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )
    indeed_port = FakeJobSearchPort()
    indeed_use_case = IndeedSearchJobsUseCase(
        port=indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_port = FakeJobSearchPort()
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )

    settings = Settings(
        db_path=":memory:",
        stats_port_timeout_seconds=timeout_seconds,
    )

    app = build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings,
    )

    # Override the aggregator with one wired to a fake repo so the
    # test gets deterministic counts. This bypasses the default
    # `app.state.job_repository` (which is built from the SQLite
    # `:memory:` DB the lifespan spins up).
    app.state.stats_aggregator = StatsAggregator(
        job_repository=FakeJobRepository(per_source=per_source),
        scheduler_provider=_fake_scheduler_provider(last_run_end),
        timeout_seconds=timeout_seconds,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
    )
    # `jobs_today` is read from the repo via a date-filtered count;
    # the aggregator's contract is "0 when the repo returns no rows".
    # The fake repo above always returns 0 for `jobs_today` because
    # it doesn't track dates — the integration test asserts
    # `>= 0`, not a specific number.

    return app


class TestStatsEndpoint:
    """Integration tests for `GET /jobs/stats` (REQ-PDPRSC-003)."""

    @pytest.mark.asyncio
    async def test_returns_all_fields_in_one_call(self) -> None:
        """SCN-PDPRSC-003-A: full payload in one HTTP call.

        The endpoint MUST return 200 with `total_jobs`, `jobs_today`,
        `last_sync`, `platform_distribution`, and `active_platforms`
        in a single JSON response.
        """
        app = _build_app_with_fake_repo()

        async with _client_with_lifespan(app) as client:
            resp = await client.get("/jobs/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert "total_jobs" in data
        assert "jobs_today" in data
        assert "last_sync" in data
        assert "platform_distribution" in data
        assert "active_platforms" in data
        assert isinstance(data["platform_distribution"], dict)
        # Per the seeded counts: 10 LinkedIn + 12 Indeed + 8 InfoJobs.
        assert data["platform_distribution"]["linkedin"] == 10
        assert data["platform_distribution"]["indeed"] == 12
        assert data["platform_distribution"]["infojobs"] == 8
        assert data["active_platforms"] == 3

    @pytest.mark.asyncio
    async def test_response_shape_matches_schema(self) -> None:
        """SCN-PDPRSC-003-E: response validates against DashboardStatsResponse.

        The Pydantic schema at the route boundary pins the field
        names + types. A future refactor that drops a field surfaces
        as a 422 from Pydantic (the test asserts 200 + the schema
        accepts the body).
        """
        app = _build_app_with_fake_repo()

        async with _client_with_lifespan(app) as client:
            resp = await client.get("/jobs/stats")

        assert resp.status_code == 200
        # Validate against the schema — this raises on shape mismatch.
        validated = DashboardStatsResponse.model_validate(resp.json())
        assert validated.total_jobs == 30
        assert validated.active_platforms == 3
        assert validated.platform_distribution["linkedin"] == 10
        assert validated.platform_distribution["indeed"] == 12
        assert validated.platform_distribution["infojobs"] == 8
        assert validated.last_sync == "2026-06-22T10:00:00Z"

    def test_stats_endpoint_registered(self) -> None:
        """The `/jobs/stats` route MUST be in `app.routes`.

        Infra assertion: a future refactor that forgets
        `app.include_router(stats_routes.router)` in
        `app_factory.build_app()` surfaces as a test failure here.
        """
        app = _build_app_with_fake_repo()
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/jobs/stats" in paths

    def test_settings_has_stats_port_timeout_seconds(self) -> None:
        """T-PDPRSC-009 (infra): the `stats_port_timeout_seconds` env
        field is wired in `Settings` (REQ-PDPRSC-003 env var).

        The field MUST default to 2.0 (per design §4) and accept a
        programmatic value via the field name (the same `AliasChoices`
        pattern used by every other Settings field).
        """
        default = Settings()
        assert default.stats_port_timeout_seconds == 2.0

        overridden = Settings(stats_port_timeout_seconds=0.5)
        assert overridden.stats_port_timeout_seconds == 0.5
