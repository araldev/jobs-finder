"""Shared helper that drains pending Playwright background tasks.

Spec: REQ-LIFECYCLE-001, REQ-LIFECYCLE-003.

WHY THIS HELPER EXISTS
======================
`async_playwright().start()` schedules a `Connection.run()` (and
a `Connection.init()`) background task on the running event loop.
`playwright.stop()` is a documented no-op
(`playwright/_impl/_playwright.py:59`); the transport pipe closes
during `browser.close()`, but the `Connection.run()` task itself
is never awaited by Playwright.

When pytest-asyncio closes the function-scoped event loop with
that task still pending, asyncio emits `Task was destroyed but
it is pending!` which pytest-asyncio promotes to
`PytestUnraisableExceptionWarning`. Because
`pyproject.toml` has `filterwarnings = ["error"]`, the warning
becomes a test error attached to whichever test happens to be
running when the GC fires — NOT to the test that leaked the task.

This produces the 9-12-test isolation cluster documented in
`sdd/fix-test-isolation/explore`. The fix is the LAST step in
each `*PlaywrightScraper.__aexit__`: after
`browser.close()` and `playwright.stop()`, await this helper so
the connection task is awaited (or cancelled) before
`__aexit__` returns.

DESIGN NOTES
============
- Match by coroutine `__qualname__` (full qualified name), not by
  class identity. Importing `playwright._impl._connection.Connection`
  would couple to a private API that can change between minor
  Playwright releases (ADR-002 in `sdd/fix-test-isolation/design`).
  If Playwright renames `Connection.run`, the drain silently
  no-ops. Mitigation: the bounded `timeout` (default 0.5s) plus
  the explicit `task.cancel()` on timeout still protect against
  leaks; the `drain_playwright_tasks` unit tests in
  `test_playwright_lifecycle.py` pin the contract.
- Drain is idempotent: when no Playwright tasks are pending, the
  helper returns without side effects.
- Drain is bounded: the `timeout` argument caps the wait for
  completion. After the timeout, any remaining tasks are
  cancelled and re-awaited so the call returns quickly.
"""

from __future__ import annotations

import asyncio
from typing import Final

# Playwright internal coroutine `__qualname__` values that
# `playwright.stop()` does not synchronously cancel. The full
# qualname is `"Connection.run"` / `"Connection.init"` because
# these are methods on `playwright._impl._connection.Connection`.
_PLAYWRIGHT_CONNECTION_CORO_NAMES: Final[frozenset[str]] = frozenset(
    {"Connection.run", "Connection.init"}
)


def _is_playwright_connection_task(task: asyncio.Task[object]) -> bool:
    """Return `True` if `task`'s coroutine is a Playwright connection method.

    The check is on `coro.__qualname__` (e.g. `"Connection.run"`),
    not on the class identity, so the helper stays source-only and
    does not import any private Playwright symbol.
    """
    return getattr(task.get_coro(), "__qualname__", "") in _PLAYWRIGHT_CONNECTION_CORO_NAMES


async def drain_playwright_tasks(timeout: float = 0.5) -> None:
    """Await pending Playwright `Connection.run` / `Connection.init` tasks.

    The 3 `*PlaywrightScraper.__aexit__` methods call this helper
    as the LAST step so the lifespan returns with no Playwright
    background tasks on the loop. Without this drain, the
    `Connection.run()` task can survive across the pytest-asyncio
    event-loop boundary and trigger `Task was destroyed but it
    is pending!` warnings, which `filterwarnings = ["error"]`
    converts to test failures.

    The drain is bounded by `timeout` (default 0.5s) so a stuck
    connection cannot hang the caller. After the timeout expires,
    any still-pending tasks are cancelled explicitly and re-awaited;
    a cancelled task is safer than a leaked one (the leaked task's
    pipe is already closed).

    Idempotent: when no Playwright tasks are pending, the helper
    returns immediately without side effects.

    Args:
        timeout: Wall-clock budget (seconds) for the `wait_for`
            around the gathered tasks. `0.0` skips the wait and
            goes straight to the cancel path.
    """
    loop = asyncio.get_running_loop()
    pending = [
        t for t in asyncio.all_tasks(loop) if not t.done() and _is_playwright_connection_task(t)
    ]
    if not pending:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout,
        )
    except TimeoutError:
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
