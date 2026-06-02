"""Unit tests for the LinkedIn HTML parsers.

Spec: REQ-015, REQ-024.
The fixture in `tests/fixtures/linkedin_search.py` is the recorded
real-DOM shape of LinkedIn's public job search results page. It uses
`<div data-entity-urn="urn:li:jobPosting:<id>">` cards with
`base-search-card__title` / `base-search-card__subtitle` /
`job-search-card__location` / `job-search-card__listdate` children.
The `slug + numeric-id` URL format is exercised here too.
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
# Helpers — load cards out of the shared fixture
# ---------------------------------------------------------------------------


def _first_card() -> Tag:
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    card = soup.select_one("div[data-entity-urn]")
    assert card is not None, "fixture is missing the first result card"
    return card


def _second_card() -> Tag:
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div[data-entity-urn]")
    assert len(cards) >= 2, "fixture is missing the second result card"
    return cards[1]


def _third_card() -> Tag:
    """The third card in the fixture intentionally has no `<time>` element
    so `parse_posted_at` exercises the missing-field path."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div[data-entity-urn]")
    assert len(cards) >= 3, "fixture is missing the third result card"
    return cards[2]


def _card_missing_title() -> str:
    return """
    <div data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link"
         href="https://es.linkedin.com/jobs/view/no-title-9999"></a>
      <h4 class="base-search-card__subtitle">Acme</h4>
      <span class="job-search-card__location">Madrid</span>
    </div>
    """


def _card_missing_company() -> str:
    return """
    <div data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link"
         href="https://es.linkedin.com/jobs/view/no-company-9999">
        <h3 class="base-search-card__title">Title</h3>
      </a>
      <span class="job-search-card__location">Madrid</span>
    </div>
    """


def _card_missing_location() -> str:
    return """
    <div data-entity-urn="urn:li:jobPosting:9999">
      <a class="base-card__full-link"
         href="https://es.linkedin.com/jobs/view/no-location-9999">
        <h3 class="base-search-card__title">Title</h3>
      </a>
      <h4 class="base-search-card__subtitle">Acme</h4>
    </div>
    """


def _card_missing_url_and_urn() -> str:
    """A card with no URN AND no link — the only path that should fail.

    `parse_job_id` first tries the URN, then falls back to the URL
    link, so removing both is the only way to force the parser to
    raise.
    """
    return """
    <div>
      <h3 class="base-search-card__title">Title</h3>
      <h4 class="base-search-card__subtitle">Acme</h4>
      <span class="job-search-card__location">Madrid</span>
    </div>
    """


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_parse_job_id_extracts_id_from_urn() -> None:
    """The first card's id is the trailing numeric segment of the URN."""
    assert parse_job_id(_first_card()) == "4217873836"


def test_parse_job_id_works_for_each_fixture_card() -> None:
    """Each card in the fixture has a distinct URN — all parse correctly."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    expected = ["4217873836", "4349673400", "4414091381"]
    actual = [parse_job_id(c) for c in soup.select("div[data-entity-urn]")]
    assert actual == expected


def test_parse_title_extracts_title_from_card() -> None:
    assert parse_title(_first_card()) == "Developer Python/AWS"


def test_parse_company_extracts_company_from_card() -> None:
    assert parse_company(_first_card()) == "Plexus Tech"


def test_parse_location_extracts_location_from_card() -> None:
    assert parse_location(_first_card()) == "Madrid, Community of Madrid, Spain"


def test_parse_url_extracts_url_from_card() -> None:
    url = parse_url(_first_card())
    assert "linkedin.com/jobs/view/developer-python-aws-at-plexus-tech-4217873836" in url
    assert url.startswith("https://")


def test_parse_posted_at_extracts_datetime_from_card() -> None:
    """The first card has `datetime="2025-04-29"` (a date, not a full ISO)."""
    result = parse_posted_at(_first_card())
    assert result == datetime(2025, 4, 29, tzinfo=UTC)


def test_parse_posted_at_accepts_iso_offset() -> None:
    """The parser accepts a tz-aware ISO datetime (the common LinkedIn shape)."""
    fragment = """
    <div data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time class="job-search-card__listdate" datetime="2026-05-01T12:34:56+02:00">yesterday</time>
    </div>
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
    """No `<a class="base-card__full-link">` link in the card."""
    with pytest.raises(LinkedInParseError, match="parse_url"):
        parse_url(_card_missing_url_and_urn())


def test_parse_job_id_raises_on_missing_urn_and_url() -> None:
    """A card with no URN and no link is the only way to force a raise."""
    with pytest.raises(LinkedInParseError, match="parse_job_id"):
        parse_job_id(_card_missing_url_and_urn())


def test_parse_job_id_falls_back_to_url_when_urn_missing() -> None:
    """When the URN is missing, the URL is used as a fallback.

    A card with a link but no URN is rare in production but legal per
    the parser contract: the URL still carries the id via the
    `slug-id` pattern.
    """
    fragment = """
    <div>
      <a class="base-card__full-link"
         href="https://es.linkedin.com/jobs/view/no-urn-but-has-id-1234567890"></a>
    </div>
    """
    assert parse_job_id(fragment) == "1234567890"


