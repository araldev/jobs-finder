"""Unit tests for `CachedJobSearchUseCase` + `SearchResult` + `CacheStatus`.

Spec: REQ-C-004, REQ-C-005, REQ-C-006.

The wrapper composes a `JobSearchPort` with a `CachePort` so
repeated identical queries within the TTL window return the
cached `list[Job]` without invoking the port. The wrapper is
itself a `JobSearchPort` (same surface) but its `search` returns
a `SearchResult` named tuple so the route can read the
`cache_status` to set the `X-Cache` response header.

This test file is the RED → GREEN → REFACTOR anchor for T-002.
It must be authored BEFORE the production class, run to confirm
it fails (RED), then the production class is added, then the test
passes (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobs_finder.application.ports import (
    JobSearchCacheKey,
    JobSearchPort,
)
from jobs_finder.application.usecases._cached_search import (
    CachedJobSearchUseCase,
    CacheStatus,
    SearchResult,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _job(idx: int) -> Job:
    return Job(
        id=f"j{idx}",
        title=f"Title {idx}",
        company="Co",
        location="Madrid",
        url=f"https://example.com/j{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


class _FakeJobSearchPort:
    """In-memory fake of `JobSearchPort`.

    Records every call. Can be primed with jobs and/or a fixed
    exception to raise. Mirrors the `FakeJobSearchPort` used by the
    other test files but is defined inline here so this test file
    remains self-contained.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        self.calls.append((keywords, location, limit))
        if self._error is not None:
            raise self._error
        return list(self._jobs)


class _FakeCachePort:
    """In-memory fake of `CachePort` for tests.

    Mirrors the `InMemoryTTLCache` behavior (no real TTL, no lock)
    but allows tests to introspect the store and reset state.
    """

    def __init__(self) -> None:
        self._store: dict[JobSearchCacheKey, list[Job]] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key: JobSearchCacheKey) -> list[Job] | None:
        self.get_calls += 1
        value = self._store.get(key)
        return list(value) if value is not None else None

    async def set(self, key: JobSearchCacheKey, value: list[Job]) -> None:
        self.set_calls += 1
        self._store[key] = list(value)

    async def delete(self, key: JobSearchCacheKey) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# SearchResult / CacheStatus shape
# ---------------------------------------------------------------------------


def test_search_result_carries_jobs_and_cache_status() -> None:
    """`SearchResult(jobs, cache_status)` is a frozen dataclass with both fields."""
    result = SearchResult(jobs=[_job(1)], cache_status=CacheStatus.HIT)
    assert result.jobs == [_job(1)]
    assert result.cache_status is CacheStatus.HIT


def test_search_result_is_immutable() -> None:
    """`SearchResult` is frozen — assigning to a field raises."""
    result = SearchResult(jobs=[_job(1)], cache_status=CacheStatus.HIT)
    with pytest.raises((AttributeError, TypeError)):  # frozen dataclass
        result.jobs = []  # type: ignore[misc]


def test_cache_status_has_hit_and_miss() -> None:
    """`CacheStatus` enum has exactly HIT and MISS members."""
    assert CacheStatus.HIT.value == "HIT"
    assert CacheStatus.MISS.value == "MISS"
    assert {s.value for s in CacheStatus} == {"HIT", "MISS"}


# ---------------------------------------------------------------------------
# Cache miss → port call → store → return (REQ-C-004)
# ---------------------------------------------------------------------------


