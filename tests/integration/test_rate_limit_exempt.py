"""Integration tests for the `RateLimitMiddleware` exempt paths.

Spec: REQ-RL-007 (exempt paths — default list, docs surface, env-var override, no headers).

`/health` is in `EXEMPT_UNCONDITIONAL` (hardcoded in the middleware) so
the k8s liveness probe never 429s the pod. `/docs`, `/openapi.json`,
and `/redoc` are appended to the effective exempt set by
`app_factory` so a `curl /docs` does not consume the bucket. All
exempt responses MUST NOT carry any `X-RateLimit-*` / `Retry-After`
header.

The scenarios are Given/When/Then, observable behavior, deterministic:

  - 4 default-list / docs-surface scenarios (existing).
  - 1 env-var override scenario: REQ-RL-007 #5 (T-005 follow-up).
  - 1 "exempt check runs FIRST / no bucket mutation" scenario:
    REQ-RL-007 #7 (T-005 follow-up).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.presentation.app_factory import build_app

# `FakeJobSearchPort` and `_build_cached_linkedin_use_case` are defined in
# `tests/conftest.py` and shared across the integration test files. Importing
# from conftest (rather than redefining them locally) is the project's pattern
# for the env-var override test below.
from tests.conftest import (  # noqa: E402
    FakeJobSearchPort,
    _build_cached_linkedin_use_case,
)


@pytest.fixture
async def client(app_with_rate_limit: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app with rate limiting."""
    transport = httpx.ASGITransport(app=app_with_rate_limit)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-RL-007 — /health exempt (default)
# ---------------------------------------------------------------------------


async def test_health_is_exempt_by_default_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """11 back-to-back `GET /health` calls all return 200 with no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 1: `/health` exempt by default. The bucket
    is sized to `rate_limit_requests=2` (per the fixture), so a
    normal route would 429 on the 3rd call. `/health` is exempt
    and bypasses the limiter entirely (no `try_acquire` call, no
    `X-RateLimit-*` headers).
    """
    for _ in range(11):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        # No `X-RateLimit-*` headers on exempt responses.
        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers
        assert "X-RateLimit-Reset" not in response.headers
        assert "Retry-After" not in response.headers


# ---------------------------------------------------------------------------
# REQ-RL-007 — /docs, /openapi.json, /redoc exempt (app_factory appends)
# ---------------------------------------------------------------------------


