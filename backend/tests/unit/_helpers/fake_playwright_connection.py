"""Shared test double: a `Connection` class whose coroutines match Playwright's internal shape.

Used by:
- `tests/unit/test_playwright_lifecycle.py` — direct unit tests for
  `drain_playwright_tasks` (the helper that drains pending Playwright
  background tasks at the `*PlaywrightScraper.__aexit__` boundary).
- `tests/unit/test_linkedin_scraper.py`,
  `tests/unit/test_indeed_scraper.py`,
  `tests/unit/test_infojobs_scraper.py` — per-scraper regression
  tests that assert no Playwright `Connection.run` task leaks
  past `__aexit__`.

WHY THE CLASS IS NAMED `Connection` (not `_FakeConnection`)
==========================================================
The drain helper in `jobs_finder.infrastructure._playwright_lifecycle`
matches tasks by `coro.__qualname__`, which includes the class
name. To make the test's fake task match the helper's
`_PLAYWRIGHT_CONNECTION_CORO_NAMES = {"Connection.run",
"Connection.init"}`, the class name MUST be exactly
`Connection` (not prefixed or wrapped in a function-local scope
where the qualname would be e.g. `main.<locals>.Connection.run`).
The class is therefore module-level and unprefixed; the
docstring makes the intent clear.
"""

from __future__ import annotations

import asyncio


class Connection:
    """Stand-in for `playwright._impl._connection.Connection`.

    The class name is intentionally `Connection` (NOT
    `_FakeConnection`) so coroutine `__qualname__` is
    `"Connection.run"` / `"Connection.init"` — the exact
    strings the drain helper matches on.

    The `run` and `init` methods block on a shared `asyncio.Event`
    until the test releases it. Tests that want the drain to
    cancel the task simply never set the event and rely on the
    drain's timeout. Tests that want the drain to complete the
    task naturally set the event from a concurrent coroutine.
    """

    async def run(self) -> None:
        await self._gate.wait()

    async def init(self) -> None:
        await self._gate.wait()

    def __init__(self) -> None:
        # One gate shared between `run` and `init` so tests can
        # release both at once when they want the drain to complete.
        self._gate: asyncio.Event = asyncio.Event()
