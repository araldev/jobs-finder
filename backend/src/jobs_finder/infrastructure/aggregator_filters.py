"""Pure helpers for the aggregator's post-scrape InfoJobs filter.

Spec: REQ-FILTER-001 (the 6 scenarios in the spec).

This module contains two pure functions:
- `tokenize(text) -> set[str]`: the canonical query-token
  format. The algorithm is `.casefold()` (Unicode-aware
  lowercase) → split on whitespace + non-word + underscore →
  filter empty → set dedup. The accent is preserved (no
  `unicodedata.normalize`); `"Málaga"` tokenizes to
  `{"málaga"}`, NOT `{"málagu\u0301a"}` (NFD-decomposed).
- `filter_infojobs_results(jobs, query_tokens) -> list[Job]`:
  discard `Job` instances whose `title` has zero token
  overlap with `query_tokens`. A job is kept iff
  `len(tokenize(job.title) & query_tokens) > 0`. The
  function is pure: it returns a new list, does not mutate
  the input, has no I/O and no randomness.

The `SearchAllSourcesUseCase` calls
`filter_infojobs_results` on the InfoJobs slice of the
aggregated results AFTER the dedup step (post-cache,
post-scrape). LinkedIn and Indeed results are NOT filtered
(per REQ-FILTER-001 scenario 3, "el filtro aplica SOLO a
InfoJobs").

The same `tokenize` algorithm is used inside
`infrastructure.keyword_score.keyword_score`; T-003's
REFACTOR step unifies the duplicated implementations (the
scorer re-exports this `tokenize` as its private helper).
"""

from __future__ import annotations

import re

from jobs_finder.domain.job import Job

# Tokenization regex: split on whitespace + non-word + underscore.
# `re.compile` at module load (not inside the function) so the
# pattern is compiled once. `\W` is "non-word" (anything not in
# `[A-Za-z0-9_]`); the explicit `_` is redundant with `\W` but
# is kept for readability — the regex matches the test fixture
# `"node_js"` → `{"node", "js"}`.
_TOKENIZE_SPLIT_RE = re.compile(r"[\s\W_]+")


def tokenize(text: str) -> set[str]:
    """Lowercase + split on whitespace + punctuation + dedupe.

    The algorithm:
        1. `text.casefold()` (Unicode-aware lowercasing).
        2. `re.split(r'[\\s\\W_]+', text)` (whitespace +
           non-word + underscore).
        3. `set(...)` for dedup (also filters empty strings
           from leading/trailing matches).

    Preserves NFC (no `.normalize()`): `"Málaga"` stays
    `"Málaga"` (U+00E1), not `"Málaga"` (NFD-decomposed).
    The accent is preserved in the tokens; matching is
    accent-sensitive on the casefolded form.

    Args:
        text: The string to tokenize. May be empty or
            whitespace-only; returns `set()` in that case.

    Returns:
        The set of normalized tokens. An empty input
        returns an empty set.
    """
    if not text:
        return set()
    return {tok for tok in _TOKENIZE_SPLIT_RE.split(text.casefold()) if tok}


def filter_infojobs_results(jobs: list[Job], query_tokens: set[str]) -> list[Job]:
    """Discard `Job` instances whose `title` has zero token overlap with `query_tokens`.

    **Defense-in-depth safety net** (REQ-PROV-005). The
    PRIMARY narrowing of InfoJobs results happens at the
    URL level via the `provinceIds` + `countryIds` query
    params — see `InfoJobsScraper.search()` /
    `InfoJobsScraperSettings.location_resolver` and the
    "InfoJobs province/country resolution" section of the
    README. This function's role is the SECONDARY safety
    net: it catches zero-overlap jobs that slip through
    when the URL plumb returns the wrong region (unmapped
    locations, future province ID drift, transient InfoJobs
    SERP changes). The function is KEEP-alive (not removed,
    not no-op'd) because the cost of removing it is small
    (~5 lines + 6 tests) but the cost of needing it again
    (a re-deploy + a hotfix + a re-capture of the broken
    region) is higher. The 6 tests in
    `test_aggregator_filters.py` pin the keep-as-defense-
    in-depth contract.

    Pure function: no I/O, no mutation of the input,
    returns a new list. A job is kept iff
    `len(tokenize(job.title) & query_tokens) > 0`.

    Args:
        jobs: The list of `Job` instances to filter. NOT
            mutated by this function.
        query_tokens: The pre-tokenized set of query tokens
            (lowercased, punctuation-stripped, deduped). An
            empty set short-circuits to `list(jobs)` (the
            caller has no filtering signal — every job is
            kept, even the irrelevant ones, so the aggregator
            returns the full InfoJobs result set).

    Returns:
        A new `list[Job]` with the zero-overlap jobs removed.
    """
    if not query_tokens:
        return list(jobs)
    return [job for job in jobs if tokenize(job.title) & query_tokens]
