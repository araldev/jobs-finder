"""Integration tests for the Redis cache backend in the composition root.

Spec: REQ-PC-007 (fail-fast on Redis-down at lifespan startup).

The first scenario (unreachable) runs ALWAYS — it points the
client at a port that is guaranteed to refuse (port 1, reserved)
and asserts the exact `RuntimeError` regex. The second scenario
(reachable) is `@pytest.mark.skipif(not _redis_reachable())` so
CI without a real Redis on `localhost:6379` sees `SKIPPED`,
not failure. Both scenarios are Given/When/Then, observable
behavior, deterministic.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import redis.asyncio as redis_async
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app


def _redis_reachable() -> bool:
    """Return `True` if `redis://localhost:6379/0` accepts a `ping`.

    The helper tries a short-timeout `redis.asyncio.from_url(
    "redis://localhost:6379/0").ping()` and returns `True`
    only on success. The connection is closed immediately to
    avoid leaking sockets in the test process.
    """

    async def _probe() -> bool:
        client = redis_async.from_url(  # type: ignore[no-untyped-call]
            "redis://localhost:6379/0", decode_responses=False
        )
        try:
            return bool(await client.ping())
        except Exception:  # noqa: BLE001
            return False
        finally:
            await client.aclose()

    try:
        return asyncio.run(_probe())
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# REQ-PC-007 — Fail-fast on Redis-down at lifespan startup (2 scenarios)
# ---------------------------------------------------------------------------


def test_redis_unreachable_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-PC-007: when Redis is unreachable, `build_app()` lifespan raises `RuntimeError`.

    The error message matches the prefix
    `Redis cache backend selected but cannot connect to {url}:`
    so the integration smoke test catches a wording drift in the
    lifespan fail-fast logic. The exact text after the colon is
    OS-dependent ("Connection refused" on Linux, "Error 111 ..."
    on some Python builds, "actively refused" on Windows) so the
    test asserts the prefix + the URL, not the exact cause text.

    The test forces a `ConnectionError` by pointing
    `CACHE_REDIS_URL` at a port that is guaranteed to refuse
    connections (port 1 — reserved, never listening). This
    scenario runs ALWAYS — no real Redis is required because
    the test is asserting the FAILURE path, not the happy path.
    """
    # `CACHE_REDIS_URL=redis://localhost:1/0` is the canonical
    # "port that refuses" target — port 1 is reserved and never
    # has a Redis server.
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("CACHE_REDIS_URL", "redis://localhost:1/0")
    settings = Settings()

    app: FastAPI = build_app(settings=settings)

    async def _run_lifespan() -> None:
        async with LifespanManager(app):
            pass  # pragma: no cover -- the lifespan should fail before this

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_run_lifespan())

    message = str(exc_info.value)
    # The error format is: `Redis cache backend selected but cannot
    # connect to {url}: {cause}`. The exact text of `{cause}` is
    # OS-dependent so the test asserts the prefix + the URL.
    expected_prefix = (
        f"Redis cache backend selected but cannot connect to {settings.cache_redis_url}:"
    )
    assert message.startswith(expected_prefix), f"unexpected error message: {message!r}"
    assert len(message) > len(expected_prefix), f"error message lacks cause: {message!r}"


@pytest.mark.skipif(not _redis_reachable(), reason="Redis not reachable on localhost:6379")
def test_redis_reachable_app_starts_and_aclose_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-PC-007: when Redis is reachable, the app starts and `ping()` succeeded.

    The test points `CACHE_REDIS_URL` at the local Redis
    (`localhost:6379`, which the `skipif` already verified is
    reachable) and runs the lifespan. The fact that the
    lifespan starts (no `RuntimeError`) AND the lifespan
    shuts down cleanly (`aclose()` returned without raising)
    verifies both the `ping()` smoke test and the `aclose()`
    shutdown path.
    """
    # The skipif guarantees Redis is reachable on
    # `localhost:6379`, so this is the real-Redis happy path.
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("CACHE_REDIS_URL", "redis://localhost:6379/0")
    settings = Settings()

    app: FastAPI = build_app(settings=settings)

    async def _run_lifespan() -> Any:  # noqa: ANN401
        async with LifespanManager(app):
            # No-op: the lifespan startup ran `ping()` and the
            # shutdown will run `aclose()`. Both must succeed
            # without raising; the `async with` block returning
            # proves the lifespan was entered and exited cleanly.
            return "ok"

    result = asyncio.run(_run_lifespan())
    assert result == "ok"
