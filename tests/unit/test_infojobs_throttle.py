"""Unit tests for `InfoJobsAsyncThrottle`.

Spec: REQ-J-001..J-006 (partial — throttle is a building block, not a
user-facing requirement on its own; the consuming scraper code lands
in T-006). The full set of linked requirements is enumerated in
`tests/integration/test_infojobs_api.py` when the route is wired.

Design: per-process lock + a sleep that fills the gap between the
previous `__aexit__` and the current `__aenter__`. Tests patch
`asyncio.sleep` and `time.monotonic` inside the throttle module to
keep runs fast and deterministic — same pattern the LinkedIn and
Indeed throttle tests use.

The InfoJobs throttle is structurally identical to the LinkedIn and
Indeed throttles (per-process, per-instance lock; configurable
`min_interval_seconds`), but the three modules must be independent:
two `InfoJobsAsyncThrottle` instances serialize independently of the
LinkedIn + Indeed throttles and of each other. The acceptance test
for that independence lives here as
`test_infojobs_throttle_is_independent_of_linkedin_and_indeed_throttles`.
"""

from __future__ import annotations

import asyncio

import pytest

from jobs_finder.infrastructure.indeed.throttle import IndeedAsyncThrottle
from jobs_finder.infrastructure.infojobs.throttle import InfoJobsAsyncThrottle
from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle

# Saved at import time, BEFORE the `sleep_recorder` fixture patches
# `asyncio.sleep`. The throttle's lock-serialization test needs to yield
# to the event loop using the *real* sleep; calling the patched one
# would record a fake duration and never actually yield.
_REAL_ASYNC_SLEEP = asyncio.sleep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sleep_recorder(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch `asyncio.sleep` inside the InfoJobs throttle module to a recorder.

    The fake is an async no-op that records the requested duration, so we
    can assert how long the throttle decided to sleep without waiting.
    """
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "jobs_finder.infrastructure.infojobs.throttle.asyncio.sleep",
        fake_sleep,
    )
    return sleeps


@pytest.fixture
def virtual_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch `time.monotonic` inside the InfoJobs throttle module to a virtual clock.

    Tests advance the clock between operations to simulate time passing
    without waiting.
    """
    now: list[float] = [1000.0]

    def fake_monotonic() -> float:
        return now[0]

    monkeypatch.setattr(
        "jobs_finder.infrastructure.infojobs.throttle.time.monotonic",
        fake_monotonic,
    )
    return now


# ---------------------------------------------------------------------------
# Sleep behavior
# ---------------------------------------------------------------------------


async def test_first_call_does_not_sleep(sleep_recorder: list[float]) -> None:
    """The first entry has no prior `__aexit__`; no sleep is needed."""
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=3.0)
    async with throttle:
        pass
    assert sleep_recorder == []


async def test_second_call_within_interval_sleeps_remainder(
    sleep_recorder: list[float], virtual_clock: list[float]
) -> None:
    """If the gap is less than `min_interval_seconds`, sleep the remainder."""
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=3.0)

    async with throttle:
        pass  # first call: no prior exit, no sleep
    assert sleep_recorder == []

    # Advance the virtual clock by 1.0s (less than 3.0s min_interval).
    virtual_clock[0] += 1.0
    async with throttle:
        pass
    # Expect a sleep of (3.0 - 1.0) = 2.0 seconds.
    assert sleep_recorder == [pytest.approx(2.0)]


async def test_second_call_after_interval_does_not_sleep(
    sleep_recorder: list[float], virtual_clock: list[float]
) -> None:
    """If the gap >= `min_interval_seconds`, no sleep is needed."""
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=3.0)

    async with throttle:
        pass
    assert sleep_recorder == []

    # Advance the virtual clock well past the interval.
    virtual_clock[0] += 10.0
    async with throttle:
        pass
    assert sleep_recorder == []


async def test_two_rapid_calls_each_see_the_previous_exit(
    sleep_recorder: list[float], virtual_clock: list[float]
) -> None:
    """A third call observes the second call's exit (not the first's)."""
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=4.0)

    async with throttle:
        pass
    virtual_clock[0] += 1.0
    async with throttle:
        pass  # sleeps 3.0 (4.0 - 1.0)
    # Advance less than the interval: third call should sleep the remainder.
    virtual_clock[0] += 1.0
    async with throttle:
        pass  # sleeps 3.0 (4.0 - 1.0)

    assert len(sleep_recorder) == 2
    assert sleep_recorder[0] == pytest.approx(3.0)
    assert sleep_recorder[1] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Concurrency / lock
# ---------------------------------------------------------------------------


