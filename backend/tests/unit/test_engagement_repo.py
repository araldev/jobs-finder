"""Unit tests for the Supabase Engagement Repository (tasks 5.2 / 2.2 + 2.3).

Strict TDD: these tests were written BEFORE the production code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobs_finder.infrastructure.engagement._supabase import (
    SupabaseEngagementRepository,
)


class TestSupabaseEngagementRepository:
    """Tests for `SupabaseEngagementRepository`.

    Spec scenarios (ENG-001, ENG-002):
      - GIVEN user generates CV WHEN record_event called THEN POST to Supabase
      - GIVEN user has events today WHEN count_events_today called THEN return count
      - GIVEN Supabase is unreachable WHEN record_event called THEN no crash (best-effort)
      - GIVEN Supabase returns error WHEN count_events_today called THEN return 0 (best-effort)
    """

    _SUPABASE_URL = "https://test.supabase.co"
    _SERVICE_KEY = "test-service-key"

    def _repo(self) -> SupabaseEngagementRepository:
        return SupabaseEngagementRepository(
            supabase_url=self._SUPABASE_URL,
            service_key=self._SERVICE_KEY,
        )

    def _mock_async_client(self) -> MagicMock:
        """Build a mock that can be used as `httpx.AsyncClient` (async CM).

        Usage:
            mock = self._mock_async_client()
            with patch("httpx.AsyncClient", return_value=mock):
                ...
        """
        mock = MagicMock()
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=None)
        return mock

    # ── record_event tests ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_record_event_calls_supabase_post(self) -> None:
        """GIVEN record_event called WHEN Supabase responds 201 THEN no error."""
        repo = self._repo()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 201

        mock = self._mock_async_client()
        mock.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock):
            await repo.record_event(
                user_id="user-123",
                event_type="cv_adapted",
                job_id=42,
                metadata={"source": "test"},
            )

        mock.post.assert_called_once()
        url = mock.post.call_args[0][0]
        json_body = mock.post.call_args[1]["json"]
        headers = mock.post.call_args[1]["headers"]

        assert url == f"{self._SUPABASE_URL}/rest/v{1}/user_engagement"
        assert json_body["user_id"] == "user-123"
        assert json_body["event_type"] == "cv_adapted"
        assert json_body["job_id"] == 42
        assert json_body["metadata"] == {"source": "test"}
        assert "created_at" in json_body
        assert headers["apikey"] == self._SERVICE_KEY
        assert headers["Authorization"] == f"Bearer {self._SERVICE_KEY}"

    @pytest.mark.asyncio
    async def test_record_event_minimal(self) -> None:
        """GIVEN record_event without optional args WHEN called THEN minimal body."""
        repo = self._repo()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 201

        mock = self._mock_async_client()
        mock.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock):
            await repo.record_event(user_id="user-123", event_type="search")

        json_body = mock.post.call_args[1]["json"]
        assert json_body["user_id"] == "user-123"
        assert json_body["event_type"] == "search"
        assert json_body.get("job_id") is None
        assert json_body.get("metadata") is None

    @pytest.mark.asyncio
    async def test_record_event_supabase_unreachable(self) -> None:
        """GIVEN Supabase unreachable WHEN record_event THEN no crash (best-effort)."""
        repo = self._repo()

        mock = self._mock_async_client()
        mock.post = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock):
            # Should NOT raise — best-effort contract
            await repo.record_event(user_id="user-123", event_type="cv_adapted")

    # ── count_events_today tests ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_count_events_today_calls_supabase_get(self) -> None:
        """GIVEN count_events_today WHEN called THEN GET with count query."""
        repo = self._repo()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"count": 3}]

        mock = self._mock_async_client()
        mock.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock):
            count = await repo.count_events_today(
                user_id="user-123", event_type="cv_adapted"
            )

        assert count == 3

        get_call = mock.get.call_args
        url = get_call[0][0]
        params = get_call[1]["params"]
        headers = get_call[1]["headers"]

        assert url == f"{self._SUPABASE_URL}/rest/v{1}/user_engagement"
        assert "user_id" in str(params)
        assert "event_type" in str(params)
        assert "created_at" in str(params)
        assert headers["apikey"] == self._SERVICE_KEY
        assert headers["Authorization"] == f"Bearer {self._SERVICE_KEY}"

    @pytest.mark.asyncio
    async def test_count_events_today_returns_zero_on_error(self) -> None:
        """GIVEN Supabase error WHEN count_events_today THEN return 0 (best-effort)."""
        repo = self._repo()

        mock = self._mock_async_client()
        mock.get = AsyncMock(side_effect=Exception("Timeout"))

        with patch("httpx.AsyncClient", return_value=mock):
            count = await repo.count_events_today(
                user_id="user-123", event_type="cv_adapted"
            )

        assert count == 0

    @pytest.mark.asyncio
    async def test_count_events_today_empty_response(self) -> None:
        """GIVEN no matching events WHEN count_events_today THEN return 0."""
        repo = self._repo()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        mock = self._mock_async_client()
        mock.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock):
            count = await repo.count_events_today(
                user_id="user-123", event_type="cv_adapted"
            )

        assert count == 0

    @pytest.mark.asyncio
    async def test_count_events_today_non_200(self) -> None:
        """GIVEN non-200 response WHEN count_events_today THEN return 0 (best-effort)."""
        repo = self._repo()

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock = self._mock_async_client()
        mock.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock):
            count = await repo.count_events_today(
                user_id="user-123", event_type="cv_adapted"
            )

        assert count == 0
