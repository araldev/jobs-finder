"""Tests for `is_auth_wall(soup)` defensive detector (T-003 of
`backend-linkedin-auth`).

Spec coverage (REQ-LA-AWALL-001..004):
- REQ-LA-AWALL-001: pure function (signature + no mutation)
- REQ-LA-AWALL-002: returns True for the BLOCK_PAGE_HTML fixture
  (auth-wall class + zero cards)
- REQ-LA-AWALL-003: returns False for a healthy SERP
  (the SEARCH_PAGE_HTML fixture has 3 cards, no auth-wall class)
- REQ-LA-AWALL-004: returns False when cards are present even with
  the `auth-wall` class ("cards win" rule, same as `is_block_page`)

The function is the WARNING-path detector (the closure emits a
WARNING log when True; REQ-LA-AWALL-005). The HARD-raise path is
still `is_block_page` (the 502 path, REQ-LA-AWALL-006 explicitly
states NO new exception type is added for the auth-wall path).
"""

from __future__ import annotations

import inspect

from bs4 import BeautifulSoup

from jobs_finder.infrastructure.linkedin.parsers import is_auth_wall
from tests.fixtures.linkedin_search import BLOCK_PAGE_HTML, SEARCH_PAGE_HTML


def test_is_auth_wall_signature() -> None:
    """REQ-LA-AWALL-001 — `is_auth_wall(soup: BeautifulSoup) -> bool`."""
    sig = inspect.signature(is_auth_wall)
    # With `from __future__ import annotations` both annotations
    # are forward-ref strings (`'BeautifulSoup'`, `'bool'`). The
    # structural assertions (1 param named `soup`, return type
    # is `bool`) are the load-bearing contract — they match the
    # project's existing test pattern at
    # `tests/unit/test_linkedin_scraper.py:188-198` and
    # `tests/unit/test_intent_extractor_port.py:52-54`.
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["soup"]
    assert sig.return_annotation == "bool" or sig.return_annotation is bool


def test_is_auth_wall_is_pure_no_mutation() -> None:
    """REQ-LA-AWALL-001 — pure function (no I/O, no `await`, no logging,
    no mutation of the input `soup`)."""
    soup = BeautifulSoup(BLOCK_PAGE_HTML, "html.parser")
    before = soup.prettify()
    result = is_auth_wall(soup)
    after = soup.prettify()
    assert result is True
    assert before == after, "is_auth_wall must not mutate the input soup"


def test_is_auth_wall_true_for_block_page_fixture() -> None:
    """REQ-LA-AWALL-002 — BLOCK_PAGE_HTML has `<body class="auth-wall">` AND
    zero job cards, so the detector returns True."""
    soup = BeautifulSoup(BLOCK_PAGE_HTML, "html.parser")
    assert is_auth_wall(soup) is True


def test_is_auth_wall_false_for_healthy_serp() -> None:
    """REQ-LA-AWALL-003 — SEARCH_PAGE_HTML is a healthy SERP with 3
    cards and NO auth-wall class."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    assert is_auth_wall(soup) is False


def test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class() -> None:
    """REQ-LA-AWALL-004 — `cards win, no false positive` rule. The HTML
    has BOTH `body.auth-wall` AND 1 card; the function returns False."""
    html = '<body class="auth-wall"><div data-entity-urn="urn:li:jobPosting:1"></div></body>'
    soup = BeautifulSoup(html, "html.parser")
    assert is_auth_wall(soup) is False
