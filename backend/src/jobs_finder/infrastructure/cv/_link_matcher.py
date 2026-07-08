"""Pure-string URL matching helpers for the CV link-preservation pipeline.

The matcher pairs `ProjectLink.label` (emitted by the LLM) with the
real URL extracted from the PDF's hyperlink annotations via a
4-strategy cascade:

  1. Exact normalized match (case-insensitive, suffix/prefix-stripped,
     whitespace-collapsed).
  2. Substring in either direction (LLM label in PDF label OR
     PDF label in LLM label).
  3. Token Jaccard overlap > 0.5 (handles paraphrased labels like
     "my github page" vs "github repo").
  4. No match → return None (caller keeps the LLM's URL).

Per design §1.6-§1.7 of `cv-link-preservation`. The functions are
pure (no I/O, no globals) so they're trivially testable in
`tests/unit/test_link_matcher.py` without any PDF/LLM fixtures.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Common suffixes that appear at the end of PDF link labels
# (e.g. "Github link", "Ver enlace"). Stripped before comparison.
_LABEL_SUFFIXES: tuple[str, ...] = (
    " link",
    " enlace",
    " url",
    " href",
    " aqui",
    " here",
    " ver",
)

# Common prefixes that appear at the start of PDF link labels
# (e.g. "go to repo", "visit my portfolio"). Stripped before comparison.
_LABEL_PREFIXES: tuple[str, ...] = (
    "go to ",
    "visit ",
    "see ",
    "ver ",
    "abre ",
    "open ",
)

# Token Jaccard threshold above which we accept a fuzzy match.
# 0.5 = "at least half the tokens must overlap" — empirically tuned
# to handle paraphrased labels like "my github page" vs "github repo"
# without leaking false positives for unrelated labels.
_JACCARD_THRESHOLD: float = 0.5


def normalize_label(s: str) -> str:
    """Normalize a label for fuzzy comparison.

    Steps:
      1. Lowercase.
      2. Strip leading/trailing whitespace.
      3. Strip common suffixes (`link`, `enlace`, `url`, `href`,
         `aqui`, `here`, `ver`) when they appear at the end.
      4. Strip common prefixes (`go to`, `visit`, `see`, `ver`,
         `abre`, `open`) when they appear at the start.
      5. Collapse internal whitespace to single spaces.

    Examples:
        >>> normalize_label("Github Link")
        'github'
        >>> normalize_label("  Ver   mi repo  ")
        'mi repo'
        >>> normalize_label("")
        ''
    """
    if not s:
        return ""
    normalized = s.lower().strip()
    for suffix in _LABEL_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip()
    for prefix in _LABEL_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].lstrip()
    return " ".join(normalized.split())


def build_url_map(hyperlinks: Iterable[Any]) -> dict[str, str]:
    """Build a `{normalized_label: url}` map from PDF hyperlinks.

    Accepts any iterable of objects with `.label` and `.url` attributes
    (the real `HyperlinkEntry` in `cv._parser` satisfies this; tests
    can pass duck-typed stubs). Last-write-wins on duplicate
    normalized labels (per design §1.1). Empty input returns an
    empty dict.
    """
    url_map: dict[str, str] = {}
    for hyperlink in hyperlinks:
        label = getattr(hyperlink, "label", "")
        url = getattr(hyperlink, "url", "")
        key = normalize_label(label)
        if not key:
            # Skip icon-only hyperlinks (no extractable label).
            continue
        url_map[key] = url
    return url_map


def find_url_for_label(label: str, url_map: dict[str, str]) -> str | None:
    """Find the URL in `url_map` whose PDF label matches `label`.

    4-strategy cascade (first hit wins):
      1. Exact normalized match.
      2. Substring either way (`norm_label in pdf_label` OR
         `pdf_label in norm_label`).
      3. Token Jaccard overlap > 0.5.
      4. No match → return None (caller keeps the LLM's URL).

    Returns None when `label` is empty or `url_map` is empty.
    """
    if not label or not url_map:
        return None

    normalized = normalize_label(label)

    # Strategy 1: exact normalized match.
    if normalized in url_map:
        return url_map[normalized]

    # Strategy 2: substring in either direction.
    for pdf_label, url in url_map.items():
        if not pdf_label:
            continue
        if normalized in pdf_label or pdf_label in normalized:
            return url

    # Strategy 3: token Jaccard overlap.
    norm_tokens = set(normalized.split())
    if not norm_tokens:
        return None
    best_url: str | None = None
    best_score: float = _JACCARD_THRESHOLD
    for pdf_label, url in url_map.items():
        pdf_tokens = set(pdf_label.split())
        if not pdf_tokens:
            continue
        intersection = len(norm_tokens & pdf_tokens)
        union = len(norm_tokens | pdf_tokens)
        if union == 0:
            continue
        score = intersection / union
        if score > best_score:
            best_url = url
            best_score = score
    return best_url
