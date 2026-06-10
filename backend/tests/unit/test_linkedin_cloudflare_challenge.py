"""Tests for `is_cloudflare_challenge(soup)` pure function (T-003 of
`backend-linkedin-stealth`).

Spec coverage (REQ-LST-CF-001..003):
- REQ-LST-CF-001: `is_cloudflare_challenge` is a pure function in
  `infrastructure/linkedin/parsers.py` next to v1 `is_auth_wall`.
  Pure: no I/O, no `await`, no logging side-effects, no mutation.
- REQ-LST-CF-002: the detector returns `True` ONLY when the page
  contains the Cloudflare 2026 signature (3-OR: title "Just a
  moment..." AND `<noscript>` AND `div.cf-mitigated` /
  `[data-cf-challenge]`).
- REQ-LST-CF-003: cards-win rule — when ≥1 `div[data-entity-urn]`
  is present (a healthy SERP with cards), the detector returns
  `False` (suppresses false positives on LinkedIn A/B tests that
  reuse the "Just a moment..." string in rate-limit banners).

The fixture `CLOUDFLARE_CHALLENGE_HTML` (in
`tests/fixtures/linkedin_search.py`) pins the 2026-06-10 capture
of the Cloudflare challenge page; the spec captures the 3
markers and 0 cards. When Cloudflare changes the markup, a
single fixture update + a single detector update are the only
changes needed.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from jobs_finder.infrastructure.linkedin.parsers import is_cloudflare_challenge
from tests.fixtures.linkedin_search import (
    BLOCK_PAGE_HTML,
    CLOUDFLARE_CHALLENGE_HTML,
    SEARCH_PAGE_HTML,
)


class TestIsCloudflareChallenge:
    """REQ-LST-CF-001..003 — the detector + the cards-win rule."""

    def test_is_cloudflare_challenge_true_on_cloudflare_fixture(self) -> None:
        """REQ-LST-CF-002 — `is_cloudflare_challenge` is `True` on the fixture.

        The fixture (`CLOUDFLARE_CHALLENGE_HTML`) contains the 3
        Cloudflare 2026 markers (title "Just a moment...",
        `<noscript>`, `div.cf-mitigated` or `[data-cf-challenge]`)
        and 0 cards. The detector returns `True`.
        """
        soup = BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser")
        assert is_cloudflare_challenge(soup) is True

    def test_is_cloudflare_challenge_false_on_healthy_serp(self) -> None:
        """`is_cloudflare_challenge` is `False` on a healthy SERP (no false positive).

        The healthy SERP (`SEARCH_PAGE_HTML`) has 3 cards; the
        title is "90 Python jobs in Madrid" (NOT "Just a
        moment..."). The detector returns `False` because the
        Cloudflare title is absent.
        """
        soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
        assert is_cloudflare_challenge(soup) is False

    def test_is_cloudflare_challenge_false_on_block_page(self) -> None:
        """`is_cloudflare_challenge` is `False` on the LinkedIn auth-wall fixture.

        The `BLOCK_PAGE_HTML` fixture is the v1 LinkedIn
        auth-wall / verification page (title "Sign In |
        LinkedIn", `<form id="login">`). The detector
        correctly returns `False` because the Cloudflare
        markers are absent (the LinkedIn auth-wall is a
        distinct signal from a Cloudflare challenge).
        """
        soup = BeautifulSoup(BLOCK_PAGE_HTML, "html.parser")
        assert is_cloudflare_challenge(soup) is False

    def test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker(
        self,
    ) -> None:
        """Cards-win rule (REQ-LST-CF-003) suppresses false positives.

        A healthy SERP that happens to render Cloudflare-style
        markup (e.g. LinkedIn A/B test that reuses the "Just a
        moment..." string in a rate-limit banner) MUST NOT
        match — the function returns False when ≥1
        `div[data-entity-urn]` is present.
        """
        html = (
            "<html><head><title>Just a moment... check</title></head>"
            "<body>"
            "<noscript>redirect</noscript>"
            '<div data-cf-challenge="x"></div>'
            '<div data-entity-urn="urn:li:jobPosting:1"></div>'
            "</body></html>"
        )
        soup = BeautifulSoup(html, "html.parser")
        assert is_cloudflare_challenge(soup) is False  # cards win

    def test_is_cloudflare_challenge_is_pure_no_mutation(self) -> None:
        """REQ-LST-CF-001 — the function is pure (no mutation, no side-effects).

        A side-effect-free function takes a soup and returns a
        bool; it does not mutate the soup, does not call any
        logging facility, does not perform I/O. The test
        constructs a soup from a string, calls the function
        twice, and asserts the return value is the same on
        both calls AND the soup's HTML is unchanged.
        """
        soup_before = BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser")
        html_before = str(soup_before)
        # Call the function multiple times; assert no mutation.
        first_result = is_cloudflare_challenge(soup_before)
        second_result = is_cloudflare_challenge(soup_before)
        assert first_result is True
        assert second_result is True
        assert str(soup_before) == html_before  # no mutation


class TestCloudflareChallengeFixture:
    """`CLOUDFLARE_CHALLENGE_HTML` fixture integrity — pins the 2026 markers."""

    def test_fixture_contains_three_cloudflare_markers(self) -> None:
        """The fixture contains the 3 Cloudflare 2026 markers (pins the contract)."""
        soup = BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser")
        # Marker 1: title "Just a moment..." (Cloudflare's 2026 default)
        assert soup.find(string=lambda t: t and "Just a moment" in t) is not None
        # Marker 2: `<noscript>` redirect block
        assert soup.find("noscript") is not None
        # Marker 3: `div.cf-mitigated` or `[data-cf-challenge]`
        assert soup.select_one("div.cf-mitigated, [data-cf-challenge]") is not None

    def test_fixture_has_zero_cards(self) -> None:
        """The fixture has 0 cards (the challenge page is a non-SERP).

        The "cards win" rule (REQ-LST-CF-003) is the regression
        check: the fixture is the negative case for the cards
        selector. If a future change adds a card to the
        fixture, the rule would short-circuit the detector
        to `False` — that would be a regression.
        """
        soup = BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser")
        assert soup.select("div[data-entity-urn]") == []
