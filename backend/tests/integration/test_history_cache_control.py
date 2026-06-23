"""Integration tests for `Cache-Control` on `/jobs/history` (REQ-CACHEUX-002).

Spec: REQ-CACHEUX-002 mandates `Cache-Control: public, max-age=60`
on both `/jobs/history` (200) and `/jobs/history/by-id/{id}` (200
+ 404). NO header on `/scheduler/status` (negative test). NO
header on 500 (negative test).

Per design OQ1, the value is EXACTLY `"public, max-age=60"` — NO
`s-maxage`, NO `stale-while-revalidate` because no CDN is deployed.

Mirrors the existing `test_history_api.py` app fixture pattern so
the test is hermetic (no Playwright, no live scrapers, no live DB).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives.asymmetric import ec
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
from jobs_finder.presentation.app_factory import build_app

# The exact header value mandated by design OQ1 (REQ-CACHEUX-002).
EXPECTED_CACHE_CONTROL = "public, max-age=60"


def _sign_test_jwt(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str = "test-user",
    email: str = "test@example.com",
) -> str:
    """Sign an ES256 JWT for the test user. The matching public key is
    exposed via the `jwks_keypair` fixture (which also patches the
    JWKS client to return it).
    """
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


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


_FIXTURE_JOB = Job(
    id="linkedin_1",
    title="Python Developer",
    company="Tech Corp",
    location="Madrid, Spain",
    url="https://linkedin.com/jobs/view/1",
    posted_at=datetime(2026, 6, 1, tzinfo=UTC),
    source="linkedin",
)


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    async with (
        LifespanManager(app, startup_timeout=30, shutdown_timeout=30),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


def _make_app_with_fakes(settings: Settings) -> Any:
    """Build an app where all three use cases return an empty list.

    Mirrors the helper in `test_history_api.py` so this test file
    is self-contained — no cross-file test fixtures.
    """
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


class TestJobsHistoryCacheControl:
    """REQ-CACHEUX-002: `Cache-Control: public, max-age=60` on /jobs/history."""

    @pytest.mark.asyncio
    async def test_jobs_history_returns_cache_control_on_200(self) -> None:
        """`GET /jobs/history` 200 carries the Cache-Control header.

        Verbatim value: `public, max-age=60`. NO `s-maxage`, NO
        `stale-while-revalidate` (no CDN deployed; design OQ1).
        """
        settings = Settings(scheduler_enabled=False, db_path=":memory:")
        app = _make_app_with_fakes(settings)

        async with _client_with_lifespan(app) as client:
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None
            await repo.upsert_jobs([_FIXTURE_JOB], query_snapshot={})

            resp = await client.get("/jobs/history")

        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == EXPECTED_CACHE_CONTROL

    @pytest.mark.asyncio
    async def test_jobs_history_by_id_returns_cache_control_on_404(self) -> None:
        """`GET /jobs/history/by-id/{unknown}` 404 carries the Cache-Control.

        Negative cache on 404 is intentional (design rationale:
        bounded by 60s; future change can invalidate by tag if
        needed). Per design OQ1, the SAME header value as 200.
        """
        settings = Settings(scheduler_enabled=False, db_path=":memory:")
        app = _make_app_with_fakes(settings)

        async with _client_with_lifespan(app) as client:
            await client.get("/jobs/history/by-id/does-not-exist")

            resp = await client.get("/jobs/history/by-id/does-not-exist")

        assert resp.status_code == 404
        assert resp.headers.get("cache-control") == EXPECTED_CACHE_CONTROL

    @pytest.mark.asyncio
    async def test_jobs_history_by_id_returns_cache_control_on_200(self) -> None:
        """`GET /jobs/history/by-id/{known}` 200 carries the Cache-Control."""
        settings = Settings(scheduler_enabled=False, db_path=":memory:")
        app = _make_app_with_fakes(settings)

        async with _client_with_lifespan(app) as client:
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None
            await repo.upsert_jobs([_FIXTURE_JOB], query_snapshot={})

            resp = await client.get("/jobs/history/by-id/linkedin_1")

        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == EXPECTED_CACHE_CONTROL

    @pytest.mark.asyncio
    async def test_scheduler_status_does_not_set_cache_control_public(
        self,
        jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    ) -> None:
        """Negative: `/scheduler/status` MUST NOT set the public cache header.

        REQ-CACHEUX-002 only applies to `/jobs/history` and its
        `/by-id` sub-endpoint. The pre-existing `Cache-Control: no-cache`
        in `chat.py` is for SSE — irrelevant here. We assert the
        EXACT value is NOT `public, max-age=60`.
        """
        private_key, _ = jwks_keypair
        settings = Settings(
            scheduler_enabled=True,
            db_path=":memory:",
            scheduler_min_interval_seconds=10000.0,
            scheduler_max_interval_seconds=20000.0,
            scheduler_queries=[{"keywords": "python", "location": "Madrid"}],
            supabase_url="https://test.supabase.co",
        )
        app = _make_app_with_fakes(settings)

        async with _client_with_lifespan(app) as client:
            resp = await client.get(
                "/scheduler/status",
                headers={"Authorization": f"Bearer {_sign_test_jwt(private_key)}"},
            )

        assert resp.status_code == 200
        # Negative assertion: the public cache directive is NOT
        # applied to /scheduler/status (REQ-CACHEUX-002 scope is
        # /jobs/history only). The header may still exist with
        # another value (e.g. "no-cache") — we only assert the
        # specific directive we added in this change is absent.
        assert resp.headers.get("cache-control") != EXPECTED_CACHE_CONTROL
