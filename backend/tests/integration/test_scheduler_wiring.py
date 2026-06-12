"""Integration tests for scheduler wiring in `app_factory.build_app`.

Spec: REQ-ROOT-001. Uses `asgi_lifespan.LifespanManager` to exercise the
FastAPI lifespan and verify that the scheduler + repository are correctly
wired when `SCHEDULER_ENABLED=true` and absent when `SCHEDULER_ENABLED=false`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from jobs_finder.presentation.app_factory import build_app


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` whose lifespan is exercised by `LifespanManager`."""
    async with (
        LifespanManager(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


class TestSchedulerWiringDisabled:
    """SCHEDULER_ENABLED=false (default): zero behavioral change."""

    @pytest.mark.asyncio
    async def test_scheduler_not_created_when_disabled(self) -> None:
        """When `scheduler_enabled=False`, no scheduler or repo is exposed."""
        app = build_app()

        # Before the lifespan runs, verify no scheduler state.
        assert not hasattr(app.state, "job_repository") or app.state.job_repository is None

        async with _client_with_lifespan(app):
            # After lifespan startup, still no scheduler state.
            repo = getattr(app.state, "job_repository", None)
            assert repo is None, "Expected no job_repository when SCHEDULER_ENABLED=false"


class TestSchedulerWiringEnabled:
    """SCHEDULER_ENABLED=true: repository opened, scheduler started/stopped."""

    @pytest.mark.asyncio
    async def test_repository_opened_and_scheduler_started(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When enabled, the lifespan opens the repo and starts the scheduler."""
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("DB_PATH", ":memory:")
        monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "10000.0")
        monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "20000.0")
        monkeypatch.setenv(
            "SCHEDULER_QUERIES",
            '[{"keywords": "python", "location": "Madrid"}]',
        )

        app = build_app()

        async with _client_with_lifespan(app):
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None, "Expected job_repository to be set when SCHEDULER_ENABLED=true"
            # The repo should be open (connection established)
            assert repo._connection is not None, "Repository should be open after lifespan startup"

    @pytest.mark.asyncio
    async def test_scheduler_repository_closed_on_shutdown(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """After lifespan shutdown, the repository connection should be closed."""
        db_file = str(tmp_path / "test_scheduler.db")
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("DB_PATH", db_file)
        monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "10000.0")
        monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "20000.0")
        monkeypatch.setenv(
            "SCHEDULER_QUERIES",
            '[{"keywords": "python", "location": "Madrid"}]',
        )

        app = build_app()

        async with _client_with_lifespan(app):
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None
            assert repo._connection is not None

        # After lifespan exits, the connection should be closed.
        assert repo._connection is None, (
            "Repository connection should be closed after lifespan shutdown"
        )
