"""Integration tests for the aggregator's ranking step.

Spec: REQ-AR-001..REQ-AR-007 (jobs-aggregator-ranking).

The ranking is wired into `app_factory.build_app()` via the
`SearchAllSourcesUseCase` constructor kwargs. This file drives
the full app stack (FastAPI + `ASGITransport`) and exercises:

1. **Default strategy** (`posted_at`): the conftest's `app`
   fixture has LinkedIn empty, Indeed with 3 sample jobs (May 1,
   2, 3), and InfoJobs with 3 sample jobs (May 1, 2, 3). The
   response is ordered `[Indeed-May-3, InfoJobs-May-3,
   Indeed-May-2, InfoJobs-May-2, Indeed-May-1, InfoJobs-May-1]`
   by `posted_at` DESC + source-priority tie-breaker.

2. **`strategy="none"`** (escape hatch): a custom app build with
   `ranking_strategy="none"` returns the pre-change
   source-priority + scrape-order. The `Indeed` jobs come first
   (LinkedIn is empty), then `InfoJobs`.

3. **`strategy="priority"`** (source grouping): a custom app
   build with `ranking_strategy="priority"` groups jobs by
   source. With the same `posted_at` dates, all 3 Indeed jobs
   come first, then all 3 InfoJobs jobs.

4. **Env-var override**: `AGGREGATOR_RANKING_STRATEGY=none`
   applied via `os.environ` + `Settings()` override changes the
   response order without invalidating the cache (the
   `X-Cache: HIT` header proves the cache key is unchanged).

5. **Limit cap preserved** (REQ-AR-001): the response can have
   up to `3 * limit` jobs (per-source scrapers cap at `limit`).
   The ranking is applied to the full deduped list; no
   aggregator-level cap is added.

These tests are the RED step of T-001 Cycle 4 (Strict TDD). They
MUST be authored BEFORE the app_factory wiring lands. The run on
a clean tree must FAIL for the right reason — the default
strategy is already wired via the `use_case.__init__` defaults,
so tests 1, 2, 3, 5 need a different `app_factory` invocation
to inject a custom `ranking_strategy`. Test 4 is the env-var
override path.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
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
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Local fixtures (mirrored from `test_aggregator_api.py` so this test
# file remains self-contained; see the conftest docs for why the
# duplication is intentional).
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers (mirror the conftest's `_build_cached_linkedin_use_case` but
# are inlined so this test file remains self-contained).
# ---------------------------------------------------------------------------


def _build_cached_linkedin_use_case(port: FakeJobSearchPort) -> CachedJobSearchUseCase:
    return SearchLinkedInJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )


def _build_cached_indeed_use_case(port: FakeJobSearchPort) -> CachedJobSearchUseCase:
    return IndeedSearchJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )


def _build_cached_infojobs_use_case(port: FakeJobSearchPort) -> CachedJobSearchUseCase:
    return InfoJobsSearchJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )


def _build_app_with_strategy(
    linkedin_port: FakeJobSearchPort,
    indeed_port: FakeJobSearchPort,
    infojobs_port: FakeJobSearchPort,
    ranking_strategy: str,
) -> FastAPI:
    """Build a `FastAPI` with a custom `ranking_strategy` on the aggregator.

    The 3 per-source use cases are wrapped around the given ports;
    the aggregator is constructed directly with the requested
    `ranking_strategy` (the default `priority_map` is used). This
    bypasses `app_factory.build_app`'s default aggregator branch
    so the test can pin a specific strategy.
    """
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = _build_cached_indeed_use_case(port=indeed_port)
    infojobs_use_case = _build_cached_infojobs_use_case(port=infojobs_port)
    aggregator_use_case = SearchAllSourcesUseCase(
        linkedin_use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        ranking_strategy=ranking_strategy,  # type: ignore[arg-type]
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        aggregator_use_case=aggregator_use_case,
    )


# ---------------------------------------------------------------------------
# 1. Default strategy: `posted_at` DESC
# ---------------------------------------------------------------------------


async def test_default_strategy_orders_jobs_by_posted_at_desc(
    client: httpx.AsyncClient,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """The conftest's `app` fixture (default strategy) orders jobs by `posted_at` DESC.

    Indeed sample jobs: May 1, 2, 3. InfoJobs sample jobs: May 1, 2, 3.
    With the default `posted_at` DESC + source-priority tie-breaker,
    the order is [Indeed-May-3, InfoJobs-May-3, Indeed-May-2,
    InfoJobs-May-2, Indeed-May-1, InfoJobs-May-1]. LinkedIn is
    empty (no jobs in the conftest fixture).

    REQ-AR-002: default ranking is `posted_at` DESC.
    """
    response = await client.get(
        "/jobs?q=python&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
    )

    assert response.status_code == 200
    body = response.json()
    assert [job["sources"] for job in body["jobs"]] == [
        ["indeed"],
        ["infojobs"],
        ["indeed"],
        ["infojobs"],
        ["indeed"],
        ["infojobs"],
    ]


# ---------------------------------------------------------------------------
# 2. `strategy="none"` — escape hatch (pre-change behavior)
# ---------------------------------------------------------------------------


async def test_strategy_none_returns_jobs_in_existing_order(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """`ranking_strategy="none"` returns the pre-change source-priority order.

    The escape hatch (REQ-AR-003): the response groups by source
    in source-priority order (LinkedIn, Indeed, InfoJobs). LinkedIn
    is empty in the conftest fixture, so the response is
    [Indeed, Indeed, Indeed, InfoJobs, InfoJobs, InfoJobs] — the
    pre-change behavior.

    REQ-AR-003 scenario "`none` preserves pre-change input order".
    """
    linkedin_port = FakeJobSearchPort()
    app = _build_app_with_strategy(linkedin_port, fake_indeed_port, fake_infojobs_port, "none")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=python&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
        )

    assert response.status_code == 200
    body = response.json()
    # Source-priority order: Indeed first, then InfoJobs.
    assert [job["sources"] for job in body["jobs"]] == ([["indeed"]] * 3 + [["infojobs"]] * 3)


# ---------------------------------------------------------------------------
# 3. `strategy="priority"` — source grouping
# ---------------------------------------------------------------------------


async def test_strategy_priority_orders_by_source_priority(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> None:
    """`ranking_strategy="priority"` groups by source, ignoring freshness.

    With the default `priority_map` (LinkedIn=0, Indeed=1, InfoJobs=2),
    the response groups by source: all Indeed jobs first, then all
    InfoJobs jobs. Within each source group, the jobs are in
    insertion order (the per-source port's emit order). The
    freshness `posted_at` is IGNORED.

    REQ-AR-003 scenario "`priority` orders by source-priority only".
    """
    linkedin_port = FakeJobSearchPort()
    app = _build_app_with_strategy(linkedin_port, fake_indeed_port, fake_infojobs_port, "priority")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=python&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
        )

    assert response.status_code == 200
    body = response.json()
    # Priority groups: Indeed first (priority 1), then InfoJobs (2).
    assert [job["sources"] for job in body["jobs"]] == ([["indeed"]] * 3 + [["infojobs"]] * 3)


# ---------------------------------------------------------------------------
# 4. Env-var override (`AGGREGATOR_RANKING_STRATEGY`) is wired
# ---------------------------------------------------------------------------


async def test_env_var_override_changes_ranking(
    monkeypatch: pytest.MonkeyPatch,
    sample_indeed_jobs: list[Job],
    sample_infojobs_jobs: list[Job],
) -> None:
    """`AGGREGATOR_RANKING_STRATEGY=none` set in env changes the response order.

    The `app_factory.build_app` default branch reads
    `effective_settings.aggregator_ranking_strategy` and passes
    it to the `SearchAllSourcesUseCase` constructor. The
    conftest's `app` fixture uses the default strategy; this test
    builds a NEW app with the env var set to `none` and asserts
    the response order changes.

    REQ-AR-003: env-var surface.
    REQ-AR-005: cache key is unchanged — flipping the strategy
    does NOT invalidate the cache. The 1st call populates the
    cache (MISS); the 2nd call under the new strategy hits the
    cache (HIT) and re-ranks. `X-Cache: HIT` on the 2nd call
    pins the invariant.
    """
    monkeypatch.setenv("AGGREGATOR_RANKING_STRATEGY", "none")
    linkedin_port = FakeJobSearchPort()
    indeed_port = FakeJobSearchPort(jobs=sample_indeed_jobs)
    infojobs_port = FakeJobSearchPort(jobs=sample_infojobs_jobs)
    app = build_app(
        use_case=_build_cached_linkedin_use_case(port=linkedin_port),
        indeed_use_case=_build_cached_indeed_use_case(port=indeed_port),
        infojobs_use_case=_build_cached_infojobs_use_case(port=infojobs_port),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = await ac.get(
            "/jobs?q=python&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
        )
        second = await ac.get(
            "/jobs?q=python&location=madrid&limit=20&sources=linkedin,indeed,infojobs"
        )

    assert first.status_code == 200
    assert second.status_code == 200
    # `strategy="none"` groups by source. LinkedIn is empty, so
    # the order is [Indeed, Indeed, Indeed, InfoJobs, InfoJobs, InfoJobs].
    assert [job["sources"] for job in first.json()["jobs"]] == (
        [["indeed"]] * 3 + [["infojobs"]] * 3
    )
    assert [job["sources"] for job in second.json()["jobs"]] == (
        [["indeed"]] * 3 + [["infojobs"]] * 3
    )
    # REQ-AR-005: the 2nd call hits the cache (the underlying
    # port was called once on the 1st request and the cache
    # stored the result; the 2nd request returns the cached
    # result with the new ranking applied).
    assert first.headers["X-Cache"] == "MISS,MISS,MISS"
    assert second.headers["X-Cache"] == "HIT,HIT,HIT"


# ---------------------------------------------------------------------------
# 5. Limit cap preserved (REQ-AR-001)
# ---------------------------------------------------------------------------


async def test_limit_cap_preserves_three_times_limit() -> None:
    """`?limit=N` returns up to `3 * N` deduped jobs (per-source cap).

    Each per-source scraper caps at `limit` independently, so the
    response can have up to `3 * limit` jobs. The ranking is
    applied to the full deduped list; no aggregator-level cap is
    added.

    With `limit=2` and 3 sources each returning 2 distinct jobs,
    the response has 6 jobs (2 + 2 + 2 = `3 * 2`).

    REQ-AR-001: cap behavior is preserved.
    """
    # 2 distinct Indeed jobs.
    indeed_jobs = [
        _custom_job("i1", posted_at=datetime(2026, 5, 1, tzinfo=UTC), source="indeed"),
        _custom_job("i2", posted_at=datetime(2026, 5, 2, tzinfo=UTC), source="indeed"),
    ]
    # 2 distinct LinkedIn jobs.
    linkedin_jobs = [
        _custom_job("l1", posted_at=datetime(2026, 5, 3, tzinfo=UTC), source="linkedin"),
        _custom_job("l2", posted_at=datetime(2026, 5, 4, tzinfo=UTC), source="linkedin"),
    ]
    # 2 distinct InfoJobs jobs.
    infojobs_jobs = [
        _custom_job("j1", posted_at=datetime(2026, 5, 5, tzinfo=UTC), source="infojobs"),
        _custom_job("j2", posted_at=datetime(2026, 5, 6, tzinfo=UTC), source="infojobs"),
    ]
    linkedin_port = FakeJobSearchPort(jobs=linkedin_jobs)
    indeed_port = FakeJobSearchPort(jobs=indeed_jobs)
    infojobs_port = FakeJobSearchPort(jobs=infojobs_jobs)
    app = build_app(
        use_case=_build_cached_linkedin_use_case(port=linkedin_port),
        indeed_use_case=_build_cached_indeed_use_case(port=indeed_port),
        infojobs_use_case=_build_cached_infojobs_use_case(port=infojobs_port),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs?q=python&location=madrid&limit=2&sources=linkedin,indeed,infojobs"
        )

    assert response.status_code == 200
    body = response.json()
    # 3 * 2 = 6 deduped jobs (no cap added at the aggregator).
    assert len(body["jobs"]) == 6
    # Default ranking is `posted_at` DESC: j2 (May 6) first, then
    # j1 (May 5), l2 (May 4), l1 (May 3), i2 (May 2), i1 (May 1).
    assert [job["id"] for job in body["jobs"]] == [
        "j2",
        "j1",
        "l2",
        "l1",
        "i2",
        "i1",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _custom_job(
    job_id: str,
    *,
    posted_at: datetime,
    source: str,
) -> Job:
    """Build a `Job` with a custom id and `posted_at` for limit-cap tests."""
    return Job(
        id=job_id,
        title=f"{source} title {job_id}",
        company=f"{source} co {job_id}",
        location="Madrid, Spain",
        url=f"https://example.com/{source}/{job_id}",
        posted_at=posted_at,
    )
