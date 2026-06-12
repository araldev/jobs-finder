"""Unit tests for `rank_jobs` — the pure ranking function.

Spec: REQ-AR-002, REQ-AR-003, REQ-AR-004, REQ-AR-006, REQ-AR-007
(jobs-aggregator-ranking).

The function is a leaf in the application layer
(`application/ranking.py`): it takes a `list[AggregatedJob]` and
returns a new `list[AggregatedJob]` ordered per the given
`strategy` and `priority_map`. It does NOT mutate the input
list, the `AggregatedJob.sources` lists, or the underlying
`Job.posted_at` timestamps. It is dependency-free (only stdlib
+ `domain.job` + `application.aggregator` types) so it can be
tested in pure isolation.

The 7 tests pin the contract:

1. Empty input returns `[]` (the function must not crash on `[]`).
2. `strategy="none"` preserves input order (the escape hatch).
3. `strategy="posted_at"` orders by `posted_at` DESC.
4. `strategy="posted_at"` with `posted_at=None` sinks to the bottom
   (defensive — current scrapers never return `None`, but the
   branch future-proofs against refactors; REQ-AR-007).
5. `strategy="priority"` orders by `priority_map` ASC, ignoring
   `posted_at`.
6. Tie-breaker chain: equal `posted_at` breaks by `priority_map`
   ASC, then by `job.id` ASC. REQ-AR-002 scenarios 3 + 4.
7. Ranking does NOT mutate the `sources` list on each
   `AggregatedJob` (REQ-AR-006).

These tests are the RED step of T-001 Cycle 2 (Strict TDD). They
MUST be authored BEFORE `application/ranking.py` is created. The
run on a clean tree must FAIL for the right reason
(`ModuleNotFoundError: No module named 'jobs_finder.application.ranking'`),
and the GREEN step then creates the module.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jobs_finder.application.aggregator import AggregatedJob
from jobs_finder.application.ranking import (
    DEFAULT_PRIORITY_MAP,
    MISSING_SOURCE_PRIORITY,
    RankingStrategy,
    rank_jobs,
)
from jobs_finder.domain.job import Job


def _job(
    idx: int,
    *,
    posted_at: datetime | None = None,
    title: str = "Title",
    company: str = "Co",
    location: str = "Madrid",
) -> Job:
    """Build a deterministic `Job` for tests.

    Default `posted_at` is `2026-06-01 + idx days` (tz-aware UTC) so
    distinct jobs have distinct freshness. Pass `posted_at=None` to
    build a `Job` with no freshness for the defensive None-branch
    test (bypasses the production invariant — current scrapers
    always fill a real datetime).
    """
    return Job(
        id=f"j{idx}",
        title=title,
        company=company,
        location=location,
        url=f"https://example.com/j{idx}",
        posted_at=posted_at if posted_at is not None else datetime(2026, 6, idx, tzinfo=UTC),
        source="linkedin",
    )


def _agg(job: Job, sources: list[str]) -> AggregatedJob:
    """Wrap a `Job` in an `AggregatedJob` with the given `sources` list."""
    return AggregatedJob(job=job, sources=list(sources))


# ---------------------------------------------------------------------------
# Module surface (pinned for future-proofing)
# ---------------------------------------------------------------------------


def test_default_priority_map_is_linkedin_first() -> None:
    """`DEFAULT_PRIORITY_MAP` is LinkedIn-first (REQ-AR-004)."""
    assert DEFAULT_PRIORITY_MAP == {"linkedin": 0, "indeed": 1, "infojobs": 2}


def test_missing_source_priority_is_unambiguously_last() -> None:
    """`MISSING_SOURCE_PRIORITY` is a large positive int (REQ-AR-004).

    The design pinned `999` so unknown sources sort consistently to
    the bottom — neither silently first (0) nor silently last
    among known sources (which would mix with `infojobs=2`).
    """
    assert MISSING_SOURCE_PRIORITY == 999
    assert max(DEFAULT_PRIORITY_MAP.values()) < MISSING_SOURCE_PRIORITY


def test_ranking_strategy_literal_is_closed_set() -> None:
    """`RankingStrategy` is a closed `Literal` of 3 strategies (REQ-AR-003)."""
    # The literal annotation is preserved at runtime via
    # `__annotations__`; the test pins that the 3 values are
    # present and the type alias is a `Literal` form.
    args = typing.get_args(RankingStrategy)
    assert set(args) == {"posted_at", "priority", "none"}


# ---------------------------------------------------------------------------
# 1. Empty input
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    """`rank_jobs([])` returns `[]` (REQ-AR-002 scenario "empty")."""
    assert rank_jobs([], strategy="posted_at") == []


# ---------------------------------------------------------------------------
# 2. `strategy="none"` preserves input order
# ---------------------------------------------------------------------------


def test_strategy_none_preserves_input_order() -> None:
    """`strategy="none"` returns a new list in input order (REQ-AR-003 escape hatch)."""
    a = _agg(_job(1), ["linkedin"])
    b = _agg(_job(2), ["indeed"])
    c = _agg(_job(3), ["infojobs"])
    result = rank_jobs([a, b, c], strategy="none")
    assert [agg.job.id for agg in result] == ["j1", "j2", "j3"]


def test_strategy_none_returns_a_new_list_not_the_input() -> None:
    """`strategy="none"` returns a NEW list (input not mutated)."""
    a = _agg(_job(1), ["linkedin"])
    b = _agg(_job(2), ["indeed"])
    input_list = [a, b]
    result = rank_jobs(input_list, strategy="none")
    assert result is not input_list


# ---------------------------------------------------------------------------
# 3. `strategy="posted_at"` orders DESC
# ---------------------------------------------------------------------------


def test_strategy_posted_at_desc_orders_by_posted_at() -> None:
    """`strategy="posted_at"` orders by `posted_at` DESC (REQ-AR-002 scenario 1).

    3 jobs with distinct `posted_at` (June 1, 3, 2) sort to
    `[June 3, June 2, June 1]`.
    """
    a = _agg(_job(1, posted_at=datetime(2026, 6, 1, tzinfo=UTC)), ["linkedin"])
    b = _agg(_job(2, posted_at=datetime(2026, 6, 3, tzinfo=UTC)), ["linkedin"])
    c = _agg(_job(3, posted_at=datetime(2026, 6, 2, tzinfo=UTC)), ["linkedin"])
    result = rank_jobs([a, c, b], strategy="posted_at")
    assert [agg.job.posted_at for agg in result] == [
        datetime(2026, 6, 3, tzinfo=UTC),
        datetime(2026, 6, 2, tzinfo=UTC),
        datetime(2026, 6, 1, tzinfo=UTC),
    ]


# ---------------------------------------------------------------------------
# 4. `posted_at=None` defensive branch
# ---------------------------------------------------------------------------


def test_strategy_posted_at_none_fallback_to_bottom() -> None:
    """`posted_at=None` jobs sink to the bottom of `strategy="posted_at"` (REQ-AR-007)."""
    # Build a Job with `posted_at=None` by bypassing the `__post_init__`
    # invariant. The production path never produces this; the
    # defensive branch covers a future refactor that might.
    none_job: Job = object.__new__(Job)  # bypass `__init__` + `__post_init__`
    for attr, value in (
        ("id", "j-none"),
        ("title", "No Date"),
        ("company", "X"),
        ("location", "Y"),
        ("url", "https://example.com/none"),
        ("posted_at", None),
    ):
        object.__setattr__(none_job, attr, value)

    with_date = _agg(_job(1, posted_at=datetime(2026, 6, 5, tzinfo=UTC)), ["linkedin"])
    with_none = _agg(none_job, ["linkedin"])

    result = rank_jobs([with_none, with_date], strategy="posted_at")
    assert result[0].job.id == "j1"  # the dated one first
    assert result[1].job.id == "j-none"  # the None one last


# ---------------------------------------------------------------------------
# 5. `strategy="priority"` ignores `posted_at`
# ---------------------------------------------------------------------------


def test_strategy_priority_orders_by_priority_map() -> None:
    """`strategy="priority"` orders by `priority_map` ASC, ignoring `posted_at` (REQ-AR-003).

    3 jobs from 3 sources with DISTINCT `posted_at` (deliberately
    inverted vs source-priority order) sort to
    `[linkedin, indeed, infojobs]` — the source-priority order,
    NOT the freshness order. Pin that the strategy ignores time.
    """
    a = _agg(_job(1, posted_at=datetime(2026, 6, 1, tzinfo=UTC)), ["infojobs"])
    b = _agg(_job(2, posted_at=datetime(2026, 6, 5, tzinfo=UTC)), ["linkedin"])
    c = _agg(_job(3, posted_at=datetime(2026, 6, 3, tzinfo=UTC)), ["indeed"])
    result = rank_jobs([a, c, b], strategy="priority")
    assert [agg.sources[0] for agg in result] == ["linkedin", "indeed", "infojobs"]


# ---------------------------------------------------------------------------
# 6. Tie-breaker chain
# ---------------------------------------------------------------------------


def test_tie_breaker_priority_then_id_when_posted_at_equal() -> None:
    """Equal `posted_at` breaks by `priority_map` ASC, then `id` ASC (REQ-AR-002).

    3 jobs (LinkedIn, Indeed, InfoJobs) with the SAME `posted_at`
    sort to source-priority order. Then 2 Indeed jobs with the
    SAME `posted_at` sort by `id` ASC.
    """
    same = datetime(2026, 6, 5, tzinfo=UTC)
    linkedin = _agg(_job(1, posted_at=same), ["linkedin"])
    indeed_b = _agg(_job(2, posted_at=same, title="Indeed B"), ["indeed"])
    indeed_a = _agg(_job(3, posted_at=same, title="Indeed A"), ["indeed"])
    infojobs = _agg(_job(4, posted_at=same), ["infojobs"])

    result = rank_jobs([infojobs, indeed_b, linkedin, indeed_a], strategy="posted_at")
    assert [agg.sources[0] for agg in result] == [
        "linkedin",
        "indeed",
        "indeed",
        "infojobs",
    ]
    # Within the 2 Indeed jobs (same source, same posted_at), `id`
    # ASC: j2 < j3, so the Indeed A job (id=j3) is THIRD, the
    # Indeed B job (id=j2) is SECOND.
    assert result[1].job.id == "j2"  # Indeed B
    assert result[2].job.id == "j3"  # Indeed A


def test_deduped_job_uses_highest_priority_source() -> None:
    """A job with `sources=["indeed", "linkedin"]` sorts by LinkedIn's priority (REQ-AR-004).

    The `sources` list accumulates in source-priority order per the
    dedup contract, but the tie-breaker must use the highest-
    priority source (the `min(priority_map[s] for s in sources)`),
    not the first or last. This pins the dedup interaction.
    """
    same = datetime(2026, 6, 5, tzinfo=UTC)
    # Job from Indeed (priority 1) + LinkedIn (priority 0) — its
    # sort key is LinkedIn's priority (0).
    deduped = _agg(_job(1, posted_at=same, title="Same"), ["indeed", "linkedin"])
    # Pure InfoJobs job (priority 2) — sorted LATER.
    infojobs = _agg(_job(2, posted_at=same, title="InfoJobs"), ["infojobs"])

    result = rank_jobs([infojobs, deduped], strategy="posted_at")
    assert result[0].job.id == "j1"  # LinkedIn-priority first
    assert result[1].job.id == "j2"  # InfoJobs last


# ---------------------------------------------------------------------------
# 7. `sources` list preservation
# ---------------------------------------------------------------------------


def test_preserves_aggregated_job_sources_list_through_ranking() -> None:
    """Ranking does NOT mutate `sources` on each `AggregatedJob` (REQ-AR-006).

    The outer list is reordered; the `sources` list on each
    `AggregatedJob` is byte-identical before and after.
    """
    a = _agg(_job(1), ["linkedin", "indeed"])
    b = _agg(_job(2), ["indeed"])
    c = _agg(_job(3), ["infojobs"])
    input_a_sources = list(a.sources)

    rank_jobs([c, a, b], strategy="posted_at")

    # `a.sources` is unchanged.
    assert a.sources == input_a_sources
    assert a.sources == ["linkedin", "indeed"]


def test_missing_source_in_priority_map_gets_missing_priority() -> None:
    """An unknown source gets `MISSING_SOURCE_PRIORITY` (REQ-AR-004).

    A custom `priority_map` that omits `infojobs` must give
    `infojobs` jobs the `MISSING_SOURCE_PRIORITY` value, so they
    sort to the bottom — the safe default for unknown sources.
    """
    custom_map = {"linkedin": 0, "indeed": 1}  # no `infojobs`
    same = datetime(2026, 6, 5, tzinfo=UTC)
    infojobs = _agg(_job(1, posted_at=same, title="InfoJobs"), ["infojobs"])
    indeed = _agg(_job(2, posted_at=same, title="Indeed"), ["indeed"])

    result = rank_jobs([infojobs, indeed], strategy="posted_at", priority_map=custom_map)
    # `indeed` is in the map (priority 1); `infojobs` is missing
    # (priority 999). Even with same `posted_at`, the missing
    # source sorts last.
    assert result[0].job.id == "j2"  # indeed
    assert result[1].job.id == "j1"  # infojobs (missing → 999)


# Silence unused-import linter for the dataclass import — kept
# available for future test additions.
_ = (dataclass, Any)
