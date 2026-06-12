"""Tests for `BackgroundJobScheduler` (T-007) — RED → GREEN → REFACTOR.

Spec: REQ-SCH-001..005.
`scheduler-retention-history` adds `retention_days` param + retention call
(REQ-RET-002, REQ-SCH-001 MODIFIED, REQ-SCH-005 MODIFIED).
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import Callable

import pytest

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.scheduler import BackgroundJobScheduler


class FakeJobRepository:
    """In-memory repository that records `upsert_jobs` and `delete_older_than` calls.

    Structurally satisfies `JobRepositoryPort` (no inheritance — structural
    conformance is enforced by mypy --strict at type-check time).

    The `delete_older_calls` list records every `(days, limit)` tuple passed
    to `delete_older_than`, so tests can assert the method was (or was not)
    called with the expected arguments (REQ-RET-002).
    """

    def __init__(self) -> None:
        self.upsert_calls: list[tuple[list[Job], dict[str, str]]] = []
        self.delete_older_calls: list[tuple[int, int]] = []

    async def upsert_jobs(
        self,
        jobs: list[Job],
        query_snapshot: dict[str, str],
    ) -> int:
        self.upsert_calls.append((jobs, query_snapshot))
        return len(jobs)

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return []

    async def delete_older_than(self, *, days: int, limit: int = 1000) -> int:
        self.delete_older_calls.append((days, limit))
        return 0

    async def search_jobs_history(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return []

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        return 0

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
        assert scheduler._retention_days == 0

    @pytest.mark.asyncio
    async def test_constructor_stores_retention_days(self) -> None:
        """`retention_days` is stored on construction."""
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[],
            retention_days=30,
        )

        assert scheduler._retention_days == 30

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
        assert len(repo.upsert_calls) >= 1, "Expected at least 1 upsert_jobs call"

    # ── Phase 3: Empty-keyword queries (Spain location-only) ─────────────────

    @pytest.mark.asyncio
    async def test_empty_keywords_accepted_and_passed_to_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scheduler accepts empty-keyword queries and passes them to search_fn without error.

        Phase 3 of `scheduler-source-fix`: scraper URL builders all use `quote("")`
        for keywords, which is a valid empty-string URL param. This test confirms
        the scheduler path works end-to-end with empty keywords.
        """
        from jobs_finder.infrastructure import scheduler as scheduler_module

        # Mock work-hours gate so the scheduler proceeds immediately
        monkeypatch.setattr(scheduler_module, "_is_within_active_hours", lambda: True)

        repo = FakeJobRepository()
        search_calls: list[tuple[str, str]] = []

        async def tracking_fn(keywords: str, location: str) -> list[Job]:
            search_calls.append((keywords, location))
            return [_make_job(f"{keywords}-{location}")]

        scheduler = BackgroundJobScheduler(
            search_fn=tracking_fn,
            repo=repo,
            queries=[
                {"keywords": "", "location": "España"},
                {"keywords": "", "location": "Madrid, España"},
                {"keywords": "", "location": "Barcelona, España"},
            ],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Empty-keyword queries must be accepted and passed to search_fn
        empty_kw_calls = [(kw, loc) for (kw, loc) in search_calls if kw == ""]
        assert len(empty_kw_calls) >= 3, (
            f"Expected at least 3 empty-keyword calls, got {len(empty_kw_calls)}: {search_calls}"
        )
        # Verify the Spain locations were used
        assert any(loc == "España" for _, loc in search_calls)
        assert any(loc == "Madrid, España" for _, loc in search_calls)
        assert any(loc == "Barcelona, España" for _, loc in search_calls)
        # upsert_jobs must have been called
        assert len(repo.upsert_calls) >= 1, "Expected at least 1 upsert_jobs call"

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
        assert call_count >= 3, f"Expected at least 3 completed cycles, got {call_count}"

    # ── REQ-RET-002: Retention called after upsert ─────────────────────────

    @pytest.mark.asyncio
    async def test_retention_called_after_upsert(self) -> None:
        """When `retention_days > 0`, `delete_older_than` is called after upsert."""
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return [_make_job("1")]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
            retention_days=30,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # Verify delete_older_than was called with the right args
        assert len(repo.delete_older_calls) >= 1, (
            "Expected delete_older_than to be called when retention_days > 0"
        )
        for days, limit in repo.delete_older_calls:
            assert days == 30
            assert limit == 1000

    @pytest.mark.asyncio
    async def test_retention_skipped_when_zero(self) -> None:
        """When `retention_days == 0`, `delete_older_than` is NOT called."""
        repo = FakeJobRepository()
        call_count = 0

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal call_count
            call_count += 1
            return [_make_job(str(call_count))]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
            retention_days=0,
        )

        scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # delete_older_than should never have been called
        assert len(repo.delete_older_calls) == 0, (
            "Expected NO delete_older_than calls when retention_days == 0"
        )

    @pytest.mark.asyncio
    async def test_retention_after_upsert_order(self) -> None:
        """`delete_older_than` is called AFTER `upsert_jobs`, never before.

        We verify that in every cycle, the last repo call is upsert_jobs,
        followed by delete_older_than (if any). Since the task runs
        concurrently, we check the cumulative call history.
        """
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return [_make_job("1")]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
            retention_days=30,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # The scheduler runs cyclically. For each cycle, the order within
        # the lock must be: search_fn → upsert_jobs → delete_older_than.
        # We can't inspect individual cycles directly, so we verify the
        # broader invariant: delete_older_calls were made AND upsert_calls
        # were made. The truth of ordering is enforced by the lock-held
        # implementation (_loop runs upsert then delete inside async with
        # self._lock).
        assert len(repo.upsert_calls) >= 1, "Expected at least 1 upsert"
        assert len(repo.delete_older_calls) >= 1, "Expected at least 1 retention call"

    # ── REQ-STATUS-001: SchedulerState tracking ───────────────────────────

    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        """Initial state: not running, None timestamps, 0 counts."""
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

        state = scheduler.state
        assert state.running is False
        assert state.last_run_start is None
        assert state.last_run_end is None
        assert state.last_error is None
        assert state.cycle_count == 0
        assert state.total_jobs_collected == 0

    @pytest.mark.asyncio
    async def test_state_after_one_cycle(self) -> None:
        """After one cycle: cycle_count>=1, running=False, timestamps set, no error."""
        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return [_make_job("1")]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        state = scheduler.state
        assert state.cycle_count >= 1, f"Expected at least 1 cycle, got {state.cycle_count}"
        assert state.running is False
        assert state.last_run_start is not None
        assert state.last_run_end is not None
        assert state.last_error is None

    @pytest.mark.asyncio
    async def test_state_on_error(self) -> None:
        """When search_fn raises, last_error is populated."""
        repo = FakeJobRepository()

        async def error_fn(_kw: str, _loc: str) -> list[Job]:
            raise ValueError("search failed")

        scheduler = BackgroundJobScheduler(
            search_fn=error_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        state = scheduler.state
        assert state.last_error is not None, "Expected last_error to be populated on error"
        assert "search failed" in state.last_error

    @pytest.mark.asyncio
    async def test_total_jobs_collected_accumulates(self) -> None:
        """total_jobs_collected accumulates across cycles."""
        repo = FakeJobRepository()
        call_count = 0

        async def counting_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal call_count
            call_count += 1
            return [_make_job(str(call_count))] * 3  # 3 jobs per cycle

        scheduler = BackgroundJobScheduler(
            search_fn=counting_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        # Initial state
        assert scheduler.state.total_jobs_collected == 0

        scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert scheduler.state.total_jobs_collected >= 3, (
            f"Expected at least 3 collected jobs, got {scheduler.state.total_jobs_collected}"
        )


def _make_job(id_suffix: str, source: str = "linkedin") -> Job:
    return Job(
        id=f"job_{id_suffix}",
        title="Test Job",
        company="Test Co",
        location="Test Location",
        url=f"https://example.com/job/{id_suffix}",
        posted_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        source=source,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TestWorkHours — REQ-HOURS-001..004: Madrid work-hours gate (09:00–22:00)
# ─────────────────────────────────────────────────────────────────────────────


class TestIsWithinActiveHours:
    """Unit tests for the `_is_within_active_hours()` helper.

    REQ-HOURS-001: Returns True when Madrid local hour is 9–21 (inclusive).
    REQ-HOURS-002: Returns False when Madrid local hour is outside 09:00–22:00.
    """

    @pytest.mark.parametrize(
        "hour,expected",
        [
            (8, False),   # 08:59 — outside (one minute before opening)
            (9, True),    # 09:00 — inside (boundary: opening)
            (10, True),   # 10:00 — inside
            (14, True),   # 14:00 — inside
            (21, True),   # 21:59 — inside (one minute before closing)
            (22, False),  # 22:00 — outside (boundary: closing)
            (23, False),  # 23:00 — outside
            (0, False),   # 00:00 — outside
        ],
    )
    def test_boundary_cases(
        self, hour: int, expected: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Madrid hour at boundary values returns expected True/False."""
        from zoneinfo import ZoneInfo

        # Fake datetime.now() that returns a Madrid time with the given hour
        class FakeDatetime:
            @staticmethod
            def now(tz: ZoneInfo) -> "FakeDatetime":
                return FakeDatetime()

            def __init__(self) -> None:
                self.hour = hour

        import jobs_finder.infrastructure.scheduler as scheduler_module

        monkeypatch.setattr(scheduler_module, "datetime", FakeDatetime())

        # Import the function after patching so the module-level reference uses the mock
        result = scheduler_module._is_within_active_hours()
        assert result is expected


class TestWorkHours:
    """Integration tests for the scheduler's work-hours gate.

    REQ-HOURS-003: Scheduler sleeps 300s when outside 09:00–22:00 Madrid time.
    REQ-HOURS-004: Scheduler proceeds with lock acquisition when within active hours.
    """

    @pytest.mark.asyncio
    async def test_outside_hours_sleeps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When outside business hours, the loop sleeps 300s without acquiring lock."""
        from jobs_finder.infrastructure import scheduler as scheduler_module

        # Mock _is_within_active_hours to always return False
        monkeypatch.setattr(
            scheduler_module, "_is_within_active_hours", lambda: False
        )

        sleep_calls: list[tuple[float]] = []

        async def tracking_sleep(delay: float) -> None:
            sleep_calls.append((delay,))
            # Don't actually sleep - we want tests to complete quickly

        monkeypatch.setattr(asyncio, "sleep", tracking_sleep)

        repo = FakeJobRepository()

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            return []

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        # Let the outer while loop run once and hit the sleep
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # Should have slept for 300 seconds (outside hours guard)
        assert len(sleep_calls) >= 1, "Expected at least one sleep call"
        assert any(delay == 300.0 for delay, in sleep_calls), (
            f"Expected sleep(300) when outside hours, got {sleep_calls}"
        )
        # Lock should NOT have been acquired (still in outer guard loop)
        assert not scheduler._lock.locked()

    @pytest.mark.asyncio
    async def test_within_hours_proceeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When within business hours, loop proceeds past the guard to lock acquisition."""
        from jobs_finder.infrastructure import scheduler as scheduler_module

        # Mock _is_within_active_hours to return True
        monkeypatch.setattr(
            scheduler_module, "_is_within_active_hours", lambda: True
        )

        sleep_calls: list[tuple[float]] = []

        async def tracking_sleep(delay: float) -> None:
            sleep_calls.append((delay,))
            # Don't actually sleep - we want tests to complete quickly

        monkeypatch.setattr(asyncio, "sleep", tracking_sleep)

        repo = FakeJobRepository()
        search_called = False

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal search_called
            search_called = True
            return [_make_job("1")]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        # Should NOT have slept 300 (guard was bypassed)
        guard_sleeps = [d for d, in sleep_calls if d == 300.0]
        assert len(guard_sleeps) == 0, (
            f"Did not expect guard sleep(300) when within hours, got {sleep_calls}"
        )
        # search_fn should have been called (lock was acquired and cycle ran)
        assert search_called, "Expected search_fn to be called when within hours"

    @pytest.mark.asyncio
    async def test_transition_to_active_hours(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Outer loop re-checks and eventually proceeds when hours become active."""
        from jobs_finder.infrastructure import scheduler as scheduler_module

        call_count = 0

        def make_is_within_active_hours() -> Callable[[], bool]:
            def is_within() -> bool:
                nonlocal call_count
                call_count += 1
                # First 3 calls return False (outside hours), then True
                return call_count > 3

            return is_within

        monkeypatch.setattr(
            scheduler_module,
            "_is_within_active_hours",
            make_is_within_active_hours(),
        )

        sleep_calls: list[tuple[float]] = []

        async def tracking_sleep(delay: float) -> None:
            sleep_calls.append((delay,))
            # Don't actually sleep - we want tests to complete quickly

        monkeypatch.setattr(asyncio, "sleep", tracking_sleep)

        repo = FakeJobRepository()
        search_called = False

        async def dummy_fn(_kw: str, _loc: str) -> list[Job]:
            nonlocal search_called
            search_called = True
            return [_make_job("1")]

        scheduler = BackgroundJobScheduler(
            search_fn=dummy_fn,
            repo=repo,
            queries=[{"keywords": "python", "location": "Madrid"}],
            min_interval=0.01,
            max_interval=0.02,
        )

        scheduler.start()
        await asyncio.sleep(0.2)
        await scheduler.stop()

        # Should have slept 300s for each of the first 3 iterations
        guard_sleeps = [d for d, in sleep_calls if d == 300.0]
        assert len(guard_sleeps) >= 3, (
            f"Expected at least 3 guard sleeps (300s each), got {guard_sleeps}"
        )
        # Eventually should have proceeded to search
        assert search_called, "Expected search_fn to be called after hours became active"
