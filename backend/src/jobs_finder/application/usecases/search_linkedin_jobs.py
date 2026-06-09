"""Use case: search LinkedIn for jobs matching a validated input.

Spec: REQ-008, REQ-010, REQ-011, REQ-012, REQ-C-001..REQ-C-006.

Two classes live in this module:

- `RawLinkedInJobsUseCase` (renamed from the original
  `SearchLinkedInJobsUseCase` in the `cache-ttl` change): the
  thin orchestrator that calls the port and returns `list[Job]`.
  This is the unwrapped implementation; it is a `JobSearchPort`
  (so the cached wrapper can compose it as its inner port).

- `SearchLinkedInJobsUseCase` (re-export of `CachedJobSearchUseCase`):
  the public class for the LinkedIn use case. The composition
  root (`app_factory.build_app()`) builds an instance of
  `CachedJobSearchUseCase` with `port=RawLinkedInJobsUseCase(...)`
  and exposes it as the LinkedIn use case. The re-export keeps
  the module's public surface stable so existing imports
  (`from jobs_finder.application.usecases.search_linkedin_jobs
  import SearchLinkedInJobsUseCase`) still resolve — they now
  point to the cached wrapper, which is what the route consumes.

The cached wrapper exposes `search(keywords, location, limit) ->
SearchResult`; the raw use case exposes `execute(input) ->
list[Job]`. Tests that exercise the raw use case should import
`RawLinkedInJobsUseCase` directly.
"""

from __future__ import annotations

from jobs_finder.application.dto import SearchLinkedInInput
from jobs_finder.application.ports import JobSearchPort
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.domain.job import Job


class RawLinkedInJobsUseCase:
    """Orchestrates a single job-search call against any `JobSearchPort`.

    Renamed from the original `SearchLinkedInJobsUseCase` in the
    `cache-ttl` change. The class is the unwrapped implementation;
    the public `SearchLinkedInJobsUseCase` (re-exported below) is
    the cached wrapper.
    """

    def __init__(self, port: JobSearchPort) -> None:
        self._port = port

    async def execute(self, input: SearchLinkedInInput) -> list[Job]:
        """Run the search and return the port's result unchanged.

        Spec: REQ-012. Exceptions from the port (`JobSearchError` and
        subclasses) propagate to the caller — the use case does not swallow
        them, does not retry, and does not return an empty list on failure.

        The `input.geo_id` (added in `fix-linkedin-geoid`) is
        the LinkedIn-specific numeric `geoId` the resolver
        returned. The kwarg is forwarded to the port so the
        LinkedIn scraper's URL builder emits `?geoId=<n>`
        (REQ-LOC-GEO-001).
        """
        return await self._port.search(
            input.keywords, input.location, input.limit, geo_id=input.geo_id
        )

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        """Structural `JobSearchPort` shim.

        `CachedJobSearchUseCase` (the cache wrapper added in the
        `cache-ttl` change) is typed against `JobSearchPort`, whose
        `search` method is the seam. Exposing `search` on the raw
        use case lets the cached wrapper compose the raw use case
        as its inner port without a Protocol rewrite. Delegates to
        `execute` so the original DTO-driven path is unchanged.

        The 4th `geo_id: int | None = None` kwarg (added in
        WU3) is forwarded via the DTO's `geo_id` field.
        """
        return await self.execute(
            SearchLinkedInInput(keywords=keywords, location=location, limit=limit, geo_id=geo_id)
        )


# Public re-export. `SearchLinkedInJobsUseCase` is the cached wrapper
# (`CachedJobSearchUseCase`) so existing imports resolve to the type
# the route consumes. Tests that need the raw orchestrator should
# import `RawLinkedInJobsUseCase` directly.
SearchLinkedInJobsUseCase = CachedJobSearchUseCase
