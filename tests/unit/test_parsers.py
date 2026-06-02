"""Unit tests for the LinkedIn HTML parsers.

Spec: REQ-015, REQ-024.
The fixture in `tests/fixtures/linkedin_search.py` is best-effort; live
verification in T-010 confirms whether it matches the real DOM.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bs4 import BeautifulSoup, Tag

from jobs_finder.infrastructure.linkedin.exceptions import LinkedInParseError
from jobs_finder.infrastructure.linkedin.parsers import (
    is_block_page,
    parse_company,
    parse_job_id,
    parse_location,
    parse_posted_at,
    parse_title,
    parse_url,
)
from tests.fixtures.linkedin_search import BLOCK_PAGE_HTML, SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_card() -> Tag:
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    card = soup.select_one("li[data-entity-urn]")
    assert card is not None, "fixture is missing the first result card"
    return card


def _second_card() -> Tag:
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li[data-entity-urn]")
    assert len(cards) >= 2, "fixture is missing the second result card"
    return cards[1]


def _card_missing_title() -> str:
    return """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/9999/"></a>
      <h4 class="base-card__subtitle">Acme</h4>
      <span class="job-search-card__location">Madrid</span>
    </li>
    """


def _card_missing_company() -> str:
    return """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/9999/">
        <h3 class="base-card__title">Title</h3>
      </a>
      <span class="job-search-card__location">Madrid</span>
    </li>
    """


def _card_missing_location() -> str:
    return """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/9999/">
        <h3 class="base-card__title">Title</h3>
      </a>
      <h4 class="base-card__subtitle">Acme</h4>
    </li>
    """


def _card_missing_url() -> str:
    return """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:9999">
      <h3 class="base-card__title">Title</h3>
      <h4 class="base-card__subtitle">Acme</h4>
      <span class="job-search-card__location">Madrid</span>
    </li>
    """


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_parse_job_id_extracts_id_from_card() -> None:
    """The first card's id is `3850000001`."""
    assert parse_job_id(_first_card()) == "3850000001"


def test_parse_title_extracts_title_from_card() -> None:
    assert parse_title(_first_card()) == "Senior Python Developer"


def test_parse_company_extracts_company_from_card() -> None:
    assert parse_company(_first_card()) == "Acme Corp"


def test_parse_location_extracts_location_from_card() -> None:
    assert parse_location(_first_card()) == "Madrid, Spain"


def test_parse_url_extracts_url_from_card() -> None:
    url = parse_url(_first_card())
    assert "linkedin.com/jobs/view/3850000001" in url
    assert url.startswith("https://")


def test_parse_posted_at_extracts_datetime_from_card() -> None:
    result = parse_posted_at(_first_card())
    assert result == datetime(2026, 5, 1, tzinfo=UTC)


def test_parse_posted_at_accepts_iso_offset() -> None:
    """The parser accepts a tz-aware ISO datetime (the common LinkedIn shape)."""
    fragment = """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time datetime="2026-05-01T12:34:56+02:00">yesterday</time>
    </li>
    """
    result = parse_posted_at(fragment)
    assert result is not None
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 1
    assert result.utcoffset() is not None


# ---------------------------------------------------------------------------
# Malformed inputs (each parser raises LinkedInParseError)
# ---------------------------------------------------------------------------


def test_parse_title_raises_on_missing_title() -> None:
    with pytest.raises(LinkedInParseError, match="parse_title"):
        parse_title(_card_missing_title())


def test_parse_company_raises_on_missing_company() -> None:
    with pytest.raises(LinkedInParseError, match="parse_company"):
        parse_company(_card_missing_company())


def test_parse_location_raises_on_missing_location() -> None:
    with pytest.raises(LinkedInParseError, match="parse_location"):
        parse_location(_card_missing_location())


def test_parse_url_raises_on_missing_url() -> None:
    with pytest.raises(LinkedInParseError, match="parse_url"):
        parse_url(_card_missing_url())


def test_parse_job_id_raises_on_missing_link() -> None:
    with pytest.raises(LinkedInParseError, match="parse_job_id"):
        parse_job_id(_card_missing_url())


# ---------------------------------------------------------------------------
# parse_posted_at — missing field degrades to None
# ---------------------------------------------------------------------------


def test_parse_posted_at_returns_none_when_missing() -> None:
    """Cards without `<time>` return None; the other parsers still work."""
    assert parse_posted_at(_second_card()) is None


def test_parse_posted_at_returns_none_when_datetime_attr_missing() -> None:
    """A `<time>` without a `datetime` attribute also yields None."""
    fragment = """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time>2 days ago</time>
    </li>
    """
    assert parse_posted_at(fragment) is None


def test_parse_posted_at_raises_on_malformed_datetime() -> None:
    """A `<time datetime="not-a-date">` raises LinkedInParseError."""
    fragment = """
    <li class="result-card" data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time datetime="not-a-date">whenever</time>
    </li>
    """
    with pytest.raises(LinkedInParseError, match="parse_posted_at"):
        parse_posted_at(fragment)


# ---------------------------------------------------------------------------
# is_block_page
# ---------------------------------------------------------------------------


def test_is_block_page_false_for_search_results() -> None:
    """The search-results fixture is NOT a block page."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    assert is_block_page(soup) is False


def test_is_block_page_true_for_auth_wall() -> None:
    """The auth-wall fixture (login form + auth-wall class) is a block page."""
    soup = BeautifulSoup(BLOCK_PAGE_HTML, "html.parser")
    assert is_block_page(soup) is True


def test_is_block_page_true_for_sign_in_title() -> None:
    """A page whose `<title>` says 'Sign In' is treated as a block page."""
    soup = BeautifulSoup(
        "<html><head><title>Sign In to LinkedIn</title></head><body></body></html>",
        "html.parser",
    )
    assert is_block_page(soup) is True


# ---------------------------------------------------------------------------
# Module purity
# ---------------------------------------------------------------------------


def test_parsers_module_has_no_playwright_or_async() -> None:
    """Parsers are pure: no Playwright, no async, no I/O.

    Uses AST to strip docstrings before scanning, so the module's own
    documentation may mention Playwright as a forbidden import without
    tripping the check.
    """
    import ast  # noqa: PLC0415

    from jobs_finder.infrastructure.linkedin import parsers  # noqa: PLC0415

    module_file = parsers.__file__
    assert module_file is not None
    with open(module_file, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    cleaned = ast.unparse(tree)
    assert "playwright" not in cleaned.lower()
    assert "async def" not in cleaned
    assert "asyncio" not in cleaned
    assert "requests." not in cleaned
    assert "urllib" not in cleaned


def test_parsers_accept_string_or_tag() -> None:
    """Helpers accept either an HTML fragment string or a `bs4.element.Tag`."""
    fragment = (
        '<li class="result-card" data-entity-urn="urn:li:jobPosting:1">'
        '<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/">'
        '<h3 class="base-card__title">X</h3>'
        '</a>'
        '<h4 class="base-card__subtitle">Y</h4>'
        '<span class="job-search-card__location">Z</span>'
        "</li>"
    )
    # All "required" parsers work on a string.
    assert parse_job_id(fragment) == "1"
    assert parse_title(fragment) == "X"
    assert parse_company(fragment) == "Y"
    assert parse_location(fragment) == "Z"
    assert "linkedin.com/jobs/view/1/" in parse_url(fragment)
