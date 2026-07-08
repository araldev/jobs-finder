"""Unit tests for `cv._link_matcher` — the post-processor that
substitutes LLM-invented URLs with the real URLs extracted from the
PDF's hyperlink annotations (per design §1.3-§1.7 of `cv-link-preservation`).

The matcher has 3 public functions:
- `normalize_label(s)` — lowercases, strips common suffixes/prefixes,
  collapses whitespace.
- `build_url_map(hyperlinks)` — maps `normalize_label(label) -> url`.
- `find_url_for_label(label, url_map)` — 4-strategy cascade:
  (1) exact normalized match, (2) substring either way,
  (3) token Jaccard > 0.5, (4) returns None.

All tests are TDD-first — each one fails on `ModuleNotFoundError`
until `_link_matcher.py` is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobs_finder.infrastructure.cv._link_matcher import (
    build_url_map,
    find_url_for_label,
    normalize_label,
)


# Local stub structurally identical to the real `HyperlinkEntry`
# (lives in `cv._parser`, Phase 2). Used so Phase 1 (matcher) tests
# are self-contained and don't pull in PDF-parsing imports.
@dataclass
class _HyperlinkStub:
    label: str
    url: str
    page: int = 1


# ── normalize_label ──────────────────────────────────────────────


class TestNormalizeLabel:
    """Pure-string normalization for label comparison."""

    def test_lowercases(self) -> None:
        assert normalize_label("Github") == "github"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert normalize_label("  github  ") == "github"

    def test_collapses_internal_whitespace(self) -> None:
        # Use a label WITHOUT a known suffix so the collapse is exercised
        # rather than masked by suffix-strip. "github link" would also
        # collapse, but then the suffix-strip would remove " link" and
        # the assertion would fail for the wrong reason.
        assert normalize_label("my    portfolio") == "my portfolio"

    def test_strips_link_suffix(self) -> None:
        assert normalize_label("Github link") == "github"

    def test_strips_enlace_suffix(self) -> None:
        assert normalize_label("Ver enlace") == "ver"

    def test_strips_url_suffix(self) -> None:
        assert normalize_label("My URL") == "my"

    def test_strips_href_suffix(self) -> None:
        assert normalize_label("Demo href") == "demo"

    def test_strips_aqui_suffix(self) -> None:
        assert normalize_label("Click aqui") == "click"

    def test_strips_here_suffix(self) -> None:
        assert normalize_label("Read here") == "read"

    def test_strips_ver_suffix(self) -> None:
        assert normalize_label("Ver repo") == "repo"

    def test_strips_go_to_prefix(self) -> None:
        assert normalize_label("go to repo") == "repo"

    def test_strips_visit_prefix(self) -> None:
        assert normalize_label("Visit my portfolio") == "my portfolio"

    def test_strips_open_prefix(self) -> None:
        assert normalize_label("open the app") == "the app"

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_label("") == ""

    def test_combined_lower_strip_suffix_and_collapse(self) -> None:
        # The user's most common case: "GitHub Link" → "github".
        assert normalize_label("  GitHub   Link  ") == "github"


# ── build_url_map ────────────────────────────────────────────────


class TestBuildUrlMap:
    """Maps `normalize_label(label) -> url`. Last-write-wins on
    duplicate normalized labels (per design §1.1)."""

    def test_empty_input_returns_empty(self) -> None:
        assert build_url_map([]) == {}

    def test_single_entry(self) -> None:
        hyperlinks = [_HyperlinkStub(label="Github link", url="https://github.com/u/v", page=1)]
        assert build_url_map(hyperlinks) == {"github": "https://github.com/u/v"}

    def test_multiple_entries_normalized(self) -> None:
        hyperlinks = [
            _HyperlinkStub(label="GitHub", url="https://github.com/u/v", page=1),
            _HyperlinkStub(label="Storybook", url="https://sb.com/u/v", page=1),
            _HyperlinkStub(label="npm", url="https://npmjs.com/u/v", page=1),
        ]
        url_map = build_url_map(hyperlinks)
        assert url_map == {
            "github": "https://github.com/u/v",
            "storybook": "https://sb.com/u/v",
            "npm": "https://npmjs.com/u/v",
        }

    def test_duplicate_normalized_labels_last_wins(self) -> None:
        hyperlinks = [
            _HyperlinkStub(label="github", url="https://first.com", page=1),
            _HyperlinkStub(label="Github Link", url="https://second.com", page=2),
        ]
        assert build_url_map(hyperlinks)["github"] == "https://second.com"


# ── find_url_for_label ───────────────────────────────────────────


class TestFindUrlForLabel:
    """4-strategy cascade: exact → substring either way → Jaccard > 0.5."""

    def test_empty_label_returns_none(self) -> None:
        assert find_url_for_label("", {"github": "https://github.com"}) is None

    def test_empty_map_returns_none(self) -> None:
        assert find_url_for_label("github", {}) is None

    def test_strategy_1_exact_normalized_match(self) -> None:
        # LLM emits "GitHub" (capital H), PDF has "github" (all lower).
        # After normalization both are "github" → exact match.
        url_map = {"github": "https://github.com/u/v"}
        assert find_url_for_label("GitHub", url_map) == "https://github.com/u/v"

    def test_strategy_2_substring_llm_label_in_pdf_label(self) -> None:
        # LLM emits "github", PDF has "Github link".
        # After normalization: LLM="github", PDF="github link".
        # "github" substring of "github link" → match.
        url_map = {"github link": "https://github.com/u/v"}
        assert find_url_for_label("github", url_map) == "https://github.com/u/v"

    def test_strategy_2_substring_pdf_label_in_llm_label(self) -> None:
        # LLM emits "GitHub Link" → "github link" (after normalize).
        # PDF has "github" → "github".
        # "github" substring of "github link" → match (same direction).
        url_map = {"github": "https://github.com/u/v"}
        assert find_url_for_label("GitHub Link", url_map) == "https://github.com/u/v"

    def test_strategy_3_token_jaccard_below_threshold_no_match(self) -> None:
        # LLM emits "github repo", PDF has "my github page".
        # Tokens: LLM={github, repo}, PDF={my, github, page}
        # Intersection = {github}, union = {github, repo, my, page} (4 tokens)
        # Jaccard = 1/4 = 0.25 — below 0.5 — should NOT match.
        url_map = {"my github page": "https://github.com/u/v"}
        assert find_url_for_label("github repo", url_map) is None

    def test_strategy_3_token_jaccard_matches_when_high_overlap(self) -> None:
        # LLM emits "github repo", PDF has "github repo extra".
        # Tokens: LLM={github, repo}, PDF={github, repo, extra}
        # Intersection = {github, repo}, union = {github, repo, extra} (3)
        # Jaccard = 2/3 = 0.667 — MATCHES (> 0.5).
        url_map = {"github repo extra": "https://github.com/u/v"}
        assert find_url_for_label("github repo", url_map) == "https://github.com/u/v"

    def test_no_match_returns_none(self) -> None:
        # LLM emits "custom internal", MAP has github/storybook/npm.
        url_map = {
            "github": "https://github.com/u/v",
            "storybook": "https://sb.com/u/v",
            "npm": "https://npmjs.com/u/v",
        }
        assert find_url_for_label("custom internal", url_map) is None

    def test_first_strategy_wins_over_others(self) -> None:
        # Exact match on "npm" should win even if other entries would
        # also match by substring.
        url_map = {
            "npm": "https://npmjs.com/u/v",  # exact match
            "npm link": "https://other.com",  # would also match by substring
        }
        assert find_url_for_label("npm", url_map) == "https://npmjs.com/u/v"
