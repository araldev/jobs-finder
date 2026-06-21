"""Integration tests for `GET /jobs/history`.

Spec: REQ-HIST-002. Tests the history endpoint with various query
parameters and validates the response shape matches `JobsHistoryResponse`.

All three use cases are injected as fakes so the test is deterministic
and never launches Playwright.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

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
from jobs_finder.infrastructure.persistence.sqlite_job_repository import (
    SqliteJobRepository,
)
from jobs_finder.presentation.app_factory import build_app


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort` for tests."""

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


_HISTORY_JOBS = [
    Job(
        id="linkedin_1",
        title="Python Developer",
        company="Tech Corp",
        location="Madrid, Spain",
        url="https://linkedin.com/jobs/view/1",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        source="linkedin",
    ),
    Job(
        id="linkedin_2",
        title="Java Engineer",
        company="Java Inc",
        location="Barcelona, Spain",
        url="https://linkedin.com/jobs/view/2",
        posted_at=datetime(2026, 5, 15, tzinfo=UTC),
        source="linkedin",
    ),
    Job(
        id="indeed_1",
        title="Python Data Analyst",
        company="Data Co",
        location="Madrid, Spain",
        url="https://es.indeed.com/viewjob?jk=indeed_1",
        posted_at=datetime(2026, 6, 10, tzinfo=UTC),
        source="indeed",
    ),
    Job(
        id="infojobs_1",
        title="Frontend Developer",
        company="Web SL",
        location="Valencia, Spain",
        url="https://www.infojobs.net/oferta-ij_1",
        posted_at=datetime(2026, 4, 1, tzinfo=UTC),
        source="infojobs",
    ),
]


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` whose lifespan is exercised by `LifespanManager`.

    `shutdown_timeout=30` to keep multi-scraper shutdown stable.
    Production uses uvicorn's graceful-shutdown timeout, not
    `LifespanManager`.
    """
    async with (
        LifespanManager(app, startup_timeout=30, shutdown_timeout=30),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


async def _insert_fixtures(app: Any) -> None:
    """Insert _HISTORY_JOBS into the repo."""
    repo: SqliteJobRepository = app.state.job_repository
    await repo.upsert_jobs([_HISTORY_JOBS[0]], query_snapshot={})
    await repo.upsert_jobs([_HISTORY_JOBS[1]], query_snapshot={})
    await repo.upsert_jobs([_HISTORY_JOBS[2]], query_snapshot={})
    await repo.upsert_jobs([_HISTORY_JOBS[3]], query_snapshot={})


def _make_app_with_empty_fakes(settings: Settings) -> Any:
    """Build an app where all three use cases return empty lists."""
    linkedin_port = FakeJobSearchPort(jobs=[])
    linkedin_use_case = SearchLinkedInJobsUseCase(
        port=linkedin_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )
    indeed_port = FakeJobSearchPort(jobs=[])
    indeed_use_case = IndeedSearchJobsUseCase(
        port=indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_port = FakeJobSearchPort(jobs=[])
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings,
    )


class TestHistoryApi:
    """Integration tests for `GET /jobs/history` (REQ-HIST-002)."""

    @pytest.mark.asyncio
    async def test_history_works_without_scheduler(self) -> None:
        """History endpoint works when scheduler is disabled but DB_PATH is set.

        Spec: REQ-HIST-002 scenario 2 — history without scheduler.
        When `scheduler_enabled=False` and `db_path` is set, the repo
        should be available and the history endpoint should return data.
        """
        settings = Settings(
            scheduler_enabled=False,
            db_path=":memory:",
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None, (
                "Expected repo when scheduler disabled, as long as db_path is set"
            )
            await _insert_fixtures(app)

            resp = await client.get("/jobs/history")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 4

    @pytest.mark.asyncio
    async def test_history_returns_items_and_total(self) -> None:
        """Basic request returns items list and total count."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            # Allow scheduler first cycle to pass
            await asyncio.sleep(0.05)

            resp = await client.get("/jobs/history")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
        assert data["total"] >= 4  # our fixtures + whatever scheduler stored
        # Default limit should be 50
        assert data["limit"] == 50
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_history_items_have_expected_fields(self) -> None:
        """Each item has the HistoricalJobResponse fields."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            await asyncio.sleep(0.05)

            resp = await client.get("/jobs/history")

        assert resp.status_code == 200
        data = resp.json()

        if data["items"]:
            item = data["items"][0]
            # Core Job fields
            assert "id" in item
            assert "title" in item
            assert "company" in item
            assert "location" in item
            assert "url" in item
            assert "posted_at" in item
            # Extra DB metadata fields (may be null if enrichment not yet done)
            # The schema declares them, they exist in the response
            assert "source" in item
            assert "first_seen_at" in item
            assert "last_seen_at" in item
            assert "query_snapshot" in item

    @pytest.mark.asyncio
    async def test_history_filters_by_source(self) -> None:
        """Filtering by source returns only jobs from that source."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            await asyncio.sleep(0.05)

            resp = await client.get("/jobs/history?sources=linkedin")

        assert resp.status_code == 200
        data = resp.json()
        # Only linkedin jobs (2 fixtures)
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_history_filters_by_date_range(self) -> None:
        """Date range filter returns jobs within [date_from, date_to]."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            await asyncio.sleep(0.05)

            # date_from=2026-05-01, date_to=2026-06-05 should include:
            #   linkedin_1 (2026-06-01), linkedin_2 (2026-05-15)
            #   but NOT indeed_1 (2026-06-10) or infojobs_1 (2026-04-01)
            resp = await client.get("/jobs/history?date_from=2026-05-01&date_to=2026-06-05")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_history_filters_by_keywords(self) -> None:
        """Keyword filter matches on title or company."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            await asyncio.sleep(0.05)

            resp = await client.get("/jobs/history?keywords=Python")

        assert resp.status_code == 200
        data = resp.json()
        # "Python" matches "Python Developer" and "Python Data Analyst"
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_history_pagination(self) -> None:
        """Pagination params limit and offset are respected."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            await asyncio.sleep(0.05)

            resp = await client.get("/jobs/history?limit=2&offset=0")

        assert resp.status_code == 200
        data = resp.json()
        # Should respect limit (at most 2 items)
        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_history_limit_is_capped_at_200(self) -> None:
        """Limit above 200 returns a validation error."""
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            resp = await client.get("/jobs/history?limit=300")

        # Pydantic rejects limit > 200 with 422
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Regression: `GET /jobs/history/by-id/{source_id}` returns the correct status
# (REQ-MAINT-012..014).
#
# Bug surfaced by `mypy --strict`: `JSONResponse(content, status=404)` is
# silently dropped because `JSONResponse.__init__` does NOT accept a `status`
# kwarg (the kwarg goes to **kwargs and is discarded). The endpoint returns
# 200 even when trying to signal 404. Fix per ADR-002: `raise HTTPException(
# status_code=404, detail="Job not found")` — FastAPI's built-in handler
# produces `{"detail": "Job not found"}` with status 404.
# ---------------------------------------------------------------------------


class TestHistoryByIdRegression:
    """Regression tests for the by-id endpoint's 404 contract (REQ-MAINT-012)."""

    @pytest.mark.asyncio
    async def test_by_id_returns_404_when_repo_missing(self) -> None:
        """When the DB is not configured (repo is None), the endpoint returns 404.

        Before the fix: returned 200 with body `{"error": "Job not found"}`
        (because `JSONResponse(..., status=404)` silently dropped `status`).
        After the fix: raises `HTTPException(404)` → FastAPI handler → 404.
        """
        # No db_path → repo is None
        settings = Settings(
            scheduler_enabled=False,
            db_path="",  # empty string disables the repository
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            repo = getattr(app.state, "job_repository", None)
            assert repo is None, "Expected repo=None when db_path is empty"

            resp = await client.get("/jobs/history/by-id/anything")

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Job not found"}

    @pytest.mark.asyncio
    async def test_by_id_returns_404_when_job_not_found(self) -> None:
        """When the repo is configured but the source_id is not present, returns 404."""
        settings = Settings(
            scheduler_enabled=False,
            db_path=":memory:",
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            resp = await client.get("/jobs/history/by-id/does-not-exist")

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Job not found"}

    @pytest.mark.asyncio
    async def test_by_id_returns_200_when_job_found(self) -> None:
        """Positive path: existing source_id → 200 + HistoricalJobResponse."""
        settings = Settings(
            scheduler_enabled=False,
            db_path=":memory:",
        )
        app = _make_app_with_empty_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await _insert_fixtures(app)
            resp = await client.get("/jobs/history/by-id/linkedin_1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "linkedin_1"
        assert body["title"] == "Python Developer"
        assert body["company"] == "Tech Corp"
        assert body["source"] == "linkedin"

    @pytest.mark.asyncio
    async def test_no_jsonresponse_with_status_kwarg_remains_in_src(self) -> None:
        """Sweep: no `JSONResponse(..., status=...)` calls remain in `backend/src/`.

        Per REQ-MAINT-014, the fix includes a sweep — after the
        `history.py` swap, NO production code should call
        `JSONResponse(content=..., status=...)` because the `status`
        kwarg is silently dropped. Future code should use
        `HTTPException(status_code=...)` for non-200 responses.
        """
        from pathlib import Path

        src_root = Path(__file__).resolve().parent.parent.parent / "src"
        offenders: list[str] = []
        for py in src_root.rglob("*.py"):
            text = py.read_text()
            if "JSONResponse(" in text and "status=" in text:
                # Check same-line or nearby lines
                for ln_no, line in enumerate(text.splitlines(), start=1):
                    if "JSONResponse(" in line and "status=" in line:
                        offenders.append(f"{py.relative_to(src_root)}:{ln_no}: {line.strip()}")

        assert offenders == [], (
            f"Found {len(offenders)} JSONResponse(...status=...) call(s):\n" + "\n".join(offenders)
        )
