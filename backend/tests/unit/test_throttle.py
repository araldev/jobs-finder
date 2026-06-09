"""Unit tests for `AsyncThrottle`.

Spec: REQ-014.
Design: per-process lock + a sleep that fills the gap between the previous
`__aexit__` and the current `__aenter__`. Tests patch `asyncio.sleep` and
`time.monotonic` inside the throttle module to keep runs fast and
deterministic.
"""

from __future__ import annotations

import asyncio

import pytest

from jobs_finder.infrastructure.linkedin.throttle import AsyncThrottle

# Saved at import time, BEFORE the `sleep_recorder` fixture patches
# `asyncio.sleep`. The throttle's lock-serialization test needs to yield to
# the event loop using the *real* sleep; calling the patched one would record
# a fake duration and never actually yield.
_REAL_ASYNC_SLEEP = asyncio.sleep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sleep_recorder(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch `asyncio.sleep` inside the throttle module to a recorder.

    The fake is an async no-op that records the requested duration, so we
    can assert how long the throttle decided to sleep without waiting.
    """
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "jobs_finder.infrastructure.linkedin.throttle.asyncio.sleep",
        fake_sleep,
    )
    return sleeps


@pytest.fixture
def virtual_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch `time.monotonic` inside the throttle module to a virtual clock.

    Tests advance the clock between operations to simulate time passing
    without waiting.
    """
    now: list[float] = [1000.0]

    def fake_monotonic() -> float:
        return now[0]

    monkeypatch.setattr(
        "jobs_finder.infrastructure.linkedin.throttle.time.monotonic",
        fake_monotonic,
    )
    return now


# ---------------------------------------------------------------------------
# Sleep behavior
# ---------------------------------------------------------------------------


async def test_first_call_does_not_sleep(sleep_recorder: list[float]) -> None:
    """The first entry has no prior `__aexit__`; no sleep is needed."""
    throttle = AsyncThrottle(min_interval_seconds=3.0)
    async with throttle:
        pass
    assert sleep_recorder == []


async def test_second_call_within_interval_sleeps_remainder(
    sleep_recorder: list[float], virtual_clock: list[float]
) -> None:
    """If the gap is less than `min_interval_seconds`, sleep the remainder."""
    throttle = AsyncThrottle(min_interval_seconds=3.0)

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
    throttle = AsyncThrottle(min_interval_seconds=3.0)

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
    throttle = AsyncThrottle(min_interval_seconds=4.0)

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
    throttle = AsyncThrottle(min_interval_seconds=0.0)
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
    throttle = AsyncThrottle()
    assert throttle._min_interval == pytest.approx(3.0)
