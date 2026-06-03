"""Aggregator use case: orchestrate the 3 source use cases in parallel + dedup.

Spec: REQ-A-001..REQ-A-006.

The aggregator is a thin composition layer over the 3 existing
per-source `CachedJobSearchUseCase` instances. It:

  1. Validates the requested sources (unknown names raise `ValueError`
     before any port is invoked).
  2. Invokes the queried sources in parallel via `asyncio.gather`,
     ordered by `SOURCE_PRIORITY` (LinkedIn > Indeed > InfoJobs) so
     the dedup picks the first occurrence in that order.
  3. Unifies the wrapped use case's `SearchResult(jobs, cache_status)`
     return shape with a raw port's `list[Job]` return shape via
     `hasattr` + `cast` detection. Wrapped use cases expose a
     `cache_status` (HIT/MISS); raw ports are always a fresh MISS.
  4. Isolates per-source `JobSearchError` — one source failing does
     NOT take down the aggregator. Non-`JobSearchError` exceptions
     (programming bugs) re-raise so the route returns 500.
  5. Deduplicates jobs by the `(title, company, location)` key
     (lowercased + whitespace-stripped). The first occurrence wins
     (LinkedIn > Indeed > InfoJobs); subsequent occurrences append
     their source name to the `sources` list.
  6. Returns an `AggregatedResult` with the deduped jobs, the per-
     source breakdown (for the `X-Aggregator-Errors` header), and
     the per-source `cache_statuses` (for the joined `X-Cache`
     header).

The module depends ONLY on `domain/`, `application/ports`, and
`application/usecases/_cached_search`. It MUST NOT import
`infrastructure/` or `presentation/` — the dependency rule
`presentation → application → domain ← infrastructure` is enforced
by `test_aggregator_does_not_import_infrastructure_or_presentation`.

The constructor is typed against a private `_AggregatorSourcePort`
Protocol that accepts BOTH `list[Job]` (raw port) and `SearchResult`
(cached wrapper) return shapes via a Union. This is intentional:
`JobSearchPort` is typed as `-> list[Job]`, but the cached wrapper
returns `-> SearchResult`. The aggregator's runtime detection
unifies both; the Union static type captures both shapes so neither
production callers (`app_factory.build_app`) nor tests need
`# type: ignore` at the call site.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, cast

from jobs_finder.application.usecases._cached_search import SearchResult
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job

# Source priority order: LinkedIn first, Indeed second, InfoJobs third.
# When deduplicating, the first occurrence in this order wins; the
# `sources` list is populated with all sources where the job appeared.
# Stored as a `tuple` (immutable) so callers cannot mutate the priority.
SOURCE_PRIORITY: tuple[str, ...] = ("linkedin", "indeed", "infojobs")


class _AggregatorSourcePort(Protocol):
    """Structural type for a source port accepted by the aggregator.

    Production callers pass `CachedJobSearchUseCase` (which returns
    `SearchResult`); tests may pass a raw port (which returns
    `list[Job]`). The Union return type captures both shapes
    statically; the runtime `hasattr(result, "jobs")` check in
    `_call_one` narrows to the right one. This is broader than the
    public `JobSearchPort` Protocol (which is typed as
    `-> list[Job]`); the broader type is what the aggregator's
    "handles both raw and wrapped" promise actually requires.
    """

    async def search(
        self, keywords: str, location: str, limit: int = 20
    ) -> list[Job] | SearchResult: ...


@dataclass(frozen=True)
class SourceResult:
    """The result of querying one source.

    `jobs` is the (possibly empty) list of `Job` objects returned
    by the source. `error` is `None` if the source succeeded, else
    a `JobSearchError` subclass. `cache_status` is `"HIT"` or
    `"MISS"` per the wrapped `CachedJobSearchUseCase`'s
    `SearchResult.cache_status` (raw ports are always `"MISS"`).

    Exactly one of `jobs` (possibly empty) and `error` is set; a
    successful source can return an empty list (no results for the
    query). `cache_status` is always set — a failing source still
    records the wrapper's cache status (the wrapper sets it on a
    miss, even if the underlying port raises; on a hit the
    underlying port is not called so the error is impossible).
    """

    source: str
    jobs: list[Job] = field(default_factory=list)
    error: JobSearchError | None = None
    cache_status: str = "MISS"

    @property
    def succeeded(self) -> bool:
        """`True` iff the source returned without raising `JobSearchError`."""
        return self.error is None


@dataclass(frozen=True)
class AggregatedJob:
    """A `Job` with a non-empty `sources` list.

    `job` is the canonical `Job` (from the first source that
    returned it, in source-priority order). `sources` is the
    list of source names where the job appeared, in source-priority
    order (LinkedIn > Indeed > InfoJobs).
    """

    job: Job
    sources: list[str]


@dataclass(frozen=True)
class AggregatedResult:
    """The result of the aggregator.

    `jobs` is the deduped union of the queried sources' results,
    each with a non-empty `sources` list. `per_source` maps the
    queried source name to its `SourceResult` (for observability
    + the `X-Aggregator-Errors` header). `cache_statuses` maps
    the queried source name to its `"HIT"` or `"MISS"` value
    (for the joined `X-Cache` header).
    """

    jobs: list[AggregatedJob]
    per_source: dict[str, SourceResult]
    cache_statuses: dict[str, str]


class SearchAllSourcesUseCase:
    """Orchestrates the 3 source use cases in parallel + dedup.

    Constructor takes the 3 source use cases (typically the
    `CachedJobSearchUseCase` instances that the per-source routes
    use; the type is `_AggregatorSourcePort` so a raw port also
    satisfies the constructor — see the Protocol docstring for
    why the type is broader than the public `JobSearchPort`).
    The use case trusts the input: it validates the requested
    `sources` against the known 3 names and raises `ValueError`
    for any unknown name before invoking any port.
    """

    def __init__(
        self,
        linkedin_use_case: _AggregatorSourcePort,
        indeed_use_case: _AggregatorSourcePort,
        infojobs_use_case: _AggregatorSourcePort,
    ) -> None:
        self._sources: dict[str, _AggregatorSourcePort] = {
            "linkedin": linkedin_use_case,
            "indeed": indeed_use_case,
            "infojobs": infojobs_use_case,
        }

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str],
    ) -> AggregatedResult:
        """Run the queried sources in parallel, dedupe, and return the aggregated result.

        The per-source calls are ordered by `SOURCE_PRIORITY` so the
        dedup picks the first occurrence in priority order. Each
        `JobSearchError` is caught and recorded in
        `AggregatedResult.per_source`; any other exception (a
        programming bug, e.g. `KeyError`) re-raises so the route
        returns 500.
        """
        # Validate the requested sources.
        unknown = set(sources) - set(self._sources.keys())
        if unknown:
            raise ValueError(f"unknown sources: {sorted(unknown)}")

        async def _call_one(source: str) -> SourceResult:
            """Invoke one source and unify the return shape.

            The cached wrapper returns `SearchResult(jobs, cache_status)`;
            a raw port returns `list[Job]`. The two are unified via
            `hasattr(result, "jobs")` + `cast` so the constructor's
            broad `JobSearchPort` typing is honored (and a future
            swap of the wrapper for the raw port does not break
            the aggregator).
            """
            port = self._sources[source]
            try:
                result = await port.search(keywords, location, limit)
            except JobSearchError as exc:
                # Per-source error isolation: record the failed
                # source in `per_source` so the route can surface
                # it in `X-Aggregator-Errors`. Re-raise non-`JobSearchError`
                # exceptions (a programming bug, e.g. `KeyError`)
                # so the registered handler maps it to 500.
                return SourceResult(source=source, error=exc)
            except Exception:
                # Non-`JobSearchError`: programming bug, re-raise so
                # the registered handler maps it to 500. Do not
                # swallow the traceback.
                raise

            if hasattr(result, "jobs"):
                # Wrapped use case: `SearchResult(jobs, cache_status)`.
                cached = cast(SearchResult, result)
                return SourceResult(
                    source=source,
                    jobs=cached.jobs,
                    cache_status=cached.cache_status.value,
                )
            # Raw port: bare `list[Job]`. Treat as a fresh MISS
            # so the route's `X-Cache` header stays consistent
            # (raw ports are never cached, so a MISS is correct).
            # mypy narrows the `hasattr` else branch to `list[Job]`
            # (the `SearchResult` member is excluded by the check).
            return SourceResult(
                source=source,
                jobs=result,
                cache_status="MISS",
            )

        # Build the per-source tasks in source-priority order so the
        # dedup picks the first occurrence in that order (the
        # `asyncio.gather` arrival order is NOT deterministic; the
        # source-priority order in `ordered_sources` is). Using
        # `SOURCE_PRIORITY.index` directly as the `sorted` key avoids
        # an unnecessary lambda wrapper.
        ordered_sources = sorted(sources, key=SOURCE_PRIORITY.index)
        results = await asyncio.gather(*(_call_one(s) for s in ordered_sources))

        # Build the dedup map. Iteration order is `ordered_sources`
        # order, so the `sources` list accumulates in source-priority
        # order naturally.
        dedup_map: dict[tuple[str, str, str], AggregatedJob] = {}
        per_source: dict[str, SourceResult] = {}
        cache_statuses: dict[str, str] = {}
        for result in results:
            per_source[result.source] = result
            cache_statuses[result.source] = result.cache_status
            for job in result.jobs:
                key = (
                    job.title.strip().lower(),
                    job.company.strip().lower(),
                    job.location.strip().lower(),
                )
                if key in dedup_map:
                    # Already seen: append the source name to the
                    # `sources` list (still in source-priority order
                    # because we iterate `ordered_sources`).
                    dedup_map[key].sources.append(result.source)
                else:
                    dedup_map[key] = AggregatedJob(job=job, sources=[result.source])

        return AggregatedResult(
            jobs=list(dedup_map.values()),
            per_source=per_source,
            cache_statuses=cache_statuses,
        )
