"""Pure ranking function for the aggregator's deduped results.

Spec: REQ-AR-002..REQ-AR-007 (jobs-aggregator-ranking).

The aggregator (`SearchAllSourcesUseCase.search()`) invokes
`rank_jobs` AFTER the dedup step on `list(dedup_map.values())`.
The function is a leaf in the application layer — no I/O, no
state, no side effects, dependency-free (only stdlib +
`domain.job` + `application.aggregator` types). It can be tested
in pure isolation; the integration tests cover the
`SearchAllSourcesUseCase` wiring.

Strategies (closed set, REQ-AR-003):

- `"posted_at"` (default): sort by `posted_at` DESC; tie-broken
  by `priority_map` ASC, then `job.id` ASC. Jobs with
  `posted_at=None` sink to the bottom (defensive — current
  scrapers never return `None`; the branch future-proofs against
  a refactor that does).
- `"priority"`: sort by `priority_map` ASC, tie-broken by
  `posted_at` DESC, then `job.id` ASC. Ignores freshness; useful
  for "I trust LinkedIn more than Indeed" deployments.
- `"none"`: preserve input order. Escape hatch for clients
  depending on the pre-change source-priority + scrape-order
  behavior.

Pinned invariants:

- The input list is NEVER mutated. `rank_jobs` returns a new
  list; the dedup map is left untouched for debugging.
- `sorted` is stable; equal keys preserve input order.
- `None` `posted_at` sinks to the bottom of `posted_at` strategy.
  Within the None group, the priority tie-breaker still applies.
- Unknown source name → `MISSING_SOURCE_PRIORITY` (last).
- Unknown strategy string → `ValueError` (caller bug; Pydantic
  `Literal` prevents this at startup).

CACHE INVARIANT: ranking is post-cache read. The cache key
(`JobSearchCacheKey(source, keywords, location, limit)` at
`application/ports.py:62-78`) is unchanged. Flipping
`AGGREGATOR_RANKING_STRATEGY` does NOT invalidate the cache; the
cache hit rate is unchanged.

DEPENDENCY RULE: this module lives in `application/` and only
imports `domain.job` + `application.aggregator` + stdlib. It does
NOT import `infrastructure` or `presentation`. The dependency
rule is pinned by the AST-walk test at the bottom of
`tests/unit/test_aggregator_ranking.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    # Imported only for the type annotations; the runtime code
    # only needs the structural shape (`job.posted_at`, `sources`,
    # `job.id`). A direct runtime import would create a circular
    # dependency: `aggregator.py` imports this module to call
    # `rank_jobs`, and this module would import `AggregatedJob`
    # back from `aggregator.py`. `TYPE_CHECKING` keeps the cycle
    # out of the runtime import graph while preserving the
    # static type for `mypy --strict`.
    from jobs_finder.application.aggregator import AggregatedJob

# Closed set of strategies. `Literal` enforces the set at
# construction (Pydantic uses the same `Literal` on
# `Settings.aggregator_ranking_strategy` so unknown values are
# rejected at startup). Exposed as a module alias so callers
# (including the `Settings` field) can refer to it without
# re-declaring the literal.
RankingStrategy = Literal["posted_at", "priority", "none"]

# Default source-priority map. LinkedIn first (priority 0), then
# Indeed (1), then InfoJobs (2). Matches the existing
# `SOURCE_PRIORITY` tuple in `application/aggregator.py:59` so
# the tie-breaker behavior is consistent with the dedup
# first-occurrence-wins logic.
DEFAULT_PRIORITY_MAP: dict[str, int] = {
    "linkedin": 0,
    "indeed": 1,
    "infojobs": 2,
}

# Priority for a source not in the map. `999` is unambiguously
# "unranked" — larger than any realistic source count, so
# unknown sources sort consistently to the bottom. `0` would
# silently elevate unknown sources to the top; `1` would mix
# with the known sources.
MISSING_SOURCE_PRIORITY = 999


def _source_priority(sources: list[str], priority_map: dict[str, int]) -> int:
    """Return the HIGHEST-priority source value for an `AggregatedJob`.

    The dedup contract pins the `sources` list to source-priority
    order (LinkedIn > Indeed > InfoJobs), so the FIRST entry is
    the highest-priority source by construction. The function
    uses `min(priority_map[s] for s in sources)` to be robust
    against future refactors that change the `sources` ordering
    invariant — e.g. if a deployment customizes the priority
    map, the tie-breaker still uses the source the deployment
    considers highest-priority.

    Unknown source names get `MISSING_SOURCE_PRIORITY` (largest
    sentinel), so they sort consistently to the bottom.
    """
    return min(
        (priority_map.get(s, MISSING_SOURCE_PRIORITY) for s in sources),
        default=MISSING_SOURCE_PRIORITY,
    )


def rank_jobs(
    jobs: list[AggregatedJob],
    strategy: RankingStrategy,
    priority_map: dict[str, int] = DEFAULT_PRIORITY_MAP,
) -> list[AggregatedJob]:
    """Return a new list of `AggregatedJob` ordered per `strategy`.

    The input list is NOT mutated. The function dispatches on
    `strategy`:

    - `"none"`: return `list(jobs)` (new list, input order).
    - `"posted_at"`: sort by `posted_at` DESC, tie-broken by
      source-priority ASC, then `job.id` ASC. `None` `posted_at`
      sinks to the bottom (REQ-AR-007).
    - `"priority"`: sort by source-priority ASC, tie-broken by
      `posted_at` DESC, then `job.id` ASC. Ignores freshness.

    `sorted` is stable; equal keys preserve input order. The
    function raises `ValueError` for an unknown `strategy` —
    Pydantic's `Literal` on `Settings.aggregator_ranking_strategy`
    prevents this at startup, so the `ValueError` is a defensive
    backstop for direct callers that bypass `Settings`.
    """
    if strategy == "none":
        # Escape hatch: return a NEW list in input order.
        return list(jobs)

    if strategy == "posted_at":
        # Primary: None sinks to the bottom (False=0 < True=1).
        # Secondary: negate the timestamp for DESC (tuple ordering
        # is ASC, so larger datetime first means smaller
        # negation first).
        # Tertiary: source-priority ASC.
        # Final: `job.id` ASC (string sort, deterministic).
        return sorted(
            jobs,
            key=lambda agg: (
                agg.job.posted_at is None,
                -(agg.job.posted_at.timestamp()) if agg.job.posted_at is not None else 0,
                _source_priority(agg.sources, priority_map),
                agg.job.id,
            ),
        )

    if strategy == "priority":
        # Primary: source-priority ASC.
        # Secondary: `posted_at` DESC (None sinks to the bottom).
        # Tertiary: `job.id` ASC.
        return sorted(
            jobs,
            key=lambda agg: (
                _source_priority(agg.sources, priority_map),
                agg.job.posted_at is None,
                -(agg.job.posted_at.timestamp()) if agg.job.posted_at is not None else 0,
                agg.job.id,
            ),
        )

    raise ValueError(f"Unknown ranking strategy: {strategy!r}")
