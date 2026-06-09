"""Integration tests for the SHA256 hashing of the rate-limiter `client_id`.

Spec: REQ-RL-012.

`hash_client_id()` (SHA256 truncated to 16 hex chars) is applied
in `RateLimitMiddleware.dispatch` AFTER `_resolve_client_id()`
and BEFORE `try_acquire(key=...)`. The bucket key is the hash,
NOT the raw IP — both `InMemoryTokenBucket._buckets` dict keys
and `RedisTokenBucket` Redis keys are opaque hashes. PII
sanitization at the HTTP boundary.

The 2 integration scenarios are Given/When/Then, observable
behavior, deterministic.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Generator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

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
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort


def _build_cached_linkedin_use_case(
    port: FakeJobSearchPort,
) -> CachedJobSearchUseCase:
    """Wrap a LinkedIn `FakeJobSearchPort` in a fresh cached wrapper."""
    return SearchLinkedInJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )


def _get_limiter(app: FastAPI) -> Any:
    """Extract the limiter instance from the `RateLimitMiddleware` kwargs."""
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            return mw.kwargs["limiter"]
    raise AssertionError("RateLimitMiddleware not in app.user_middleware")


@pytest.fixture
def make_hashing_app(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> Generator[Any, None, None]:
    """Build a `FastAPI` app for the hashing integration tests.

    Yields a callable that takes a socket-IP tuple and returns
    a fresh app. The rate limiter is the in-memory backend
    (default); capacity is 20 to give plenty of headroom.
    """

    def _factory(socket_client: tuple[str, int]) -> FastAPI:
        settings = Settings(
            rate_limit_requests=20,
            rate_limit_window_seconds=60.0,
        )
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

    yield _factory


# ---------------------------------------------------------------------------
# REQ-RL-012 scenario 5 — `InMemoryTokenBucket._buckets` dict keys are hashes
# ---------------------------------------------------------------------------


async def test_in_memory_dict_key_is_hash_not_raw_ip(
    make_hashing_app: Any,
) -> None:
    """A request from socket IP `1.2.3.4` lands in a bucket whose key is the SHA256 hash.

    REQ-RL-012 scenario 5: the middleware applies
    `hash_client_id(resolved_id)` before `try_acquire`. The
    `InMemoryTokenBucket._buckets` dict key is the hash, not
    the raw IP. The hash matches `re.fullmatch(r"[0-9a-f]{16}", key)`.
    """
    socket_ip = "1.2.3.4"
    app = make_hashing_app(socket_client=(socket_ip, 50000))
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/jobs/linkedin?keywords=python&location=madrid")
        assert response.status_code == 200

    # Exactly 1 bucket was created (the resolved socket IP `1.2.3.4`).
    assert len(limiter._buckets) == 1
    # The key is the SHA256 hash, NOT the raw IP.
    (key,) = limiter._buckets.keys()
    assert key != socket_ip, f"raw IP leaked as bucket key: {key!r}"
    # The key matches the hash format.
    assert re.fullmatch(r"[0-9a-f]{16}", key), f"key is not 16 hex chars: {key!r}"
    # The key equals the canonical SHA256 of the socket IP.
    expected_hash = hashlib.sha256(socket_ip.encode("utf-8")).hexdigest()[:16]
    assert key == expected_hash


# ---------------------------------------------------------------------------
# Bonus integration test — Two distinct IPs produce two distinct hash keys
# ---------------------------------------------------------------------------


async def test_two_distinct_socket_ips_produce_two_distinct_hash_keys(
    make_hashing_app: Any,
) -> None:
    """Two requests with different socket IPs land in two distinct hash buckets.

    The bucket count == 2; the two keys are distinct SHA256
    hashes of the two different socket IPs; neither key is
    equal to its raw IP. This pins the rightmost-untrusted
    resolution + the hashing step in one scenario.
    """
    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"
    app = make_hashing_app(socket_client=(ip_a, 50000))  # initial socket ignored
    limiter = _get_limiter(app)

    # Request 1: socket IP = ip_a.
    transport_a = httpx.ASGITransport(app=app, client=(ip_a, 50000))
    async with httpx.AsyncClient(transport=transport_a, base_url="http://test") as client:
        r1 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
        assert r1.status_code == 200

    # Request 2: socket IP = ip_b (different).
    transport_b = httpx.ASGITransport(app=app, client=(ip_b, 50000))
    async with httpx.AsyncClient(transport=transport_b, base_url="http://test") as client:
        r2 = await client.get("/jobs/linkedin?keywords=python&location=madrid")
        assert r2.status_code == 200

    # Two distinct hash buckets.
    assert len(limiter._buckets) == 2
    keys = set(limiter._buckets.keys())
    assert len(keys) == 2
    # Neither key is the raw IP.
    assert ip_a not in keys
    assert ip_b not in keys
    # Each key matches the SHA256 of its corresponding IP.
    expected_a = hashlib.sha256(ip_a.encode("utf-8")).hexdigest()[:16]
    expected_b = hashlib.sha256(ip_b.encode("utf-8")).hexdigest()[:16]
    assert expected_a in keys
    assert expected_b in keys
