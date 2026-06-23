"""Integration tests for scheduler wiring in `app_factory.build_app`.

Spec: REQ-ROOT-001, REQ-HIST-002 (scenario 2). Uses
`asgi_lifespan.LifespanManager` to exercise the FastAPI lifespan and
verify that the scheduler + repository are correctly wired.

`scheduler-retention-history` Phase 5 (DB path independence): the
repository is now built when `db_path` is non-empty regardless of
`scheduler_enabled`. The scheduler is only built when
`scheduler_enabled=true`.

The `TestSchedulerWiringEnabled` tests monkeypatch the three scrapers'
`__aenter__` / `__aexit__` to no-ops so the lifespan never tries to
launch a real Chromium browser. Real-browser launches fail in
sandbox environments (EACCES) and would also slow the suite by
multiple seconds per test. The scrapers' `__aenter__` is replaced with
a fake that just sets `_browser = None` and returns `self`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.indeed.scraper import IndeedPlaywrightScraper
from jobs_finder.infrastructure.infojobs.scraper import InfoJobsPlaywrightScraper
from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper
from jobs_finder.presentation.app_factory import build_app


def _patch_scrapers_to_skip_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch the three scrapers' `__aenter__` / `__aexit__` to no-ops.

    The lifespan opens the 3 default scrapers in parallel via
    `asyncio.gather(..., return_exceptions=True)`. In a sandboxed CI
    environment without Chromium execute permissions, real browser
    launches fail with `Error: spawn . EACCES`. To keep these tests
    deterministic we replace each scraper's `__aenter__` with a no-op
    that sets `_browser = None` and returns `self`, and each
    `__aexit__` with a no-op.
    """

    async def _fake_aenter(self: object) -> object:
        # Mirror the production code's attribute set without
        # actually launching Chromium.
        self._browser = None  # type: ignore[attr-defined]
        return self

    async def _fake_aexit(self: object, *exc: object) -> None:
        return None

    for cls in (
        LinkedInPlaywrightScraper,
        IndeedPlaywrightScraper,
        InfoJobsPlaywrightScraper,
    ):
        monkeypatch.setattr(cls, "__aenter__", _fake_aenter)
        monkeypatch.setattr(cls, "__aexit__", _fake_aexit)


@asynccontextmanager
async def _client_with_lifespan(app: Any) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` whose lifespan is exercised by `LifespanManager`.

    `LifespanManager`'s default `shutdown_timeout` is 5s; the
    `app = build_app()` default branch opens 3 `*PlaywrightScraper`
    instances whose `__aexit__` may take >5s when running serially
    (browser cleanup, drain helper, asyncio scheduling jitter).
    We bump to 15s to keep these tests stable without changing the
    `*PlaywrightScraper` shutdown semantics. Production uses
    uvicorn's graceful-shutdown timeout, not `LifespanManager`.
    """
    async with (
        LifespanManager(app, startup_timeout=30, shutdown_timeout=30),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        yield client


class TestSchedulerWiringDisabled:
    """SCHEDULER_ENABLED=false: repo built only when db_path is set."""

    @pytest.mark.asyncio
    async def test_no_repo_when_db_path_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When `db_path=""`, no repository is built regardless of scheduler."""
        monkeypatch.setenv("DATABASE_URL", "")
        app = build_app(settings=Settings(db_path=""))

        async with _client_with_lifespan(app):
            repo = getattr(app.state, "job_repository", None)
            assert repo is None, "Expected no job_repository when db_path=''"

    @pytest.mark.asyncio
    async def test_repo_built_without_scheduler_when_db_path_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When db_path set and scheduler disabled, repo is built but scheduler is not."""
        monkeypatch.setenv("DATABASE_URL", "")
        app = build_app(settings=Settings(db_path=":memory:", scheduler_enabled=False))

        async with _client_with_lifespan(app):
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None, (
                "Expected repo when db_path is set even with scheduler_enabled=False"
            )
            assert repo._connection is not None, "Repo should be open after lifespan startup"
            scheduler = getattr(app.state, "scheduler", None)
            assert scheduler is None, "Expected no scheduler when scheduler_enabled=False"


class TestSchedulerWiringEnabled:
    """SCHEDULER_ENABLED=true: repository opened, scheduler started/stopped."""

    @pytest.mark.asyncio
    async def test_repository_opened_and_scheduler_started(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When enabled, the lifespan opens the repo and starts the scheduler."""
        _patch_scrapers_to_skip_browser(monkeypatch)
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "10000.0")
        monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "20000.0")
        monkeypatch.setenv(
            "SCHEDULER_QUERIES",
            '[{"keywords": "python", "location": "Madrid"}]',
        )

        app = build_app(
            settings=Settings(
                scheduler_enabled=True,
                db_path=":memory:",
                database_url="",  # Force SQLite regardless of env
            )
        )

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
        _patch_scrapers_to_skip_browser(monkeypatch)
        db_file = str(tmp_path / "test_scheduler.db")
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "10000.0")
        monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "20000.0")
        monkeypatch.setenv(
            "SCHEDULER_QUERIES",
            '[{"keywords": "python", "location": "Madrid"}]',
        )

        app = build_app(
            settings=Settings(
                scheduler_enabled=True,
                db_path=db_file,
                database_url="",  # Force SQLite regardless of env
            )
        )

        async with _client_with_lifespan(app):
            repo = getattr(app.state, "job_repository", None)
            assert repo is not None
            assert repo._connection is not None

        # After lifespan exits, the connection should be closed.
        assert repo._connection is None, (
            "Repository connection should be closed after lifespan shutdown"
        )


# ── REQ-RET-001 / REQ-ROOT-001 (MODIFIED): retention_days wiring ────────────


class TestSchedulerRetentionWiring:
    """SCHEDULER_ENABLED=true + RETENTION_DAYS > 0."""

    @pytest.mark.asyncio
    async def test_retention_days_wired_to_scheduler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When `RETENTION_DAYS=30`, the scheduler receives `retention_days=30`."""
        _patch_scrapers_to_skip_browser(monkeypatch)
        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("RETENTION_DAYS", "30")
        monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "10000.0")
        monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "20000.0")
        monkeypatch.setenv(
            "SCHEDULER_QUERIES",
            '[{"keywords": "python", "location": "Madrid"}]',
        )

        app = build_app(
            settings=Settings(
                scheduler_enabled=True,
                db_path=":memory:",
                database_url="",
                retention_days=30,
            )
        )

        async with _client_with_lifespan(app):
            scheduler = getattr(app.state, "scheduler", None)
            assert scheduler is not None, (
                "Expected scheduler to be set on app.state when SCHEDULER_ENABLED=true"
            )
            assert scheduler._retention_days == 30, (
                f"Expected retention_days=30, got {scheduler._retention_days}"
            )
