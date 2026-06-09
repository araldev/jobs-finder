"""Aggregator use case: orchestrate the 3 source use cases in parallel + dedup.

Spec: REQ-A-001..REQ-A-006 (jobs-aggregator-endpoint) +
REQ-AR-001..REQ-AR-007 (jobs-aggregator-ranking).

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
  6. (REQ-AR-002) Ranks the deduped list per the configured
     `ranking_strategy` (default `posted_at` DESC; `priority`
     groups by source; `none` preserves input order). Ranking is
     post-cache: the cache key `(source, keywords, location, limit)`
     does NOT include the strategy, so flipping the strategy does
     not invalidate the cache.
  7. Returns an `AggregatedResult` with the ranked jobs, the per-
     source breakdown (for the `X-Aggregator-Errors` header), and
     the per-source `cache_statuses` (for the joined `X-Cache`
     header).

The module depends ONLY on `domain/`, `application/ports`,
`application/usecases/_cached_search`, and `application/ranking`.
It MUST NOT import `infrastructure/` or `presentation/` — the
dependency rule `presentation → application → domain ← infrastructure`
is enforced by `test_aggregator_does_not_import_infrastructure_or_presentation`.

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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, cast

from jobs_finder.application.ranking import (
    DEFAULT_PRIORITY_MAP,
    RankingStrategy,
    rank_jobs,
)
from jobs_finder.application.usecases._cached_search import SearchResult
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job

# Type aliases for the 2 injected pure-function helpers
# (REQ-FILTER-001 + REQ-SCORE-001, T-004). The signatures
# match `filter_infojobs_results` (in
# `infrastructure.aggregator_filters`) and `keyword_score` (in
# `infrastructure.keyword_score`). The aggregator does NOT
# import the concrete modules — the dependency rule
# `application → domain ← infrastructure` is preserved by
# constructor injection (`app_factory` wires the real
# functions at composition-root time). Tests can inject fakes
# to assert the dispatch behavior.
_FilterInfoJobsFn = Callable[[list[Job], set[str]], list[Job]]
_KeywordScoreFn = Callable[[Job, set[str]], float]


# Default no-op implementations for the 2 helpers — used when
# the aggregator is constructed without the kwargs (e.g. in
# the existing test suite that does not exercise the filter or
# the scoring). The defaults preserve the v1 contract: a
# default-constructed aggregator behaves EXACTLY like the
# pre-T-004 one (no filter, `posted_at` sort, no opt-in score).
# The "no filter" default is the identity function; the "no
# score" default always returns 0.0 (the `posted_at` sort
# step then uses `posted_at` as the primary key).
def _noop_keyword_score(_job: Job, _query_tokens: set[str]) -> float:
    """Default no-op scorer: always returns 0.0.

    The aggregator's `posted_at` sort (the v1 default) does
    not use the score; this default is the sentinel "no
    score-based ranking is active" value.
    """
    return 0.0


def _identity_filter(jobs: list[Job], _query_tokens: set[str]) -> list[Job]:
    """Default no-op filter: returns a copy of the input list.

    Preserves the v1 contract: when the aggregator is built
    without an injected `filter_infojobs_results` callable,
    no InfoJobs filter is applied. The function returns a new
    `list[Job]` (not the input reference) so downstream code
    that mutates the filtered list does not corrupt the input.
    """
    return list(jobs)


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

    The 4th `geo_id: int | None = None` kwarg (added in
    `fix-linkedin-geoid`, REQ-LOC-GEO-001) is the
    LinkedIn-specific numeric `geoId` the resolver returned
    for `location`. The aggregator forwards the kwarg ONLY
    to the LinkedIn use case (per `SearchAllSourcesUseCase.search`
    dispatch); Indeed + InfoJobs use cases ignore it. The
    default `None` preserves backward compat for the
    pre-WU3 caller shape.
    """

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
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
    """Orchestrates the 3 source use cases in parallel + dedup + rank.

    Constructor takes the 3 source use cases (typically the
    `CachedJobSearchUseCase` instances that the per-source routes
    use; the type is `_AggregatorSourcePort` so a raw port also
    satisfies the constructor — see the Protocol docstring for
    why the type is broader than the public `JobSearchPort`).
    The use case trusts the input: it validates the requested
    `sources` against the known 3 names and raises `ValueError`
    for any unknown name before invoking any port.

    Two keyword-only `__init__` parameters (added in
    `jobs-aggregator-ranking`) configure the post-dedup ranking
    step (REQ-AR-002, REQ-AR-003, REQ-AR-004):

    - `ranking_strategy`: closed set `Literal["posted_at", "priority",
      "none"]` (default `"posted_at"`). The Pydantic `Literal` on
      `Settings.aggregator_ranking_strategy` rejects unknown
      values at startup; the `rank_jobs` function raises
      `ValueError` as a defensive backstop for direct callers.
    - `priority_map`: `dict[str, int]` mapping source name to
      priority (default `DEFAULT_PRIORITY_MAP` —
      LinkedIn=0, Indeed=1, InfoJobs=2). Used as the primary
      sort key for `strategy="priority"` and as the tie-breaker
      for `strategy="posted_at"`. Unknown source names get
      `MISSING_SOURCE_PRIORITY` (999, last).

    Both params have defaults so existing callers (with no
    keyword args) keep working — backward-compatible.
    """

    def __init__(
        self,
        linkedin_use_case: _AggregatorSourcePort,
        indeed_use_case: _AggregatorSourcePort,
        infojobs_use_case: _AggregatorSourcePort,
        *,
        ranking_strategy: RankingStrategy = "posted_at",
        priority_map: dict[str, int] = DEFAULT_PRIORITY_MAP,
        filter_infojobs_results: _FilterInfoJobsFn | None = None,
        keyword_score: _KeywordScoreFn | None = None,
    ) -> None:
        self._sources: dict[str, _AggregatorSourcePort] = {
            "linkedin": linkedin_use_case,
            "indeed": indeed_use_case,
            "infojobs": infojobs_use_case,
        }
        self._ranking_strategy = ranking_strategy
        self._priority_map = priority_map
        # The 2 pure-function helpers are constructor-injected
        # (REQ-FILTER-001 + REQ-SCORE-001, T-004). The
        # dependency rule
        # `application → domain ← infrastructure` is preserved
        # by NOT importing the concrete modules from
        # `infrastructure/`. The defaults are no-op fallbacks
        # that preserve the v1 contract (no filter, no opt-in
        # score). The `app_factory` wires the real functions
        # at composition-root time.
        self._filter_infojobs_results: _FilterInfoJobsFn = (
            filter_infojobs_results if filter_infojobs_results is not None else _identity_filter
        )
        self._keyword_score: _KeywordScoreFn = (
            keyword_score if keyword_score is not None else _noop_keyword_score
        )

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str],
        *,
        linkedin_geo_id: int | None = None,
        query_tokens: frozenset[str] = frozenset(),
        enable_keyword_scoring: bool = False,
    ) -> AggregatedResult:
        """Run the queried sources in parallel, dedupe, and return the aggregated result.

        The per-source calls are ordered by `SOURCE_PRIORITY` so the
        dedup picks the first occurrence in priority order. Each
        `JobSearchError` is caught and recorded in
        `AggregatedResult.per_source`; any other exception (a
        programming bug, e.g. `KeyError`) re-raises so the route
        returns 500.

        The keyword-only `linkedin_geo_id: int | None = None`
        kwarg (added in `fix-linkedin-geoid`, REQ-LOC-GEO-001)
        is the LinkedIn-specific numeric `geoId` the resolver
        returned. The aggregator forwards the kwarg ONLY to
        the LinkedIn use case; Indeed + InfoJobs use cases are
        called WITHOUT the kwarg (they accept `location=`
        strings; they don't need a `geoId=`). The default
        `None` preserves the pre-WU3 call shape: a caller
        that doesn't pass `linkedin_geo_id` gets the same
        behavior as before (LinkedIn scraper falls back to
        `?location=<str>`).
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

            The `geo_id` kwarg is forwarded ONLY to the LinkedIn
            use case (the per-source kwarg is part of
            `JobSearchCacheKey` 5th field; Indeed + InfoJobs
            ports ignore the kwarg).
            """
            port = self._sources[source]
            try:
                if source == "linkedin":
                    result = await port.search(keywords, location, limit, geo_id=linkedin_geo_id)
                else:
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

        # REQ-FILTER-001: client-side filter for the InfoJobs
        # slice (post-cache, post-dedup, post-scrape). The
        # filter is a pure function over the InfoJobs slice; a
        # job is kept iff `len(tokenize(job.title) & query_tokens) > 0`.
        # LinkedIn + Indeed slices are NOT filtered. When
        # `query_tokens` is empty (the v1 default), the filter
        # is a no-op (the injected function short-circuits on
        # empty `query_tokens`).
        deduped_list = list(dedup_map.values())
        if query_tokens:
            infojobs_jobs = [j for j in deduped_list if "infojobs" in j.sources]
            other_jobs = [j for j in deduped_list if "infojobs" not in j.sources]
            filtered_infojobs = self._filter_infojobs_results(
                [j.job for j in infojobs_jobs], set(query_tokens)
            )
            filtered_infojobs_ids = {id(j) for j in filtered_infojobs}
            kept_infojobs = [
                j
                for j in infojobs_jobs
                if j.job in filtered_infojobs or id(j.job) in filtered_infojobs_ids
            ]
            deduped_list = other_jobs + kept_infojobs

        # REQ-AR-002 / REQ-AR-003 + REQ-SCORE-001: post-cache
        # ranking step. The `rank_jobs` function is a pure
        # function on the deduped `list[AggregatedJob]`; it
        # returns a new list, leaving the dedup map (and the
        # per-source + cache_statuses structures) untouched.
        # When `enable_keyword_scoring=True`, the opt-in
        # `keyword_score` sort is used: jobs are sorted by
        # `keyword_score desc, posted_at desc`. When
        # `False` (the default), the existing `rank_jobs`
        # path is used — the v1 contract is preserved.
        if enable_keyword_scoring:
            tokens_set = set(query_tokens)
            ranked_jobs = sorted(
                deduped_list,
                key=lambda j: (
                    self._keyword_score(j.job, tokens_set),
                    j.job.posted_at,
                ),
                reverse=True,
            )
        else:
            ranked_jobs = rank_jobs(
                jobs=deduped_list,
                strategy=self._ranking_strategy,
                priority_map=self._priority_map,
            )

        return AggregatedResult(
            jobs=ranked_jobs,
            per_source=per_source,
            cache_statuses=cache_statuses,
        )