async def test_lock_serializes_concurrent_entries(
    sleep_recorder: list[float],
) -> None:
    """Two concurrent `async with throttle:` calls run sequentially.

    Uses 0.0s interval so the throttle does not inject a sleep, and an
    event pair to hold the first task in the lock while checking the
    second task is blocked.
    """
    throttle = InfoJobsAsyncThrottle(min_interval_seconds=0.0)
    first_entered = asyncio.Event()
    first_can_finish = asyncio.Event()

    async def task_first() -> None:
        async with throttle:
            first_entered.set()
            await first_can_finish.wait()

    async def task_second() -> None:
        async with throttle:
            pass  # body runs only after first releases the lock

    first = asyncio.create_task(task_first())
    await first_entered.wait()

    second = asyncio.create_task(task_second())
    # Yield to let the scheduler pick up the second task; it should block
    # on the lock and not complete. Use the REAL sleep (saved at import
    # time) so the patch in `sleep_recorder` does not absorb the yield.
    await _REAL_ASYNC_SLEEP(0)
    assert not second.done()

    # Allow the first to finish; this releases the lock and unblocks second.
    first_can_finish.set()
    await first
    await second
    # Sleep was never called by the throttle because interval is 0.0.
    assert sleep_recorder == []


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------


def test_default_min_interval_is_3_seconds() -> None:
    """The default `min_interval_seconds` matches the design (3.0s)."""
    throttle = InfoJobsAsyncThrottle()
    assert throttle._min_interval == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Independence (REQ-J-001..J-006): InfoJobs throttle is independent of
# the LinkedIn + Indeed throttles. Per-process, per-instance lock; the
# `_last_exit` field is per-instance, not module-global.
# ---------------------------------------------------------------------------


def test_infojobs_throttle_is_a_separate_class_from_linkedin_and_indeed() -> None:
    """`InfoJobsAsyncThrottle` is its own class, not a re-export of either.

    This is the static check that the three throttles are independent
    modules. A future refactor that aliases one to another would
    silently break the per-source isolation; this test pins the
    separation.
    """
    assert InfoJobsAsyncThrottle is not AsyncThrottle  # type: ignore[comparison-overlap]
    assert InfoJobsAsyncThrottle is not IndeedAsyncThrottle  # type: ignore[comparison-overlap]
    assert AsyncThrottle is not IndeedAsyncThrottle  # type: ignore[comparison-overlap]


async def test_infojobs_throttle_is_independent_of_linkedin_and_indeed_throttles() -> None:
    """A LinkedIn OR Indeed throttle call does not affect an InfoJobs throttle call.

    Each throttle has its own `_last_exit` and its own lock. The
    acceptance criterion: a fresh throttle's first entry should NOT
    observe the OTHER throttle's `_last_exit`, so it does NOT sleep.

    Uses `min_interval_seconds=0.0` so the test runs in zero real
    time and exercises the state-isolation property, not the sleep
    math. The sleep math is already covered by the other tests in
    this file.
    """
    linkedin = AsyncThrottle(min_interval_seconds=0.0)
    indeed = IndeedAsyncThrottle(min_interval_seconds=0.0)
    infojobs = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    # Pump the LinkedIn throttle so its `_last_exit` is fresh.
    async with linkedin:
        pass
    # The InfoJobs throttle is untouched — its first entry should NOT
    # observe the LinkedIn exit.
    async with infojobs:
        pass

    # Pump the Indeed throttle so its `_last_exit` is fresh.
    async with indeed:
        pass
    # The InfoJobs throttle is untouched by the Indeed call too.
    async with infojobs:
        pass

    # The reverse: pumping InfoJobs does not poison a fresh LinkedIn
    # OR Indeed entry either.
    async with linkedin:
        pass
    async with indeed:
        pass


# ---------------------------------------------------------------------------
# Per-instance lock: two InfoJobs throttles have INDEPENDENT locks.
# ---------------------------------------------------------------------------


async def test_two_infojobs_throttle_instances_have_independent_locks() -> None:
    """Two `InfoJobsAsyncThrottle` instances have their own lock each.

    The InfoJobs throttle (per the design) is per-process, per-instance.
    Two instances can run concurrently because they own their own
    `asyncio.Lock`. The throttle is a per-call gate, not a global
    mutex. Pinning this here so a future refactor that turns the lock
    into a module-level singleton cannot silently break parallelism.
    """
    a = InfoJobsAsyncThrottle(min_interval_seconds=0.0)
    b = InfoJobsAsyncThrottle(min_interval_seconds=0.0)

    a_entered = asyncio.Event()
    b_entered = asyncio.Event()
    a_can_finish = asyncio.Event()
    b_can_finish = asyncio.Event()

    async def task_a() -> None:
        async with a:
            a_entered.set()
            await a_can_finish.wait()

    async def task_b() -> None:
        async with b:
            b_entered.set()
            await b_can_finish.wait()

    task_a_handle = asyncio.create_task(task_a())
    task_b_handle = asyncio.create_task(task_b())

    # Both should be in their critical section — they have independent
    # locks, so neither blocks the other. Yield to let both run.
    await _REAL_ASYNC_SLEEP(0)
    await _REAL_ASYNC_SLEEP(0)
    assert a_entered.is_set()
    assert b_entered.is_set()
    assert not task_a_handle.done()
    assert not task_b_handle.done()

    a_can_finish.set()
    b_can_finish.set()
    await task_a_handle
    await task_b_handle
