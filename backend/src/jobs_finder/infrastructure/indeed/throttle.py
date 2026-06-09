"""Per-process async throttle for serializing calls to Indeed.

Spec: REQ-I-008.
Design: one `asyncio.Lock` per `IndeedAsyncThrottle` instance. On each
`__aenter__`, if the gap since the last `__aexit__` is less than
`min_interval_seconds`, the throttle awaits the remainder. Two
`async with throttle:` calls on the SAME instance always serialize
(the lock blocks the second `__aenter__` until the first `__aexit__`
runs).

Per-process, per-instance: two `IndeedAsyncThrottle` instances can
serialize independently of the LinkedIn throttle and of each other.
The lock lives in the calling process; in a multi-worker deployment
each worker has its own throttle.

This module is a 1:1 structural mirror of
`jobs_finder.infrastructure.linkedin.throttle.AsyncThrottle`. The
classes are intentionally separate (not aliased) so a future
refactor to one does not silently change the other's behavior. The
test `test_indeed_throttle_is_independent_of_linkedin_throttle`
pins that separation.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Self


class IndeedAsyncThrottle:
    """Async context manager that serializes calls and paces them apart."""

    def __init__(self, min_interval_seconds: float = 3.0) -> None:
        self._min_interval: float = min_interval_seconds
        self._lock: asyncio.Lock = asyncio.Lock()
        self._last_exit: float | None = None

    async def __aenter__(self) -> Self:
        await self._lock.acquire()
        if self._last_exit is not None:
            elapsed = time.monotonic() - self._last_exit
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._last_exit = time.monotonic()
        self._lock.release()