async def test_first_call_is_a_miss_and_invokes_the_port() -> None:
    """On an empty cache, the wrapper invokes the port and returns MISS."""
    port = _FakeJobSearchPort(jobs=[_job(1), _job(2)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    result = await wrapper.search("python", "madrid", 20)

    assert result.jobs == [_job(1), _job(2)]
    assert result.cache_status is CacheStatus.MISS
    assert port.calls == [("python", "madrid", 20)]


async def test_cache_miss_stores_the_result_in_the_cache() -> None:
    """On a miss, the port's return value is stored in the cache after the call."""
    port = _FakeJobSearchPort(jobs=[_job(1)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    await wrapper.search("python", "madrid", 20)

    expected_key = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20
    )
    assert await cache.get(expected_key) == [_job(1)]


async def test_cache_hit_does_not_invoke_the_port() -> None:
    """A second identical call within the TTL returns HIT and does not call the port."""
    port = _FakeJobSearchPort(jobs=[_job(1)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    # First call: MISS, port invoked.
    first = await wrapper.search("python", "madrid", 20)
    assert first.cache_status is CacheStatus.MISS
    assert port.calls == [("python", "madrid", 20)]

    # Second call: HIT, port NOT invoked.
    second = await wrapper.search("python", "madrid", 20)
    assert second.cache_status is CacheStatus.HIT
    assert second.jobs == [_job(1)]
    assert port.calls == [("python", "madrid", 20)]  # still one call


# ---------------------------------------------------------------------------
# Error propagation (REQ-C-006: errors do NOT poison the cache)
# ---------------------------------------------------------------------------


async def test_port_exception_propagates_and_does_not_store_to_cache() -> None:
    """A port exception propagates to the caller and the cache stays empty."""
    port = _FakeJobSearchPort(error=JobSearchError("upstream is down"))
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    with pytest.raises(JobSearchError, match="upstream is down"):
        await wrapper.search("python", "madrid", 20)

    # The cache must NOT have stored the failure.
    expected_key = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20
    )
    assert await cache.get(expected_key) is None


async def test_subclass_of_job_search_error_propagates() -> None:
    """A subclass of `JobSearchError` propagates as its actual type, not the parent."""

    class _CustomBlockedError(JobSearchError):
        pass

    port = _FakeJobSearchPort(error=_CustomBlockedError("auth wall"))
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    with pytest.raises(_CustomBlockedError, match="auth wall"):
        await wrapper.search("python", "madrid", 20)


async def test_repeated_failure_does_not_serve_cached_error() -> None:
    """Two consecutive port failures are both invoked (no stale error cache)."""
    port = _FakeJobSearchPort(error=JobSearchError("upstream is down"))
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    with pytest.raises(JobSearchError):
        await wrapper.search("python", "madrid", 20)
    with pytest.raises(JobSearchError):
        await wrapper.search("python", "madrid", 20)

    # The port was invoked twice (no cached error shortcutting the 2nd call).
    assert port.calls == [("python", "madrid", 20), ("python", "madrid", 20)]


async def test_prior_success_then_failure_does_not_overwrite_cache() -> None:
    """A prior success + manual cache clear + later failure leaves the cache empty.

    The scenario: cache had a successful entry, the entry is cleared
    (simulating TTL expiry or manual invalidation), the port is primed
    to fail, and the next call hits a fresh miss. The port fails, the
    exception propagates, and the cache MUST NOT be updated with the
    failure (REQ-C-006 — no stale-error poisoning).
    """
    # 1) First call: success → cache has entry.
    port = _FakeJobSearchPort(jobs=[_job(1)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    first = await wrapper.search("python", "madrid", 20)
    assert first.cache_status is CacheStatus.MISS

    # 2) Simulate TTL expiry: clear the cache. The port is now primed
    #    to fail. A fresh miss will invoke the port and raise.
    await cache.clear()
    port._error = JobSearchError("upstream is down")
    with pytest.raises(JobSearchError, match="upstream is down"):
        await wrapper.search("python", "madrid", 20)

    # 3) The cache MUST still be empty (failure was NOT stored).
    expected_key = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20
    )
    assert await cache.get(expected_key) is None

    # 4) Clear the error; the next call is STILL a miss (cache was
    #    never re-populated), and the port returns fresh data.
    port._error = None
    port._jobs = [_job(2)]
    third = await wrapper.search("python", "madrid", 20)
    assert third.cache_status is CacheStatus.MISS
    assert third.jobs == [_job(2)]


# ---------------------------------------------------------------------------
# Per-source key isolation (REQ-C-005)
# ---------------------------------------------------------------------------


async def test_different_sources_with_same_query_have_distinct_cache_entries() -> None:
    """Two sources with the same query do not share a cache entry."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    linkedin_cache = _FakeCachePort()
    indeed_cache = _FakeCachePort()
    linkedin = CachedJobSearchUseCase(port=linkedin_port, cache=linkedin_cache, source="linkedin")
    indeed = CachedJobSearchUseCase(port=indeed_port, cache=indeed_cache, source="indeed")

    linkedin_result = await linkedin.search("python", "madrid", 20)
    indeed_result = await indeed.search("python", "madrid", 20)

    assert linkedin_result.jobs == [_job(1)]
    assert indeed_result.jobs == [_job(2)]
    # Each cache has its own entry.
    linkedin_key = JobSearchCacheKey(
        source="linkedin", keywords="python", location="madrid", limit=20
    )
    indeed_key = JobSearchCacheKey(source="indeed", keywords="python", location="madrid", limit=20)
    assert await linkedin_cache.get(linkedin_key) == [_job(1)]
    assert await indeed_cache.get(indeed_key) == [_job(2)]


# ---------------------------------------------------------------------------
# Key shape (REQ-C-001: tuple key includes source)
# ---------------------------------------------------------------------------


async def test_cache_key_includes_all_four_fields() -> None:
    """The cache key is `JobSearchCacheKey(source, keywords, location, limit)`."""
    port = _FakeJobSearchPort(jobs=[_job(1)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="infojobs")

    await wrapper.search("rust", "barcelona", 5)

    expected_key = JobSearchCacheKey(
        source="infojobs", keywords="rust", location="barcelona", limit=5
    )
    assert await cache.get(expected_key) == [_job(1)]


# ---------------------------------------------------------------------------
# Default limit (REQ-009 mirror: 20)
# ---------------------------------------------------------------------------


async def test_search_uses_default_limit_twenty() -> None:
    """`search(keywords, location)` uses `limit=20` by default.

    The default is duplicated on the Pydantic schema at the
    presentation boundary; the use case's signature also defaults
    to 20 for source-agnostic safety.
    """
    port = _FakeJobSearchPort(jobs=[_job(1)])
    cache = _FakeCachePort()
    wrapper = CachedJobSearchUseCase(port=port, cache=cache, source="linkedin")

    result = await wrapper.search("python", "madrid")

    assert port.calls == [("python", "madrid", 20)]
    assert result.jobs == [_job(1)]


# ---------------------------------------------------------------------------
# Async shape
# ---------------------------------------------------------------------------


def test_search_is_a_coroutine_function() -> None:
    """`search` is a coroutine function (awaitable)."""
    import inspect  # noqa: PLC0415

    wrapper = CachedJobSearchUseCase(
        port=_FakeJobSearchPort(), cache=_FakeCachePort(), source="linkedin"
    )
    assert inspect.iscoroutinefunction(wrapper.search) is True


# ---------------------------------------------------------------------------
# Structural conformance with JobSearchPort
# ---------------------------------------------------------------------------


def test_wrapper_structurally_satisfies_job_search_port() -> None:
    """`CachedJobSearchUseCase` exposes an async `search` method (structural Protocol)."""
    import inspect  # noqa: PLC0415

    wrapper = CachedJobSearchUseCase(
        port=_FakeJobSearchPort(), cache=_FakeCachePort(), source="linkedin"
    )
    assert callable(getattr(wrapper, "search", None))
    assert inspect.iscoroutinefunction(wrapper.search)
    # The Protocol declares `search` as a method.
    protocol_attrs: set[str] = getattr(JobSearchPort, "__protocol_attrs__", set())
    assert "search" in protocol_attrs


# ---------------------------------------------------------------------------
# Dependency rule: the wrapper does not import infrastructure / presentation.
# ---------------------------------------------------------------------------


def test_cached_search_does_not_import_infrastructure_or_presentation() -> None:
    """`_cached_search.py` (application layer) has no infrastructure or presentation imports."""
    import ast  # noqa: PLC0415

    source_path = "src/jobs_finder/application/usecases/_cached_search.py"
    with open(source_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "infrastructure" not in joined, f"{source_path} imports infrastructure"
    assert "presentation" not in joined, f"{source_path} imports presentation"
    assert "playwright" not in joined, f"{source_path} imports playwright"
    assert "fastapi" not in joined, f"{source_path} imports fastapi"


# ---------------------------------------------------------------------------
# CacheStatus str-enum value (REQ-C-003: header value is "HIT" or "MISS")
# ---------------------------------------------------------------------------


def test_cache_status_is_a_str_enum() -> None:
    """`CacheStatus` is a `str, Enum` so `result.cache_status.value` is a string
    ready to drop into a response header.
    """
    assert isinstance(CacheStatus.HIT, str)
    assert isinstance(CacheStatus.MISS, str)
    # The value is the exact string the route emits in the X-Cache header.
    assert CacheStatus.HIT.value == "HIT"
    assert CacheStatus.MISS.value == "MISS"
