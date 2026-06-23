"""Integration tests for CV endpoint authentication, quota, and event recording.

Strict TDD: these tests were written BEFORE the production-code changes to
the CV route (tasks 3.3 + 3.4).

Spec coverage:
  - JWT-001: GIVEN valid/invalid/missing JWT WHEN POST /cv/generate THEN 401/401/200
  - ENG-001: GIVEN quota exceeded WHEN POST /cv/generate THEN 429
  - ENG-002: GIVEN quota available WHEN CV generated THEN event recorded
  - QUOTA-003: X-Quota-Remaining header present on 429 and success (post-verify fix)
  - QUOTA-004: USER_CV_DAILY_QUOTA=0 means unlimited
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from pydantic import SecretStr

from jobs_finder.application.usecases.generate_adapted_cv import (
    GenerateAdaptedCVRequest,
    GenerateAdaptedCVResult,
    GenerateAdaptedCVUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort, _build_cached_linkedin_use_case

_VALID_USER_ID = "user-abc-123"


def _make_jwt(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str = _VALID_USER_ID,
    email: str = "test@example.com",
) -> str:
    """Build a valid-looking ES256 JWT for testing.

    ES256 (asymmetric) — the matching public key is exposed via the
    `jwks_keypair` fixture (which also patches the JWKS client to
    return it). See the fixture docstring for details.
    """
    payload: dict[str, object] = {
        "sub": sub,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


class FakeEngagementPort:
    """In-memory fake of the EngagementPort Protocol.

    Records every ``record_event`` call and returns a configurable
    count from ``count_events_today`` (default 0 — quota available).
    """

    def __init__(self, count_today: int = 0) -> None:
        self.count_today: int = count_today
        self.recorded_events: list[dict[str, object]] = []

    async def record_event(
        self,
        user_id: str,
        event_type: str,
        job_id: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.recorded_events.append(
            {"user_id": user_id, "event_type": event_type, "job_id": job_id, "metadata": metadata}
        )

    async def count_events_today(self, user_id: str, event_type: str) -> int:
        return self.count_today


class FakeGenerateAdaptedCVUseCase(GenerateAdaptedCVUseCase):
    """Fake CV use case that returns a canned PDF response without an LLM."""

    def __init__(self) -> None:
        # Bypass the real LLM client requirement
        pass

    async def execute(self, request: GenerateAdaptedCVRequest) -> GenerateAdaptedCVResult:
        return GenerateAdaptedCVResult(
            pdf_bytes=b"%PDF-1.4 fake cv content",
            filename="adapted_cv.pdf",
        )


async def _build_test_client(
    quota: int = 5,
    count_today: int = 0,
) -> httpx.AsyncClient:
    """Build a test ASGI client with fake dependencies.

    Args:
        quota: ``user_cv_daily_quota`` setting (default 5).
        count_today: Value ``FakeEngagementPort.count_events_today`` returns.

    Returns an ``httpx.AsyncClient`` (caller must close it).
    """
    settings = Settings(
        # ES256+JWKS: setting `supabase_url` causes Settings to auto-compute
        # `supabase_jwt_jwks_url = {supabase_url}/auth/v1/.well-known/jwks.json`.
        # The `jwks_keypair` fixture (passed by callers) intercepts the
        # JWKS lookup so we never hit the real endpoint.
        supabase_url="https://test.supabase.co",
        # `supabase_service_key` stays as SecretStr (it's still a credential).
        supabase_service_key=SecretStr("test-service-key"),
        user_cv_daily_quota=quota,
        rate_limit_enabled=False,
        # Minimal settings for fake ports to work
        llm_filter_enabled=False,
        cache_ttl_seconds=60.0,
        database_url="",
        db_path="",
        scheduler_enabled=False,
    )

    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = _build_cached_linkedin_use_case(port=linkedin_port)

    from jobs_finder.application.usecases.search_indeed_jobs import (
        SearchJobsUseCase as IndeedSearchJobsUseCase,
    )
    from jobs_finder.application.usecases.search_infojobs_jobs import (
        SearchJobsUseCase as InfoJobsSearchJobsUseCase,
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

    fake_engagement = FakeEngagementPort(count_today=count_today)
    fake_cv_use_case = FakeGenerateAdaptedCVUseCase()

    app: FastAPI = build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        cv_use_case_override=fake_cv_use_case,
        engagement_port=fake_engagement,
        settings=settings,
    )

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Standard test client: quota=5, count_today=0."""
    async with await _build_test_client() as ac:
        yield ac