async def test_docs_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /docs` (FastAPI Swagger UI) is exempt — 200, no `X-RateLimit-*` headers.

    The default branch of `app_factory` unions
    `frozenset({"/docs", "/openapi.json", "/redoc"})` into the
    effective exempt set, so a `curl /docs` does not consume
    the bucket. REQ-RL-007 scenario 2.
    """
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


async def test_openapi_json_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /openapi.json` is exempt — 200, no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 3. The schema endpoint is part of the
    FastAPI docs surface and is unconditionally exempt.
    """
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


async def test_redoc_is_exempt_returns_200_without_headers(
    client: httpx.AsyncClient,
) -> None:
    """`GET /redoc` (FastAPI ReDoc UI) is exempt — 200, no `X-RateLimit-*` headers.

    REQ-RL-007 scenario 4. The redoc endpoint is part of the
    FastAPI docs surface and is unconditionally exempt.
    """
    response = await client.get("/redoc")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


# ---------------------------------------------------------------------------
# REQ-RL-007 #5 — `RATE_LIMIT_EXEMPT_PATHS` JSON override (T-005 follow-up)
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_rate_limit_exempt_override(
    monkeypatch: pytest.MonkeyPatch,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """A FastAPI app with `RATE_LIMIT_EXEMPT_PATHS` overridden via env var.

    Sets `RATE_LIMIT_EXEMPT_PATHS='["/health","/internal/ping"]'` so
    the env-var override path is exercised. The settings also set
    `rate_limit_requests=1` (so a non-exempt path 429s on the 2nd
    call, making the contrast between exempt and non-exempt
    observable in a single test).
    """
    monkeypatch.setenv("RATE_LIMIT_EXEMPT_PATHS", '["/health", "/internal/ping"]')
    settings = Settings(rate_limit_requests=1, rate_limit_window_seconds=60.0)

    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(
        port=fake_indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=fake_infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings,
    )


async def test_ratelimit_exempt_paths_env_override(
    app_with_rate_limit_exempt_override: FastAPI,
) -> None:
    """REQ-RL-007 #5: an env-var override actually exempts a new path end-to-end.

    The settings test pins that `RATE_LIMIT_EXEMPT_PATHS` is
    PARSED as a JSON list. This test pins the END-TO-END
    behavior: a path that is NOT in the default
    `frozenset({"/health"})` IS exempt when added via the env
    var. With `rate_limit_requests=1`:

      - `GET /health` returns 200 with no `X-RateLimit-*` headers
        (default + override; either way exempt).
      - `GET /internal/ping` returns 404 (the route is not
        registered, so Starlette returns 404 from the route
        layer) BUT no `X-RateLimit-*` headers are set
        (the env-var override made the path exempt at the
        middleware layer; the route 404 is incidental).
      - `GET /jobs/linkedin` is NOT in the override; with
        `rate_limit_requests=1`, the 1st call returns 200 with
        `X-RateLimit-*` headers (consumed the only token) and
        the 2nd call returns 429 (bucket exhausted).
    """
    transport = httpx.ASGITransport(app=app_with_rate_limit_exempt_override)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # `/health` is exempt (default + override).
        r_health = await ac.get("/health")
        assert r_health.status_code == 200
        assert "X-RateLimit-Limit" not in r_health.headers
        assert "X-RateLimit-Remaining" not in r_health.headers
        assert "X-RateLimit-Reset" not in r_health.headers

        # `/internal/ping` is exempt via the env-var override.
        # The route is not registered, so the response is 404 —
        # but the middleware did NOT consume a token (no
        # `X-RateLimit-*` headers, no `Retry-After`).
        r_ping = await ac.get("/internal/ping")
        assert r_ping.status_code == 404
        assert "X-RateLimit-Limit" not in r_ping.headers
        assert "X-RateLimit-Remaining" not in r_ping.headers
        assert "X-RateLimit-Reset" not in r_ping.headers
        assert "Retry-After" not in r_ping.headers

        # `/jobs/linkedin` is NOT exempt: 1st call consumes the
        # only token, 2nd call 429s. The presence of the
        # `X-RateLimit-*` headers proves the middleware ran
        # (i.e. the path is NOT in the exempt set).
        r_jobs1 = await ac.get("/jobs/linkedin?keywords=python&location=madrid")
        assert r_jobs1.status_code == 200
        assert r_jobs1.headers["X-RateLimit-Limit"] == "1"
        assert r_jobs1.headers["X-RateLimit-Remaining"] == "0"

        r_jobs2 = await ac.get("/jobs/linkedin?keywords=python&location=madrid")
        assert r_jobs2.status_code == 429
        assert "Retry-After" in r_jobs2.headers


# ---------------------------------------------------------------------------
# REQ-RL-007 #7 — Exempt check runs FIRST (no bucket mutation, T-005 follow-up)
# ---------------------------------------------------------------------------


async def test_exempt_path_does_not_touch_bucket(
    app_with_rate_limit: FastAPI,
) -> None:
    """REQ-RL-007 #7: the exempt check runs FIRST — `try_acquire` is NEVER called.

    The 11 back-to-back /health tests IMPLICITLY verify this (if
    the exempt check ran after the bucket check, /health would
    429 on the 3rd call). This test makes the invariant EXPLICIT
    by snapshotting the limiter's `_buckets` dict before and
    after a /health call: the snapshot is identical, proving
    the middleware short-circuited before the limiter.

    The test consumes the bucket first (2 calls to /jobs/linkedin)
    so the limiter has a real `(tokens=0, last_refill_at=...)`
    entry for the testclient host. The 50 /health calls then
    confirm the limiter's state is UNCHANGED — the entry for
    the testclient host still has `tokens=0` and a non-empty
    `_buckets` dict (no new keys were created).

    The limiter is reached via `app.user_middleware` introspection
    (mirrors `test_aggregator_consumes_3_tokens` in
    `test_rate_limit_headers.py`): the `limiter` kwarg of the
    `RateLimitMiddleware` factory is the `InMemoryTokenBucket`
    instance the middleware will use.
    """
    # Reach the limiter via the middleware's kwargs (the same
    # pattern as `test_aggregator_consumes_3_tokens`).
    found: Any = None
    for mw in app_with_rate_limit.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            found = mw
            break
    assert found is not None, "RateLimitMiddleware not in app.user_middleware"
    limiter: InMemoryTokenBucket = found.kwargs["limiter"]
    assert isinstance(limiter, InMemoryTokenBucket)

    transport = httpx.ASGITransport(app=app_with_rate_limit)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # Consume the bucket so the limiter has a real per-key
        # entry. With `rate_limit_requests=2`, the 3rd call would
        # 429 — but for THIS test we only care that the entry
        # exists, not that it's exhausted.
        await ac.get("/jobs/linkedin?keywords=python&location=madrid")
        await ac.get("/jobs/linkedin?keywords=python&location=madrid")

        # Snapshot the limiter's internal state.
        buckets_before = dict(limiter._buckets)
        assert len(buckets_before) >= 1, (
            "expected at least 1 bucket entry after /jobs/linkedin calls"
        )

        # 50 /health calls. If the exempt check runs SECOND (after
        # the bucket check), each call would call `try_acquire`
        # which would either decrement the bucket or return a 429
        # (and the 3rd+ call WOULD 429 since the bucket is at 0).
        for _ in range(50):
            response = await ac.get("/health")
            assert response.status_code == 200

        # The limiter's state is UNCHANGED — no `try_acquire` was
        # called for any /health request.
        buckets_after = dict(limiter._buckets)
        assert buckets_after == buckets_before, (
            "expected the exempt check to short-circuit before "
            "touching the bucket; bucket state was mutated"
        )
