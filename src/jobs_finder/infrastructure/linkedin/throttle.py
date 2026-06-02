"""Per-process async throttle for serializing calls to a rate-limited source.

Spec: REQ-014.
Design: one `asyncio.Lock` per `AsyncThrottle` instance. On each `__aenter__`,
if the gap since the last `__aexit__` is less than `min_interval_seconds`,
the throttle awaits the remainder. Two `async with throttle:` calls on the
SAME instance always serialize (the lock blocks the second `__aenter__`
until the first `__aexit__` runs).

Per-process: the lock lives in the calling process. In a multi-worker
deployment each worker has its own throttle; this is documented as a known
limitation in the spec.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Self


class AsyncThrottle:
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
