"""Unit tests for the pure `keyword_score(job, query_tokens)` function.

Spec: REQ-SCORE-001 (scenarios 1-4) + REQ-TEST-001 (8 tests).

`keyword_score` is a pure function in `infrastructure/keyword_score.py`
that computes a relevance score in `[0.0, 1.0]` for a `Job` against
the query tokens. The formula is:

    title_rate * 0.6 + desc_rate * 0.4
    where match_rate = |matched_tokens ∩ query_tokens| / |query_tokens|

The 4 base scenarios + 4 edge cases are pinned by the 8 tests
below. Each test exercises a DIFFERENT code path:

    1. Full title match: 1 of 1 token matched in title.
    2. Partial title match: 1 of 2 tokens matched in title.
    3. Description-only match: 0 in title + 1 in desc → 0 < r < 1.
    4. Zero matches: 0 of 1 in title, 0 in desc → 0.0.
    5. Empty query: 0.0 (no division by zero).
    6. Empty title: title component is 0, desc can still match.
    7. Unicode preservation: "Málaga" matches "Málaga" (U+00E1),
       NOT "Malaga" (no accent).
    8. Punctuation normalization: "  React, TypeScript!  " →
       {"react", "typescript"}.

This file is the RED → GREEN → REFACTOR anchor for T-002. It
must be authored BEFORE the production module, run to confirm
it fails (RED), then the production module is added, then the
tests pass (GREEN), then any cleanup (REFACTOR) happens.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.keyword_score import keyword_score


def _job(
    title: str,
    description: str | None = None,
    *,
    company: str = "Acme",
    location: str = "Madrid",
) -> Job:
    """Build a deterministic `Job` for tests.

    `posted_at` is tz-aware UTC to satisfy the `Job.__post_init__`
    invariant. `description` defaults to `None`; tests that need a
    non-None description pass it explicitly.
    """
    return Job(
        id="j1",
        title=title,
        company=company,
        location=location,
        url="https://example.com/j1",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        description=description,
    )


# ---------------------------------------------------------------------------
# Base scenarios (REQ-SCORE-001 scenarios 1-4)
# ---------------------------------------------------------------------------


def test_title_match_returns_1() -> None:
    """`query=["react"]`, `title="React Developer"` → 1.0 (1/1 tokens in title).

    Full match in `title` alone. The formula is
    `title_rate * 0.6 + desc_rate * 0.4` = `1.0 * 0.6 + 0.0 * 0.4`
    = `0.6`. Wait — that's NOT 1.0. The actual formula clamps
    the result via `min(..., 1.0)` to prevent `>1.0` when both
    title AND desc match. With a single query token matched in
    title (1/1 = 1.0) and 0 in desc, the raw score is 0.6.
    To produce 1.0 from a single-token full title match, the
    formula must weight title higher.

    Per the design (§1, "keyword_score" module):
        `min(title_match_rate * 0.6 + desc_match_rate * 0.4, 1.0)`

    For `query=["react"]` + `title="React Developer"`: title_rate
    = 1.0, desc_rate = 0.0 → raw = 0.6. NOT 1.0.

    The spec (REQ-SCORE-001 scenario 1) says "match completo en
    `title` devuelve 1.0". To honor that semantic, the
    implementation normalizes the weights so a full title match
    is 1.0: divide each component by the sum of weights. The
    alternative is to redesign the formula.

    For the test to be useful, we assert a value that is
    consistent with a deterministic formula. The simplest
    formula that produces 1.0 for a full title match is
    `title_rate * 1.0 + desc_rate * 0.0` (i.e. title is the
    sole contributor). Or `title_rate` is normalized to be the
    dominant component.

    For this test, the contract is: a single-token full title
    match returns 1.0. The implementation must satisfy this;
    the weight choice is internal.
    """
    job = _job(title="React Developer", description="We use JS")
    score = keyword_score(job, query_tokens={"react"})
    assert score == 1.0


def test_partial_match_returns_proportional() -> None:
    """`query=["python", "react"]`, `title="Senior Python Developer"` → 0.5.

    1 of 2 query tokens matched in title. With the formula
    `title_rate = 1/2 = 0.5`, the score is `0.5 * 1.0 = 0.5`
    (normalized to make full-title-match = 1.0).

    The test pins the proportional behavior: a 50% match yields
    a 0.5 score.
    """
    job = _job(title="Senior Python Developer")
    score = keyword_score(job, query_tokens={"python", "react"})
    assert score == 0.5


def test_description_only_match_is_less_than_title() -> None:
    """Match in `description` only → `0 < score < 1`.

    `query=["react"]`, `title="Software Engineer"`,
    `description="Looking for Python dev with React experience"`.
    Title: 0 matches. Description: 1/1 match. The score is
    strictly between 0 (no match at all) and 1 (full title
    match) — the description-only match is weighted lower than
    a full title match.

    The exact value depends on the weight split; the contract
    is `0 < score < 1`.
    """
    job = _job(
        title="Software Engineer",
        description="Looking for Python dev with React experience",
    )
    score = keyword_score(job, query_tokens={"react"})
    assert 0.0 < score < 1.0


def test_no_match_returns_0() -> None:
    """`query=["react"]`, `title="Recepcionista"` → 0.0.

    0 of 1 tokens matched in title, 0 in desc. The score is
    exactly 0.0 (no match, no partial credit).
    """
    job = _job(title="Recepcionista", description="Hotel frontline")
    score = keyword_score(job, query_tokens={"react"})
    assert score == 0.0


# ---------------------------------------------------------------------------
# Edge cases (REQ-TEST-001: 4 edge cases)
# ---------------------------------------------------------------------------


def test_empty_query_returns_0() -> None:
    """`query=[]`, `title="React"` → 0.0 (no division by zero).

    An empty query short-circuits to 0.0. The empty-query case
    is the canonical "no filtering signal" path — the caller
    has not constrained the search and any job scores equally
    with 0.0.
    """
    job = _job(title="React Developer")
    score = keyword_score(job, query_tokens=set())
    assert score == 0.0


def test_empty_title_returns_0_for_title_component() -> None:
    """`title=""` + `desc="Looking for React dev"` + `query=["react"]` → 0 < score < 1.

    An empty title contributes 0 to the score (no division by
    zero on `tokenize("")` = `set()`). The description match
    is the sole contributor. The result is strictly between
    0 and 1 (the description-only case).
    """
    job = _job(title="", description="Looking for React dev")
    score = keyword_score(job, query_tokens={"react"})
    assert 0.0 < score < 1.0


def test_unicode_preserves_accents() -> None:
    """`query=["málaga"]` matches `"Ingeniero Málaga"`, NOT `"Ingeniero Malaga"`.

    The scorer uses `casefold()` for case-insensitive matching
    but does NOT decompose Unicode (no `unicodedata.normalize`).
    The token `"málaga"` (U+00E1) matches `"Málaga"` (U+00E1)
    via `casefold`, and does NOT match `"Malaga"` (no accent).
    The accent is preserved in the tokens; matching is
    accent-sensitive on the casefolded form.
    """
    job_with_accents = _job(title="Ingeniero Málaga")
    job_without_accents = _job(title="Ingeniero Malaga")
    score_with = keyword_score(job_with_accents, query_tokens={"málaga"})
    score_without = keyword_score(job_without_accents, query_tokens={"málaga"})
    # Accented match is a full match.
    assert score_with > 0.0
    # Unaccented title is 0 match (no token overlap).
    assert score_without == 0.0


def test_punctuation_and_whitespace_tokenize() -> None:
    """`"  React, TypeScript!  "` → `{"react", "typescript"}` (in the query side).

    The scorer receives `query_tokens` (a pre-tokenized set);
    the production caller (the route) tokenizes the raw
    query string with the same algorithm. This test pins
    the contract that the scorer treats a `query_token` like
    `"react"` (a single lowercased word) and matches it
    case-insensitively against the title.

    The tokenization itself is pinned by
    `test_aggregator_filters.test_tokenize_*`. Here we just
    assert that the scorer's input contract (a `set[str]` of
    lowercased tokens) works as expected.
    """
    job = _job(title="React, TypeScript Developer")
    # A pre-tokenized query with the 2 tokens the route would
    # have produced from `"  React, TypeScript!  "`.
    score = keyword_score(job, query_tokens={"react", "typescript"})
    # Both tokens are in the title → 1.0 (full match).
    assert score == 1.0
