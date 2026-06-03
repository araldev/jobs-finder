"""Integration tests for the 502 + X-Cache: MISS header contract.

Spec: REQ-C-003 3rd scenario (per the cache-ttl verify report WARNING #1).
A 502 response from any of the 3 source routes MUST include the
`X-Cache: MISS` header. A 502 in this design always implies a fresh
MISS — cache hits short-circuit before the port runs and a port
exception propagates to the handler without being cached (REQ-C-006).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
from jobs_finder.domain.exceptions import (
    JobSearchError,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.indeed.exceptions import (
    IndeedBlockedError,
    IndeedParseError,
    IndeedTimeoutError,
)
from jobs_finder.infrastructure.infojobs.exceptions import (
    InfoJobsBlockedError,
    InfoJobsParseError,
)
from jobs_finder.infrastructure.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInParseError,
    LinkedInTimeoutError,
)
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app_with_error(error: JobSearchError) -> FastAPI:
    """Build a `FastAPI` whose 3 use cases all raise the given error.

    The fake ports are primed with `error=...` so the FIRST
    `search()` call raises. Each source gets a fresh
    `InMemoryTTLCache` (no shared state across tests). Cache is
    irrelevant for these tests because the error is raised before
    the cache can be consulted (the wrapper does `cache.get` first
    which returns `None` → then calls `port.search()` → exception
    propagates → response is 502 with `X-Cache: MISS`).
    """
    linkedin_port = FakeJobSearchPort(error=error)
    indeed_port = FakeJobSearchPort(error=error)
    infojobs_port = FakeJobSearchPort(error=error)
    return build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=linkedin_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
        indeed_use_case=IndeedSearchJobsUseCase(
            port=indeed_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="indeed",
        ),
        infojobs_use_case=InfoJobsSearchJobsUseCase(
            port=infojobs_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="infojobs",
        ),
    )


def _build_cached_use_case(port: FakeJobSearchPort, source: str) -> CachedJobSearchUseCase:
    """Wrap a `FakeJobSearchPort` in a `CachedJobSearchUseCase` with a fresh cache.

    Mirror of `tests.conftest._build_cached_linkedin_use_case` for
    the 3 sources. Each test gets a clean cache.
    """
    cls = {
        "linkedin": SearchLinkedInJobsUseCase,
        "indeed": IndeedSearchJobsUseCase,
        "infojobs": InfoJobsSearchJobsUseCase,
    }[source]
    return cls(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source=source,
    )


# Reference the helper so the linter doesn't flag it (used by other tests).
_ = _build_cached_use_case


# ---------------------------------------------------------------------------
# LinkedIn 502 + X-Cache: MISS
# ---------------------------------------------------------------------------


async def test_502_on_linkedin_blocked_includes_x_cache_miss() -> None:
    """`GET /jobs/linkedin` returning 502 includes `X-Cache: MISS`."""
    app = _build_app_with_error(LinkedInBlockedError("auth wall"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


async def test_502_on_linkedin_parse_error_includes_x_cache_miss() -> None:
    """A 502 from a LinkedIn parser error also includes `X-Cache: MISS`."""
    app = _build_app_with_error(LinkedInParseError("zero cards on first page"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


async def test_502_on_linkedin_timeout_includes_x_cache_miss() -> None:
    """A 502 from a LinkedIn timeout also includes `X-Cache: MISS`."""
    app = _build_app_with_error(LinkedInTimeoutError("timeout"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


# ---------------------------------------------------------------------------
# Indeed 502 + X-Cache: MISS
# ---------------------------------------------------------------------------


async def test_502_on_indeed_blocked_includes_x_cache_miss() -> None:
    """`GET /jobs/indeed` returning 502 includes `X-Cache: MISS`."""
    app = _build_app_with_error(IndeedBlockedError("cloudflare"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


async def test_502_on_indeed_parse_error_includes_x_cache_miss() -> None:
    """A 502 from an Indeed parser error also includes `X-Cache: MISS`."""
    app = _build_app_with_error(IndeedParseError("zero cards on first page"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


# ---------------------------------------------------------------------------
# InfoJobs 502 + X-Cache: MISS
# ---------------------------------------------------------------------------


async def test_502_on_infojobs_blocked_includes_x_cache_miss() -> None:
    """`GET /jobs/infojobs` returning 502 (Distil/Geetest) includes `X-Cache: MISS`."""
    app = _build_app_with_error(InfoJobsBlockedError("distil"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


async def test_502_on_infojobs_parse_error_includes_x_cache_miss() -> None:
    """A 502 from an InfoJobs parser error also includes `X-Cache: MISS`."""
    app = _build_app_with_error(InfoJobsParseError("zero cards on first page"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"


# ---------------------------------------------------------------------------
# Cache miss path is consistent across the 3 sources (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("/jobs/linkedin", LinkedInBlockedError("auth wall")),
        ("/jobs/linkedin", LinkedInParseError("zero cards")),
        ("/jobs/indeed", IndeedBlockedError("cloudflare")),
        ("/jobs/indeed", IndeedTimeoutError("timeout")),
        ("/jobs/infojobs", InfoJobsBlockedError("distil")),
        ("/jobs/infojobs", InfoJobsParseError("zero cards")),
    ],
)
async def test_502_includes_x_cache_miss_for_all_sources_and_errors(
    path: str, error: JobSearchError
) -> None:
    """Every 502 from any of the 3 sources (any error subclass) includes `X-Cache: MISS`.

    Parametrized over the 3 sources × 2 error subclasses per source
    = 6 invocations. Together with the 7 explicit tests above,
    this covers every error subclass on every source.
    """
    app = _build_app_with_error(error)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{path}?keywords=python&location=madrid&limit=5")
    assert response.status_code == 502
    assert response.headers["x-cache"] == "MISS"
    # The body still uses the masked detail + request_id (per REQ-020)
    body = response.json()
    assert body["detail"] == "upstream source unavailable"
    assert body["request_id"]  # non-empty