# ---------------------------------------------------------------------------
# parse_posted_at — missing field degrades to None
# ---------------------------------------------------------------------------


def test_parse_posted_at_returns_none_when_time_element_missing() -> None:
    """The third fixture card has no `<time>` element; parser returns None."""
    assert parse_posted_at(_third_card()) is None


def test_parse_posted_at_returns_none_when_datetime_attr_missing() -> None:
    """A `<time>` without a `datetime` attribute also yields None."""
    fragment = """
    <div data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time class="job-search-card__listdate">2 days ago</time>
    </div>
    """
    assert parse_posted_at(fragment) is None


def test_parse_posted_at_raises_on_malformed_datetime() -> None:
    """A `<time datetime="not-a-date">` raises LinkedInParseError."""
    fragment = """
    <div data-entity-urn="urn:li:jobPosting:1">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1/"></a>
      <time class="job-search-card__listdate" datetime="not-a-date">whenever</time>
    </div>
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
# is_block_page — must not be fooled by hidden sign-in modals
# ---------------------------------------------------------------------------


def test_is_block_page_false_when_cards_present_even_with_login_modal() -> None:
    """A SERP page that contains a hidden `<form id="login">` inside a
    sign-in modal is still the legitimate search results page when
    real job cards are present.

    Bug (pre-fix): the public SERP always contains a hidden sign-in
    modal with `form#login`. A naive `is_block_page` that scans for
    that selector first will misclassify the entire SERP as a
    blocked page and the route will 502 even when the page has
    results. The fix is to short-circuit: cards present == not
    blocked, full stop.
    """
    from tests.fixtures.linkedin_malaga_canonical import MALAGA_CANONICAL_HTML  # noqa: PLC0415

    soup = BeautifulSoup(MALAGA_CANONICAL_HTML, "html.parser")
    # Sanity: the fixture has cards AND a form#login inside a hidden modal.
    assert soup.select("div[data-entity-urn]"), "fixture should have job cards"
    assert soup.select_one("form#login"), "fixture should have a hidden login form"
    # The login form lives inside a modal whose overlay is `invisible`
    # and `pointer-events-none` — the modal is in the DOM but not
    # visible to the user. `is_block_page` must NOT take that as a
    # signal that the page is blocked.
    assert is_block_page(soup) is False


def test_is_block_page_true_for_login_form_without_any_cards() -> None:
    """When there is a `form#login` and NO job cards, the page IS a
    real block (the auth wall proper).

    This is the partner of the previous test: cards present -> not
    blocked; no cards + login form -> blocked. The two tests pin the
    contract from both sides so a future change cannot flip one
    without breaking the other.
    """
    soup = BeautifulSoup(
        """
        <html><head><title>Sign In | LinkedIn</title></head>
        <body>
          <form id="login" action="/checkpoint">
            <input name="session_key" />
            <input name="session_password" type="password" />
          </form>
        </body></html>
        """,
        "html.parser",
    )
    assert soup.select_one("div[data-entity-urn]") is None
    assert is_block_page(soup) is True


def test_parse_cards_extracts_from_malaga_canonical_fixture() -> None:
    """The canonical-URL SERP fixture yields 3 fully-populated jobs.

    Exercises the full `_parse_cards` pipeline against a fixture
    that mirrors the structured-location SERP. Pinning this test
    prevents future DOM drift from breaking the canonical-URL path
    silently.
    """
    from jobs_finder.infrastructure.linkedin.scraper import _parse_cards  # noqa: PLC0415
    from tests.fixtures.linkedin_malaga_canonical import MALAGA_CANONICAL_HTML  # noqa: PLC0415

    soup = BeautifulSoup(MALAGA_CANONICAL_HTML, "html.parser")
    jobs = _parse_cards(soup, limit=10)
    assert len(jobs) == 3
    assert [j.id for j in jobs] == ["4354113538", "4391577086", "4417875990"]
    assert [j.title for j in jobs] == [
        "Python Developer",
        "Python Backend Developer",
        "Senior Backend Python Developer",
    ]
    assert [j.company for j in jobs] == ["Version 1", "TransPerfect", "Altia"]
    assert [j.location for j in jobs] == [
        "Málaga, Andalusia, Spain",
        "Málaga, Andalusia, Spain",
        "Málaga, Andalusia, Spain",
    ]


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
        '<div data-entity-urn="urn:li:jobPosting:1234567890">'
        '<a class="base-card__full-link" '
        'href="https://es.linkedin.com/jobs/view/x-at-y-1234567890">'
        '<h3 class="base-search-card__title">X</h3>'
        "</a>"
        '<h4 class="base-search-card__subtitle">Y</h4>'
        '<span class="job-search-card__location">Z</span>'
        "</div>"
    )
    # All "required" parsers work on a string.
    assert parse_job_id(fragment) == "1234567890"
    assert parse_title(fragment) == "X"
    assert parse_company(fragment) == "Y"
    assert parse_location(fragment) == "Z"
    assert "linkedin.com/jobs/view/x-at-y-1234567890" in parse_url(fragment)