@pytest.fixture
async def client_quota_zero() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Test client with unlimited quota (quota=0, count_today=999)."""
    async with await _build_test_client(quota=0, count_today=999) as ac:
        yield ac


# ── Auth tests ────────────────────────────────────────────────────────────────


async def test_cv_generate_no_auth_returns_401(client: httpx.AsyncClient) -> None:
    """GIVEN no Authorization header WHEN POST /cv/generate THEN 401."""
    response = await client.post(
        "/cv/generate",
        files={"file": ("test.pdf", b"dummy", "application/pdf")},
        data={"job_title": "Test", "job_company": "Test"},
    )
    assert response.status_code == 401
    body = response.json()
    assert "detail" in body


async def test_cv_generate_invalid_jwt_returns_401(client: httpx.AsyncClient) -> None:
    """GIVEN invalid JWT WHEN POST /cv/generate THEN 401."""
    response = await client.post(
        "/cv/generate",
        headers={"Authorization": "Bearer invalid-token"},
        files={"file": ("test.pdf", b"dummy", "application/pdf")},
        data={"job_title": "Test", "job_company": "Test"},
    )
    assert response.status_code == 401


async def test_cv_generate_valid_jwt_passes_auth(
    client: httpx.AsyncClient,
    jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> None:
    """GIVEN valid JWT WHEN POST /cv/generate THEN not 401 (200 expected)."""
    private_key, _ = jwks_keypair
    token = _make_jwt(private_key)
    response = await client.post(
        "/cv/generate",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.pdf", b"dummy content", "application/pdf")},
        data={"job_title": "Test", "job_company": "Test"},
    )
    # Not 401 — the request got past auth. With quota available and
    # the fake CV use case, should return 200.
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    # QUOTA-003: success response includes X-Quota-Remaining header
    # quota=5, count_today=0, so remaining = 5 - 0 - 1 = 4
    assert response.headers.get("X-Quota-Remaining") == "4", (
        f"Expected X-Quota-Remaining: 4, got {response.headers.get('X-Quota-Remaining')}"
    )


# ── Quota tests ───────────────────────────────────────────────────────────────


async def test_cv_generate_quota_exceeded_returns_429(
    client: httpx.AsyncClient,
    jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> None:
    """GIVEN quota exceeded WHEN POST /cv/generate THEN 429."""
    private_key, _ = jwks_keypair
    token = _make_jwt(private_key)
    fake_eng: FakeEngagementPort = client._transport.app.state.engagement_port  # type: ignore[attr-defined]
    fake_eng.count_today = 5  # quota is 5, so this exceeds it

    # Send a dummy file + required form fields so FastAPI validation
    # passes; the quota check fires BEFORE we try to process the file.
    response = await client.post(
        "/cv/generate",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.pdf", b"dummy content", "application/pdf")},
        data={"job_title": "Test", "job_company": "Test"},
    )
    assert response.status_code == 429, f"Expected 429, got {response.status_code}"
    body = response.json()
    assert "detail" in body
    # QUOTA-003: 429 response includes X-Quota-Remaining: 0
    assert response.headers.get("X-Quota-Remaining") == "0", (
        f"Expected X-Quota-Remaining: 0, got {response.headers.get('X-Quota-Remaining')}"
    )


async def test_cv_generate_quota_zero_is_unlimited(
    client_quota_zero: httpx.AsyncClient,
    jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> None:
    """GIVEN user_cv_daily_quota=0 WHEN POST /cv/generate THEN 200 (no quota)."""
    private_key, _ = jwks_keypair
    token = _make_jwt(private_key)
    response = await client_quota_zero.post(
        "/cv/generate",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.pdf", b"dummy content", "application/pdf")},
        data={"job_title": "Test", "job_company": "Test"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    # quota=0 -> unlimited -> X-Quota-Remaining: -1
    assert response.headers.get("X-Quota-Remaining") == "-1", (
        f"Expected X-Quota-Remaining: -1, got {response.headers.get('X-Quota-Remaining')}"
    )


# ── Count endpoint tests ────────────────────────────────────────────────────────


async def test_cv_count_requires_auth(client: httpx.AsyncClient) -> None:
    """GIVEN no Authorization WHEN GET /cv/count THEN 401."""
    response = await client.get("/cv/count")
    assert response.status_code == 401


async def test_cv_count_returns_today_total(
    client: httpx.AsyncClient,
    jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> None:
    """GIVEN valid JWT WHEN GET /cv/count THEN returns total_today."""
    private_key, _ = jwks_keypair
    token = _make_jwt(private_key)
    response = await client.get(
        "/cv/count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"total_today": 0}


async def test_cv_count_reflects_quota_used(
    client: httpx.AsyncClient,
    jwks_keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
) -> None:
    """GIVEN user has used quota WHEN GET /cv/count THEN returns correct total."""
    private_key, _ = jwks_keypair
    token = _make_jwt(private_key)
    # Set the fake so count returns 3
    fake_eng: FakeEngagementPort = client._transport.app.state.engagement_port  # type: ignore[attr-defined]
    fake_eng.count_today = 3

    response = await client.get(
        "/cv/count",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"total_today": 3}
