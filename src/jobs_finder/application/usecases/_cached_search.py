"""Cache-wrapping use case for any `JobSearchPort`.

Spec: REQ-C-004, REQ-C-005, REQ-C-006.

`CachedJobSearchUseCase` composes a `JobSearchPort` with a
`CachePort[JobSearchCacheKey, list[Job]]` so repeated identical
queries within the TTL window return the cached `list[Job]`
without invoking the underlying port. The wrapper's `search`
returns a `SearchResult(jobs, cache_status)` named tuple so the
route can read the `cache_status` to set the `X-Cache` response
header (REQ-C-003).

The wrapper itself is a `JobSearchPort` (same surface: an async
`search(keywords, location, limit)` method), so the composition
root can swap a raw use case for a cached one without touching
the route handler.

The module is a single file with the wrapper, `SearchResult`, and
`CacheStatus` colocated. The leading underscore in the file name
flags it as a private use-case helper (not a per-source binding);
the per-source use-case modules
(`search_linkedin_jobs.py`, `search_indeed_jobs.py`,
`search_infojobs_jobs.py`) wrap the raw use case + cache for
their source. In practice the default branch in
`app_factory.build_app()` uses `CachedJobSearchUseCase` directly
with a `source` label, so the per-source use-case modules
delegate to the cache wrapper rather than wrapping their own
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jobs_finder.application.ports import (
    CachePort,
    JobSearchCacheKey,
    JobSearchPort,
)
from jobs_finder.domain.job import Job


class CacheStatus(StrEnum):
    """Whether a `search` call was served from the cache or freshly scraped.

    The enum's `value` is the exact string emitted in the `X-Cache`
    response header (REQ-C-003): `"HIT"` or `"MISS"`.
    """

    HIT = "HIT"
    MISS = "MISS"


@dataclass(frozen=True)
class SearchResult:
    """The return shape of `CachedJobSearchUseCase.search`.

    `jobs` is the list of jobs (cached or freshly scraped).
    `cache_status` is `HIT` if the response came from the cache,
    `MISS` if the port was invoked.
    """

    jobs: list[Job]
    cache_status: CacheStatus


class CachedJobSearchUseCase:
    """Wraps a `JobSearchPort` with a TTL cache.

    The wrapper is itself a `JobSearchPort` (same interface); the
    composition root in `app_factory.py` builds it by composing
    the raw port + the cache. Tests can inject a `_FakeCachePort`
    (or the real `InMemoryTTLCache`) to assert cache-hit behavior
    end-to-end.

    The wrapper is source-agnostic: the same wrapper is used by
    all 3 source use cases (LinkedIn, Indeed, InfoJobs). The
    `source` label is part of the cache key (REQ-C-005) so a
    query on one source does not share an entry with another
    source.
    """

    def __init__(
        self,
        port: JobSearchPort,
        cache: CachePort[JobSearchCacheKey, list[Job]],
        source: str,
    ) -> None:
        self._port = port
        self._cache = cache
        self._source = source

    async def search(self, keywords: str, location: str, limit: int = 20) -> SearchResult:
        """Run the search, served from the cache when possible.

        On a cache hit, the underlying port is NOT invoked and the
        cached `list[Job]` is returned. On a miss, the port is
        invoked and the result is stored in the cache before
        being returned. Port exceptions propagate to the caller
        without being stored (REQ-C-006 — no stale-error
        poisoning).
        """
        key = JobSearchCacheKey(
            source=self._source,
            keywords=keywords,
            location=location,
            limit=limit,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return SearchResult(jobs=cached, cache_status=CacheStatus.HIT)
        result = await self._port.search(keywords, location, limit)
        # Only cache successful results. Errors (502) propagate
        # to the caller without poisoning the cache.
        self._cache.set(key, result)
        return SearchResult(jobs=result, cache_status=CacheStatus.MISS)
