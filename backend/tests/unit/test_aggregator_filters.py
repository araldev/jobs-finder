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
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Docstring + README grep tests (REQ-PROV-005)
#
# These are NOT behavioral tests (they don't call the function
# with different inputs and assert different outputs). They are
# DOCUMENTATION tests: they assert that the docstring + README
# contain the canonical keywords the design pinned (REQ-PROV-005
# scenario 5: "README documents 'defense-in-depth' / 'safety net'
# role"). The grep assertions catch regressions where a future
# refactor removes the documentation hint without removing the
# code (or vice-versa).
# ---------------------------------------------------------------------------


def test_filter_infojobs_results_docstring_marks_defense_in_depth() -> None:
    """`filter_infojobs_results` docstring contains the phrase "defense-in-depth".

    REQ-PROV-005 pins the docstring MUST call itself a
    "defense-in-depth safety net" so future readers
    understand the function is intentionally kept alive
    (not removed, not no-op'd).     A regression that strips
    the phrase (e.g. a docstring rewrite during a
    refactor) is a silent spec drift; the test catches it.
    """
    docstring = filter_infojobs_results.__doc__ or ""
    assert "defense-in-depth" in docstring.lower()
    # The docstring also points readers to the README
    # section that explains the role in detail.
    assert "province" in docstring.lower()
    assert "countryIds" in docstring or "country" in docstring.lower()


def test_backend_readme_documents_infojobs_province_country_resolution() -> None:
    """`backend/README.md` contains a "InfoJobs province/country resolution" section
    that documents:
        - The 9-entry mapping table
        - The 4 speculative IDs (Madrid/Barcelona/Valencia/Sevilla)
        - The LIVE test gate (`LLM_LIVE_TESTS=1`)
        - The unmapped-location fallback (graceful degradation)
    """
    readme_path = Path(__file__).resolve().parent.parent.parent / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    # The new section exists with the canonical title.
    assert "InfoJobs province/country resolution" in readme_text
    # The 4 speculative IDs are documented.
    assert "SPECULATIVE" in readme_text or "speculative" in readme_text
    # The LIVE test gate env var is documented.
    assert "LLM_LIVE_TESTS" in readme_text
    # The unmapped-location fallback is documented.
    assert "unmapped" in readme_text.lower() or "graceful" in readme_text.lower()
    # The defense-in-depth role of the filter is documented.
    assert "defense-in-depth" in readme_text.lower() or "defense in depth" in readme_text.lower()


def test_backend_readme_documents_url_formula_with_province_country_ids() -> None:
    """`backend/README.md` documents the `provinceIds` + `countryIds` URL params.

    The URL formula is the user-facing contract: an
    operator reading the README should know that a query
    for `?location=Málaga` is narrowed to
    `&provinceIds=34&countryIds=17` in the URL the
    InfoJobs scraper visits. The grep assertion catches
    regressions where the docs lose the URL example.
    """
    readme_path = Path(__file__).resolve().parent.parent.parent / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    # The query params are spelled out (the canonical names).
    assert "provinceIds" in readme_text
    assert "countryIds" in readme_text
    # At least one example URL is shown.
    assert "provinceIds=34" in readme_text  # the canonical Málaga example
    assert "countryIds=17" in readme_text  # the canonical España example
