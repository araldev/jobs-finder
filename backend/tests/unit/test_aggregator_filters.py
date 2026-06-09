"""Unit tests for the pure `filter_infojobs_results` and `tokenize` helpers.

Spec: REQ-FILTER-001 (scenarios 1-6) + REQ-TEST-001 (6 tests).

`filter_infojobs_results` discards `Job` instances whose `title`
has zero token overlap with the query (REQ-FILTER-001). The
function is a pure utility — no I/O, no side effects — that
the `SearchAllSourcesUseCase` applies to the InfoJobs slice of
the aggregated results AFTER the dedup step (the
post-cache, post-scrape filter, per design §1 #3).

The companion `tokenize` helper is the same algorithm used
inside `keyword_score` (REQ-FILTER-001 scenario 5) so the
filter and the scorer agree on what "token overlap" means.
The two implementations are co-located in
`infrastructure/aggregator_filters.py`; T-003's REFACTOR
step unifies the duplicated `_tokenize` in
`keyword_score.py` with the public `tokenize` here.

The 6 tests pin 4 base scenarios + 2 edge cases:

    1. `test_filter_discards_zero_token_title` — query={"react",
       "málaga"}, title="Recepcionista" → discarded.
    2. `test_filter_keeps_partial_token_match` — query={"react"},
       title="Desarrollador React" → kept.
    3. `test_filter_does_not_mutation_input` — input list is
       not the same object as the output (no in-place mutation).
    4. `test_filter_is_pure_same_input_same_output` — 100
       invocations return identical outputs.
    5. `test_tokenize_normalizes_whitespace_and_punct` —
       `"  React, TypeScript  "` → `{"react", "typescript"}`.
    6. `test_tokenize_unicode_preserves_accents` — `"Málaga"`
       → `{"málaga"}` (accent preserved via `casefold`).

This file is the RED → GREEN → REFACTOR anchor for T-003.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.aggregator_filters import (
    filter_infojobs_results,
    tokenize,
)


def _job(idx: int, title: str) -> Job:
    """Build a deterministic `Job` for tests.

    `posted_at` is tz-aware UTC to satisfy the `Job.__post_init__`
    invariant. `idx` is the unique `id` so the dedup key in
    downstream consumers doesn't collide.
    """
    return Job(
        id=f"j{idx}",
        title=title,
        company="Acme",
        location="Madrid",
        url=f"https://example.com/j{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Base scenarios (REQ-FILTER-001 scenarios 1-4)
# ---------------------------------------------------------------------------


def test_filter_discards_zero_token_title() -> None:
    """`query={"react", "málaga"}` + `title="Recepcionista"` → filtered out.

    Zero token overlap: `tokenize("Recepcionista") = {"recepcionista"}`
    ∩ `{"react", "málaga"}` = `set()`. The job is discarded.
    """
    jobs = [_job(1, title="Recepcionista")]
    result = filter_infojobs_results(jobs, query_tokens={"react", "málaga"})
    assert result == []


def test_filter_keeps_partial_token_match() -> None:
    """`query={"react"}` + `title="Desarrollador React"` → kept (1 token match).

    1 of 1 query token (`react`) is in the title's tokens
    `{"desarrollador", "react"}`. The job is kept.
    """
    jobs = [_job(1, title="Desarrollador React")]
    result = filter_infojobs_results(jobs, query_tokens={"react"})
    assert len(result) == 1
    assert result[0].title == "Desarrollador React"


def test_filter_does_not_mutation_input() -> None:
    """`filter_infojobs_results` returns a NEW list, not the input.

    Pure-function contract: the input list is not mutated in
    place, and the output is a distinct list object. A
    regression that mutates the input (e.g. `jobs[:] = ...`)
    would surface here.
    """
    jobs = [_job(1, title="Recepcionista"), _job(2, title="Desarrollador React")]
    result = filter_infojobs_results(jobs, query_tokens={"react"})
    # The output is a new list (identity check).
    assert result is not jobs
    # The input is not mutated.
    assert len(jobs) == 2
    assert [j.title for j in jobs] == ["Recepcionista", "Desarrollador React"]


def test_filter_is_pure_same_input_same_output() -> None:
    """100 calls with the same input return identical outputs.

    Pure-function contract: the function is deterministic for
    a given input. No I/O, no randomness, no side effects.
    The test invokes the function 100 times and asserts all
    outputs are equal.
    """
    jobs = [_job(1, title="Desarrollador React"), _job(2, title="Recepcionista")]
    query = {"react"}
    first = filter_infojobs_results(jobs, query_tokens=query)
    for _ in range(100):
        again = filter_infojobs_results(jobs, query_tokens=query)
        assert [j.id for j in again] == [j.id for j in first]


# ---------------------------------------------------------------------------
# `tokenize` (REQ-FILTER-001 scenarios 5-6)
# ---------------------------------------------------------------------------


def test_tokenize_normalizes_whitespace_and_punct() -> None:
    """`"  React, TypeScript  "` → `{"react", "typescript"}`.

    Lowercased via `.casefold()`, split on whitespace +
    non-word + underscore, deduped via `set()`. The tokenize
    algorithm is the canonical "query token" format used by
    the filter and the scorer.
    """
    assert tokenize("  React, TypeScript  ") == {"react", "typescript"}


def test_tokenize_unicode_preserves_accents() -> None:
    """`"Málaga"` → `{"málaga"}` (accent preserved via `casefold`).

    `casefold()` is Unicode-aware: it lowercases `"Málaga"`
    (U+00E1) to `"málaga"` (U+00E1) without decomposing the
    accent (no `unicodedata.normalize("NFD", ...)` is
    applied). This is the same algorithm as the production
    resolver: accent-sensitive matching (a job titled
    `"Ingeniero Malaga"` does NOT match a query of
    `"Málaga"`).

    The contract is pinned by REQ-FILTER-001 scenario 6: a
    job with the same accent is kept; a job without the
    accent is discarded.
    """
    assert tokenize("Málaga") == {"málaga"}
    # And the cross-check: the filter with the same query
    # token keeps the accented title and discards the
    # unaccented one.
    jobs = [_job(1, title="Ingeniero Málaga"), _job(2, title="Ingeniero Malaga")]
    result = filter_infojobs_results(jobs, query_tokens={"málaga"})
    assert len(result) == 1
    assert result[0].title == "Ingeniero Málaga"
