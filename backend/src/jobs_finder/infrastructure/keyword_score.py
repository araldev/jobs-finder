"""Pure `keyword_score(job, query_tokens)` function — opt-in relevance ranking.

Spec: REQ-SCORE-001 (scenarios 1-4 + 5-6 env var opt-in).

The scorer computes a relevance score in `[0.0, 1.0]` for a
`Job` against a pre-tokenized set of query tokens. The
production caller (the `GET /jobs` route) tokenizes the
`q` parameter via the `tokenize` helper and passes the
resulting `set[str]` to the aggregator; the aggregator then
calls `keyword_score(job, query_tokens)` for each `Job` when
`enable_keyword_scoring=True` (env var `ENABLE_KEYWORD_SCORING`,
default `False` — opt-in).

The function is a PURE function:
- No I/O (no Playwright, no network, no LLM).
- No mutation of the input `Job` or `query_tokens`.
- No randomness.
- Deterministic for a given input pair.

The formula is:

    title_rate = |tokenize(job.title) ∩ query_tokens| / |query_tokens|
    desc_rate  = |tokenize(job.description or "") ∩ query_tokens| / |query_tokens|
    score      = max(title_rate, min(desc_rate, 0.3))

The `max(title_rate, ...)` ensures a full title match is
exactly `1.0` (the canonical "this job is on-topic" signal).
The `min(desc_rate, 0.3)` caps the description's contribution
at `0.3` so a description-only match is strictly less than a
title match (REQ-SCORE-001 scenario 3). The formula satisfies
all 4 spec scenarios:
- `title_match_returns_1`: title_rate=1.0 → score=1.0.
- `partial_match_returns_proportional`: title_rate=0.5 → score=0.5.
- `description_only_match_is_less_than_title`: title_rate=0,
  desc_rate=0.5 → score=min(0.5, 0.3)=0.3 (strictly between 0
  and 1).
- `no_match_returns_0`: title_rate=0, desc_rate=0 → score=0.0.

The empty-query edge case short-circuits to `0.0` BEFORE the
division (no `ZeroDivisionError`).

Unicode handling: `tokenize` uses `.casefold()` for
case-insensitive matching and preserves accents (no
`unicodedata.normalize` — the same algorithm as
`aggregator_filters.tokenize`). The query side does the
tokenization; the scorer is agnostic to the raw query
string.

`tokenize` is inlined here (a copy of the canonical
implementation in `infrastructure.aggregator_filters`) so
T-002 can land independently. T-003's REFACTOR step will
unify the two implementations (the function is a private
helper of this module, NOT a public export).
"""

from __future__ import annotations

import re

from jobs_finder.domain.job import Job

# The description weight cap (0.3) is intentionally below the
# title's contribution (1.0) so a description-only match can
# never reach a full title match's score. The constant is
# hoisted to module scope so the formula is self-documenting.
_DESC_WEIGHT_CAP: float = 0.3

# Tokenization regex: split on whitespace + non-word + underscore.
# Matches the algorithm in `infrastructure.aggregator_filters.py`
# (T-003 will deduplicate the two implementations; the inlined
# version is intentional for T-002 to keep the tasks independent).
_TOKENIZE_SPLIT_RE = re.compile(r"[\s\W_]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase + split on whitespace + punctuation + dedupe.

    Mirrors `infrastructure.aggregator_filters.tokenize` —
    duplicated here so T-002 lands independently of T-003.
    T-003's REFACTOR will unify the two implementations.
    """
    if not text:
        return set()
    return {tok for tok in _TOKENIZE_SPLIT_RE.split(text.casefold()) if tok}


def keyword_score(job: Job, query_tokens: set[str]) -> float:
    """Return a relevance score in `[0.0, 1.0]` for `job` against `query_tokens`.

    Args:
        job: The `Job` value object to score. The function reads
            `job.title` and `job.description` (the latter is
            `Optional[str]` per the `Job` schema).
        query_tokens: The pre-tokenized set of query tokens
            (lowercased, punctuation-stripped, deduped). An
            empty set short-circuits to `0.0` (the canonical
            "no query" sentinel — the aggregator's filter
            short-circuits on this case too).

    Returns:
        A float in `[0.0, 1.0]`. The formula is
        `max(title_rate, min(desc_rate, 0.3))` where
        `title_rate` and `desc_rate` are the fraction of
        query tokens matched in the job's title and
        description respectively. See the module docstring
        for the full rationale.
    """
    if not query_tokens:
        return 0.0
    title_tokens = _tokenize(job.title)
    desc_tokens = _tokenize(job.description or "")
    title_rate = len(title_tokens & query_tokens) / len(query_tokens)
    desc_rate = len(desc_tokens & query_tokens) / len(query_tokens)
    return max(title_rate, min(desc_rate, _DESC_WEIGHT_CAP))
