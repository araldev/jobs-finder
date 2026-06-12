"""Tests for `BackgroundJobScheduler` (T-007) — RED → GREEN → REFACTOR.

Spec: REQ-SCH-001..005.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime

import pytest

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.scheduler import BackgroundJobScheduler


class FakeJobRepository:
    """In-memory repository that records `upsert_jobs` calls.

    Structurally satisfies `JobRepositoryPort` (no inheritance — structural
    conformance is enforced by mypy --strict at type-check time).
    """

    def __init__(self) -> None:
        self.upsert_calls: list[tuple[list[Job], str, dict[str, str]]] = []

    async def upsert_jobs(
        self,
        jobs: list[Job],
        source: str,
        query_snapshot: dict[str, str],
    ) -> int:
        self.upsert_calls.append((jobs, source, query_snapshot))
        return len(jobs)

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return []

    async def close(self) -> None:
        pass


class TestBackgroundJobScheduler:
    """Tests for `BackgroundJobScheduler`."""

    # ── REQ-SCH-001: Constructor stores params, no side effects ────────────

    @pytest.mark.asyncio
    async def test_constructor_stores_params(self) -> None:
        """Construction stores `search_fn`, `repo`, `queries`, and interval bounds."""
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=10.0,
            max_interval=20.0,
        )

        assert scheduler._search_fn is dummy_fn
        assert scheduler._repo is repo
        assert scheduler._queries == [{"keywords": "python", "location": "Madrid"}]
        assert scheduler._min_interval == 10.0
        assert scheduler._max_interval == 20.0
        assert scheduler._task is None

    # ── REQ-SCH-004: Start/stop lifecycle ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_start_creates_background_task(self) -> None:
        """`start()` creates an `asyncio.Task` that runs `_loop()`."""
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[],
            min_interval=1000.0,
            max_interval=2000.0,
        )

        assert scheduler._task is None
        scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()
        # Clean up
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task_gracefully(self) -> None:
        """`stop()` cancels the task and catches `CancelledError` without propagating."""
        repo = FakeJobRepository()

        async def long_fn(_kw: str, _loc: str) -> list[Job]:
            await asyncio.sleep(3600)  # never completes
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=long_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=1000.0,
            max_interval=2000.0,
        )

        scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()

        # Stop mid-cycle — task should be cancelled silently
        await scheduler.stop()
        assert scheduler._task is None

    # ── REQ-SCH-003: Lock prevents overlapping runs ─────────────────────────

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_execution(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the lock is already held, `_loop` logs a WARNING and skips the cycle."""
        repo = FakeJobRepository()

        async def fast_fn(_kw: str, _loc: str) -> list[Job]:
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=fast_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.01,
        )

        # Pre-acquire the lock to simulate a running cycle from a different
        # task (e.g. a double call to start()).
        await scheduler._lock.acquire()

        # Start the scheduler — _loop runs, checks locked(), sees it held,
        # logs WARNING, and skips to sleep.
        scheduler.start()
        await asyncio.sleep(0.05)

        # Release the lock so the next cycle can proceed, then stop.
        scheduler._lock.release()
        await scheduler.stop()

        # The WARNING should have been logged for the skipped overlapping run.
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("overlapping" in msg.lower() for msg in warning_messages), (
            f"Expected a WARNING about overlapping run, got: {warning_messages}"
        )

    # ── REQ-SCH-002: Random interval ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sleep_range_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The `_loop` should sleep for `random.uniform(min, max)` between cycles."""
        repo = FakeJobRepository()
        call_count = 0

        async def fast_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal call_count
            call_count += 1
            return [_make_job(str(call_count))]

        # Patch random.uniform to return a deterministic value
        original_uniform = random.uniform
        uniform_calls: list[tuple[float, float]] = []

        def tracking_uniform(a: float, b: float) -> float:
            uniform_calls.append((a, b))
            return original_uniform(a, b)

        monkeypatch.setattr(random, "uniform", tracking_uniform)

        scheduler = BackgroundJobScheduler(
            search_fn=fast_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        # Let the scheduler run for a bit (at least 2 cycles)
        await asyncio.sleep(0.15)

        await scheduler.stop()

        # Verify random.uniform was called with the right bounds
        assert len(uniform_calls) >= 1, "random.uniform should have been called"
        for a, b in uniform_calls:
            assert a == 0.01, f"Expected min_interval=0.01, got {a}"
            assert b == 0.02, f"Expected max_interval=0.02, got {b}"

    # ── REQ-SCH-005: Multiple queries per cycle ─────────────────────────────

    @pytest.mark.asyncio
    async def test_multiple_queries_per_cycle(self) -> None:
        """Each cycle iterates all queries and calls `repo.upsert_jobs` once."""
        repo = FakeJobRepository()
        search_calls: list[tuple[str, str]] = []

        async def tracking_fn(keywords: str, location: str) -> list[Job]:
            search_calls.append((keywords, location))
            return [_make_job(f"{keywords}-{location}")]

        scheduler = BackgroundJobScheduler(
            search_fn=tracking_fn,
            repo=repo,
            queries=[
                {"keywords": "python", "location": "Madrid"},
                {"keywords": "java", "location": "Barcelona"},
            ],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # Each cycle should have called search_fn for each query
        assert len(search_calls) >= 2, (
            f"Expected at least 2 search_fn calls, got {len(search_calls)}"
        )
        # At least one complete cycle should have run
        assert ("python", "Madrid") in search_calls or ("java", "Barcelona") in search_calls

        # upsert_jobs should have been called with accumulated results
        assert len(repo.upsert_calls) >= 1, (
            "Expected at least 1 upsert_jobs call"
        )

    # ── Sequential runs succeed (REQ-SCH-003 scenario 2) ────────────────────

    @pytest.mark.asyncio
    async def test_sequential_runs_succeed(self) -> None:
        """When no overlap occurs, all cycles invoke `search_fn` each time."""
        repo = FakeJobRepository()
        call_count = 0

        async def fast_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal call_count
            call_count += 1
            return [_make_job(str(call_count))]

        scheduler = BackgroundJobScheduler(
            search_fn=fast_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Should have completed multiple cycles
        assert call_count >= 3, (
            f"Expected at least 3 completed cycles, got {call_count}"
        )


def _make_job(id_suffix: str) -> Job:
    return Job(
        id=f"job_{id_suffix}",
        title="Test Job",
        company="Test Co",
        location="Test Location",
        url=f"https://example.com/job/{id_suffix}",
        posted_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
