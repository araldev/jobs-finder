"""Integration tests for the `RATE_LIMIT_ENABLED=False` kill-switch.

Spec: REQ-RL-009 scenario 2 (Disabled → middleware absent from
stack + no headers on response).

When `RATE_LIMIT_ENABLED=false`, the rate limiter is a true
no-op:
  - `RateLimitMiddleware` is NOT added to the app's middleware
    stack (the `if effective_settings.rate_limit_enabled:` guard
    in `app_factory.build_app()` short-circuits the
    `add_middleware` call).
  - Every request returns 200 with NO `X-RateLimit-*` headers —
    no `X-RateLimit-Limit`, no `X-RateLimit-Remaining`, no
    `X-RateLimit-Reset`, no `Retry-After`. The factory returns
    a `NoOpRateLimiter` (covered separately by
    `test_build_rate_limiter_with_disabled_returns_noop`); this
    file pins the APP-level behavior.

The two scenarios are Given/When/Then, observable behavior,
deterministic.
"""

from __future__ import annotations

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
def app_with_rate_limit_disabled(
    monkeypatch: pytest.MonkeyPatch,
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """A FastAPI app with `RATE_LIMIT_ENABLED=false` (middleware absent)."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    settings = Settings(
        rate_limit_enabled=False,
        rate_limit_requests=1,  # would 429 on 2nd call if enabled
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


# ---------------------------------------------------------------------------
# REQ-RL-009 #2 — Disabled → middleware absent from stack
# ---------------------------------------------------------------------------


def test_disabled_middleware_absent_from_stack(
    app_with_rate_limit_disabled: FastAPI,
) -> None:
    """`RATE_LIMIT_ENABLED=false` → `RateLimitMiddleware` NOT in `app.user_middleware`.

    REQ-RL-009 scenario 2: the disabled state is a true no-op at
    the app level — the middleware is not even added to the
    stack. The `if effective_settings.rate_limit_enabled:`
    guard in `app_factory.build_app()` short-circuits the
    `add_middleware` call.

    The test iterates `app.user_middleware` (mirrors
    `test_aggregator_consumes_3_tokens` /
    `test_cost_map_is_immutable_at_runtime` in
    `test_rate_limit_headers.py`) and asserts no entry has
    `cls.__name__ == "RateLimitMiddleware"`. The result is
    structural: the middleware is NOT in the stack, so no
    request can ever be 429'd by it.
    """
    found: Any = None
    for mw in app_with_rate_limit_disabled.user_middleware:
        if getattr(mw.cls, "__name__", None) == "RateLimitMiddleware":
            found = mw
            break
    assert found is None, (
        "RateLimitMiddleware is in app.user_middleware despite "
        "RATE_LIMIT_ENABLED=false — the kill-switch is broken"
    )


# ---------------------------------------------------------------------------
# REQ-RL-009 #2 — Disabled → no `X-RateLimit-*` headers on response
# ---------------------------------------------------------------------------


async def test_disabled_no_rate_limit_headers_on_response(
    app_with_rate_limit_disabled: FastAPI,
) -> None:
    """With `RATE_LIMIT_ENABLED=false`, 100 requests return 200 with no rate-limit headers.

    REQ-RL-009 scenario 2: every request returns 200 and the
    response carries NO `X-RateLimit-Limit`,
    `X-RateLimit-Remaining`, `X-RateLimit-Reset`, or
    `Retry-After` header. Even with
    `rate_limit_requests=1` (which would 429 the 2nd call if
    the middleware were active), all 100 calls return 200 with
    no rate-limit headers — proving the middleware is
    completely absent.
    """
    transport = httpx.ASGITransport(app=app_with_rate_limit_disabled)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        for call_index in range(100):
            response = await ac.get("/jobs/linkedin?keywords=python&location=madrid")
            assert response.status_code == 200, (
                f"call {call_index + 1}: expected 200 (no rate limiting), "
                f"got {response.status_code}"
            )
            # No `X-RateLimit-*` headers on ANY call.
            assert "X-RateLimit-Limit" not in response.headers, (
                f"call {call_index + 1}: X-RateLimit-Limit present"
            )
            assert "X-RateLimit-Remaining" not in response.headers, (
                f"call {call_index + 1}: X-RateLimit-Remaining present"
            )
            assert "X-RateLimit-Reset" not in response.headers, (
                f"call {call_index + 1}: X-RateLimit-Reset present"
            )
            assert "Retry-After" not in response.headers, (
                f"call {call_index + 1}: Retry-After present"
            )
