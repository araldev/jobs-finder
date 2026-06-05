"""Integration tests for the TRUSTED_PROXY + X-Forwarded-For parsing.

Spec: REQ-RL-011.

`RateLimitMiddleware` gains a private helper `_resolve_client_id(
request, trusted_proxies)` implementing the **rightmost-untrusted**
algorithm:

  1. Empty `trusted_proxies` or direct untrusted socket IP -> return
     `request.client.host`; IGNORE `X-Forwarded-For` (security
     default; AD-7 in the design).
  2. Socket IP in a trusted CIDR + `X-Forwarded-For` present ->
     walk right-to-left, skip trusted hops, return the first
     untrusted IP.
  3. All hops trusted, header absent, or malformed hop -> fall back
     to `request.client.host`; log WARNING on malformed input.

The 5 scenarios are Given/When/Then, observable behavior, deterministic.

The test seam: `httpx.ASGITransport(client=(ip, port))` sets the
socket IP to a real value (not the default `"testclient"` string)
so the rightmost-untrusted walk can exercise the real algorithm.
Each test inspects `limiter._buckets` keys (a `dict[str, ...]`) to
assert which client_id the middleware resolved.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
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

# Reuse the conftest's `FakeJobSearchPort` class (defined in
# `tests/conftest.py` and consumed by other integration tests).
from tests.conftest import FakeJobSearchPort


def _build_cached_linkedin_use_case(
    port: FakeJobSearchPort,
) -> CachedJobSearchUseCase:
    """Wrap a LinkedIn `FakeJobSearchPort` in a fresh cached wrapper.

    Mirrors the conftest helper but lives in this test file so
    the fixture below is self-contained.
    """
    return SearchLinkedInJobsUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )


def _get_limiter(app: FastAPI) -> Any:
    """Extract the limiter instance from the `RateLimitMiddleware` kwargs in the stack.

    Starlette stores middleware classes + kwargs in `app.user_middleware`
    and constructs the middleware instance lazily on the first request.
    The kwargs include the `limiter=` we passed to `add_middleware`, so
    we can inspect the limiter BEFORE the first request without
    triggering any request-driven side effects.
    """
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            return mw.kwargs["limiter"]
    raise AssertionError("RateLimitMiddleware not in app.user_middleware")


@pytest.fixture
def make_app_with_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> Generator[Callable[[str | None, tuple[str, int]], FastAPI], None, None]:
    """Build a `FastAPI` app with optional `RATE_LIMIT_TRUSTED_PROXIES` env override.

    Usage:
        app = make_app_with_trusted_proxies(
            '["10.0.0.0/8"]', ("10.0.0.1", 50000)
        )
        # -> builds an app with `RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8"]'`
        #    and the TestClient will see a socket IP of `10.0.0.1`.

    The factory clears `RATE_LIMIT_TRUSTED_PROXIES` from the env
    first (so prior tests don't leak) then optionally sets the
    value. The app is built with `rate_limit_requests=20` to give
    plenty of headroom for tests that fire 1-2 requests.
    """
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXIES", raising=False)

    def _factory(
        trusted_proxies_json: str | None,
        socket_client: tuple[str, int],
    ) -> FastAPI:
        if trusted_proxies_json is not None:
            monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", trusted_proxies_json)
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
# REQ-RL-011 scenario 1 — Empty trusted_proxies ignores X-Forwarded-For
# ---------------------------------------------------------------------------


async def test_trusted_proxies_empty_ignores_xff(
    make_app_with_trusted_proxies: Any,
) -> None:
    """Default `RATE_LIMIT_TRUSTED_PROXIES=[]` ignores XFF; socket IP is the bucket key.

    REQ-RL-011 scenario 1: with `trusted_proxies` empty (the
    security default), the middleware uses `request.client.host`
    and IGNORES the `X-Forwarded-For` header. Two requests with
    different `X-Forwarded-For` values land in the SAME bucket
    (the socket IP), NOT in separate buckets per the spoofed IP.
    """
    socket_ip = "203.0.113.5"
    app = make_app_with_trusted_proxies(
        trusted_proxies_json=None,  # unset -> defaults to frozenset()
        socket_client=(socket_ip, 50000),
    )
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        r2 = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "5.6.7.8"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200

    # Both requests landed in the SAME bucket (the socket IP).
    # The spoofed XFF IPs are NOT in the bucket.
    assert len(limiter._buckets) == 1
    assert socket_ip in limiter._buckets
    assert "1.2.3.4" not in limiter._buckets
    assert "5.6.7.8" not in limiter._buckets


# ---------------------------------------------------------------------------
# REQ-RL-011 scenario 2 — Socket IP NOT in trusted CIDR ignores XFF
# ---------------------------------------------------------------------------


async def test_socket_ip_not_in_trusted_cidr_ignores_xff(
    make_app_with_trusted_proxies: Any,
) -> None:
    """When socket IP is NOT in any trusted CIDR, XFF is ignored.

    REQ-RL-011 scenario 2: a direct connection from an untrusted
    IP cannot claim to be behind a proxy. With
    `RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8"]'` and socket IP
    `203.0.113.5` (NOT in `10.0.0.0/8`), the middleware uses
    the socket IP and IGNORES `X-Forwarded-For`.
    """
    socket_ip = "203.0.113.5"
    app = make_app_with_trusted_proxies(
        trusted_proxies_json='["10.0.0.0/8"]',
        socket_client=(socket_ip, 50000),
    )
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        r2 = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "5.6.7.8"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200

    # Both requests landed in the SAME bucket (the socket IP),
    # not in separate buckets per the spoofed XFF.
    assert len(limiter._buckets) == 1
    assert socket_ip in limiter._buckets
    assert "1.2.3.4" not in limiter._buckets


# ---------------------------------------------------------------------------
# REQ-RL-011 scenario 3 — Trusted socket IP, 3-hop rightmost-untrusted
# ---------------------------------------------------------------------------


async def test_trusted_socket_ip_resolves_rightmost_untrusted_hop(
    make_app_with_trusted_proxies: Any,
) -> None:
    """When socket IP is in a trusted CIDR, XFF is parsed right-to-left.

    REQ-RL-011 scenario 3: with socket IP `10.0.0.1` in the
    trusted CIDR `10.0.0.0/8` and
    `X-Forwarded-For: "1.2.3.4, 5.6.7.8, 9.10.11.12"` (the latter
    2 hops also trusted), the helper walks right-to-left and
    returns `"1.2.3.4"` (the leftmost untrusted hop — the
    "original client" per the rightmost-untrusted convention).
    """
    socket_ip = "10.0.0.1"
    app = make_app_with_trusted_proxies(
        trusted_proxies_json='["10.0.0.0/8", "5.6.7.8/32", "9.10.11.12/32"]',
        socket_client=(socket_ip, 50000),
    )
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.10.11.12"},
        )
        assert response.status_code == 200

    # The bucket key is the leftmost untrusted hop ("1.2.3.4"),
    # NOT the socket IP and NOT any of the trusted proxies.
    assert len(limiter._buckets) == 1
    assert "1.2.3.4" in limiter._buckets
    assert socket_ip not in limiter._buckets
    assert "5.6.7.8" not in limiter._buckets
    assert "9.10.11.12" not in limiter._buckets


# ---------------------------------------------------------------------------
# REQ-RL-011 scenario 4 — All hops trusted -> fall back to socket IP
# ---------------------------------------------------------------------------


async def test_all_hops_trusted_falls_back_to_socket_ip(
    make_app_with_trusted_proxies: Any,
) -> None:
    """When all XFF hops are in trusted CIDRs, fall back to socket IP.

    REQ-RL-011 scenario 4: with `X-Forwarded-For: "10.0.0.5,
    10.0.0.6"` (both in `10.0.0.0/8`, all hops trusted), the
    rightmost-untrusted walk finds NO untrusted hop and falls
    back to the socket IP.
    """
    socket_ip = "10.0.0.1"
    app = make_app_with_trusted_proxies(
        trusted_proxies_json='["10.0.0.0/8"]',
        socket_client=(socket_ip, 50000),
    )
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/jobs/linkedin?keywords=python&location=madrid",
            headers={"X-Forwarded-For": "10.0.0.5, 10.0.0.6"},
        )
        assert response.status_code == 200

    # All hops are trusted; the helper falls back to the socket IP.
    assert len(limiter._buckets) == 1
    assert socket_ip in limiter._buckets
    assert "10.0.0.5" not in limiter._buckets
    assert "10.0.0.6" not in limiter._buckets


# ---------------------------------------------------------------------------
# REQ-RL-011 scenario 5 — Malformed XFF hop -> WARNING + fall back to socket IP
# ---------------------------------------------------------------------------


async def test_malformed_xff_hop_logs_warning_and_falls_back(
    make_app_with_trusted_proxies: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When an XFF hop is malformed, log WARNING and fall back to socket IP.

    REQ-RL-011 scenario 5: a hop like `"not-an-ip"` causes
    `ipaddress.ip_address(hop)` to raise `ValueError`. The
    helper logs a WARNING (so ops can spot misconfigured
    proxies) and falls back to the socket IP.
    """
    socket_ip = "10.0.0.1"
    app = make_app_with_trusted_proxies(
        trusted_proxies_json='["10.0.0.0/8"]',
        socket_client=(socket_ip, 50000),
    )
    limiter = _get_limiter(app)

    transport = httpx.ASGITransport(app=app, client=(socket_ip, 50000))
    with caplog.at_level(logging.WARNING, logger="jobs_finder.presentation.middleware"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/jobs/linkedin?keywords=python&location=madrid",
                headers={"X-Forwarded-For": "not-an-ip"},
            )
            assert response.status_code == 200

    # The bucket falls back to the socket IP (the malformed hop is NOT
    # in any bucket; the warning is logged and we return socket_ip).
    assert len(limiter._buckets) == 1
    assert socket_ip in limiter._buckets
    # The WARNING was logged with the bad hop value so ops can debug.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, "expected at least one WARNING log record"
    # At least one warning mentions the malformed hop OR the XFF header.
    warning_text = " ".join(r.getMessage() for r in warning_records)
    assert "not-an-ip" in warning_text or "X-Forwarded-For" in warning_text or "XFF" in warning_text
