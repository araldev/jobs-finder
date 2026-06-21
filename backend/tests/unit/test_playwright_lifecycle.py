"""Unit tests for the shared Playwright task-drain helper.

Spec: REQ-LIFECYCLE-001, REQ-LIFECYCLE-003, REQ-LIFECYCLE-007, REQ-LIFECYCLE-009;
SCN-LIFECYCLE-001-1, SCN-LIFECYCLE-001-2, SCN-LIFECYCLE-001-3, SCN-LIFECYCLE-003-1.

WHY THIS HELPER EXISTS
======================
`async_playwright().start()` spawns a `Connection.run()` background
task that survives `playwright.stop()` (which is a documented
no-op: `playwright/_impl/_playwright.py:59`). When pytest-asyncio
closes the function-scoped event loop, the leaked task triggers
`Task was destroyed but it is pending!` warnings, which
`filterwarnings = ["error"]` converts to test errors attached to
whichever test happens to be running when the GC fires. This
produces the 9-12-test isolation cluster documented in
`sdd/fix-test-isolation/explore`.

The 3 `*PlaywrightScraper.__aexit__` methods call this helper
as the LAST step so the test boundary is clean.

Test approach:
- `Connection` (module-level) provides a method whose coro
  `__qualname__` is `"Connection.run"`. The class name is
  intentionally `Connection` (NOT `_FakeConnection`) so the
  qualified name mirrors Playwright's internal class — that
  is the exact string the drain helper matches.
- Tests spawn a real `asyncio.Task` wrapping that coro, then call
  the drain and assert the task is `done()` afterwards.
- For the "cancels on timeout" scenario, the coro awaits an
  Event that the test never sets; the drain's timeout forces a
  cancel.
"""

from __future__ import annotations

import asyncio

from jobs_finder.infrastructure._playwright_lifecycle import (
    drain_playwright_tasks,
)

# ---------------------------------------------------------------------------
# Fakes — `Connection.run` and `Connection.init` shaped coros
# ---------------------------------------------------------------------------


class Connection:
    """Stand-in for Playwright's internal `Connection` class.

    The class name is intentionally `Connection` (NOT
    `_FakeConnection`) so the coroutine `__qualname__` mirrors
    Playwright's actual class. The drain helper matches on
    `coro.__qualname__ in {"Connection.run", "Connection.init"}`
    (see `_PLAYWRIGHT_CONNECTION_CORO_NAMES`); using a different
    class name would make the qualname mismatch and the tests
    would not exercise the helper's matching logic.
    """

    async def run(self) -> None:
        # Block on the gate until the test releases it; the
        # drain's timeout forces a cancel on the timeout-zero
        # scenario.
        await self._gate.wait()

    async def init(self) -> None:
        await self._gate.wait()

    def __init__(self) -> None:
        # One gate shared between `run` and `init` so tests can
        # release both at once when they want the drain to complete.
        self._gate: asyncio.Event = asyncio.Event()


def _spawn_connection_run(connection: Connection) -> asyncio.Task[None]:
    """Schedule `connection.run()` as a real asyncio task.

    The task's `get_coro().__qualname__` is `"Connection.run"`
    (the method's qualified name on the class), which is what
    the drain helper matches.
    """
    return asyncio.create_task(connection.run())


def _pending_connection_tasks() -> list[asyncio.Task[None]]:
    """Return all pending tasks whose coro is a Playwright Connection method."""
    return [
        t
        for t in asyncio.all_tasks()
        if not t.done()
        and getattr(t.get_coro(), "__qualname__", "") in {"Connection.run", "Connection.init"}
    ]


# ---------------------------------------------------------------------------
# REQ-LIFECYCLE-003 / SCN-LIFECYCLE-001-2 — idempotent no-op
# ---------------------------------------------------------------------------


async def test_drain_no_op_when_no_pending_tasks() -> None:
    """`drain_playwright_tasks()` is a no-op when no Playwright tasks are pending.

    REQ-LIFECYCLE-001 (d) — the drain is idempotent. SCN-LIFECYCLE-001-2.
    A pre-condition of ZERO pending Playwright tasks must return
    cleanly without raising. This is the safety property: the
    scraper `__aexit__` can call the drain unconditionally.
    """
    # Sanity: baseline is zero.
    assert _pending_connection_tasks() == []
    # The drain returns without error when nothing is pending.
    await drain_playwright_tasks(timeout=0.1)
    # Still zero after the call (no spurious tasks created).
    assert _pending_connection_tasks() == []


# ---------------------------------------------------------------------------
# REQ-LIFECYCLE-003 / SCN-LIFECYCLE-001-1 + SCN-LIFECYCLE-003-1
# ---------------------------------------------------------------------------


async def test_drain_awaits_pending_playwright_task() -> None:
    """A pending `Connection.run` task is awaited to completion by the drain.

    REQ-LIFECYCLE-001 (a) + (b) — the drain finds and awaits
    tasks whose coro `__qualname__` is in `{Connection.run,
    Connection.init}`. SCN-LIFECYCLE-001-1 + SCN-LIFECYCLE-003-1.

    The test:
    1. Spawns a real asyncio task wrapping `Connection.run()`.
       The task's coro `__qualname__` is `"Connection.run"`.
    2. Calls the drain (the coro is blocked on an unresolved Event).
    3. Releases the Event from a concurrent task so the drain's
       `gather` can complete the task naturally.
    4. Asserts the task is `done()` with no exception.
    """
    connection = Connection()
    task = _spawn_connection_run(connection)
    # Yield once so the task is actually scheduled and pending.
    await asyncio.sleep(0)
    assert not task.done()
    assert _pending_connection_tasks() == [task]

    # Release the gate concurrently with the drain so `await
    # gather(*pending)` can complete within the timeout.
    async def release() -> None:
        await asyncio.sleep(0.01)
        connection._gate.set()

    await asyncio.gather(drain_playwright_tasks(timeout=1.0), release())
    # The task was awaited to completion; no cancellation, no exception.
    assert task.done()
    assert not task.cancelled()
    assert task.exception() is None
    # The drain removed it from the pending set.
    assert _pending_connection_tasks() == []


# ---------------------------------------------------------------------------
# REQ-LIFECYCLE-003 / SCN-LIFECYCLE-001-3
# ---------------------------------------------------------------------------


async def test_drain_cancels_on_timeout_zero() -> None:
    """`drain(timeout=0)` cancels a Playwright task that does not finish in time.

    REQ-LIFECYCLE-001 (c) — the drain cancels and re-awaits any
    task that does not finish within the timeout.
    SCN-LIFECYCLE-001-3.

    The test:
    1. Spawns a real `Connection.run` task that blocks forever.
    2. Calls the drain with `timeout=0` (the wait_for expires
       immediately, triggering the cancel path).
    3. Asserts the task is `done()` and `cancelled()`.
    """
    connection = Connection()
    task = _spawn_connection_run(connection)
    await asyncio.sleep(0)
    assert not task.done()

    await drain_playwright_tasks(timeout=0)

    # The task is done because the drain cancelled it on the
    # immediate-timeout path. `cancelled()` is the precise
    # assertion (vs. `done()` which also matches a clean return).
    assert task.done()
    assert task.cancelled()
    # No pending Playwright tasks remain after the drain.
    assert _pending_connection_tasks() == []
