"""Unit tests for the InfoJobs HTML parsers.

Spec: REQ-J-001 (URL pattern is the same shape), REQ-J-005 (real
fixture replacement is T-010; placeholder is the v1 source of truth
for the parser tests). The full set of linked requirements is
enumerated in `tests/integration/test_infojobs_api.py` when the
route is wired.

The fixture in `tests/fixtures/infojobs_search.py` is a SYNTHETIC
placeholder. It exists so the parsers can land RED → GREEN without
the network. T-010 (later batch) replaces the placeholder with the
REAL captured HTML and re-runs these tests against the live DOM;
any selector assumption that disagrees with the real DOM is fixed
in the parser, not the test.

The fixture provides 15+ synthetic job cards shaped like the public
InfoJobs SERP, with relative-time strings covering the
`parse_infojobs_posted_at` contract: `Hoy`, `Hace 2 horas`,
`hace 30+ días`, `Hace 3 días`, `Recién publicado`. Per the
test-driven-development skill, the fixture is built to match the
parser contract, not vice-versa.
"""

from __future__ import annotations

import ast
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from jobs_finder.infrastructure.infojobs.exceptions import InfoJobsParseError
from jobs_finder.infrastructure.infojobs.parsers import (
    _MONTH_MAP,
    is_infojobs_blocked,
    parse_infojobs_company,
    parse_infojobs_description,
    parse_infojobs_job_id,
    parse_infojobs_location,
    parse_infojobs_posted_at,
    parse_infojobs_title,
    parse_infojobs_url,
)
from tests.fixtures.infojobs_search import BLOCKED_PAGE_HTML, SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Helpers — load cards out of the shared fixture
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path("tests/fixtures/infojobs_search.py")


def _card(idx: int) -> Tag:
    """Return the `idx`-th (0-based) job card from the real-capture fixture."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li.ij-OfferList-offerCardItem")
    assert len(cards) >= 10, f"real-capture fixture must have 10+ cards; got {len(cards)}"
    assert idx < len(cards), f"fixture does not have card index {idx}"
    return cards[idx]


def _card_missing_title() -> str:
    """A card with no `h2.ij-OfferCardContent-description-title` — exercises the missing-title path."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900001"></a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
        </div>
      </div>
    </li>
    """


def _card_missing_company() -> str:
    """A card with no `.ij-OfferCardContent-description-subtitle` — exercises the missing-company path."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900002">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
        </div>
      </div>
    </li>
    """


def _card_missing_location() -> str:
    """A card with no `.ij-OfferCardContent-description-list-item` — exercises the missing-location path."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900003">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list"></ul>
        </div>
      </div>
    </li>
    """


def _card_missing_job_id() -> str:
    """A card with no `href` on the title anchor — the only way to force `parse_infojobs_job_id` to raise."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
        </div>
      </div>
    </li>
    """


def _card_malformed_job_id() -> str:
    """A card whose `href` is malformed (no `oferta-` prefix and no id)."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/some-other-path">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
        </div>
      </div>
    </li>
    """


def _card_no_date() -> str:
    """A card with no `.ij-OfferCardContent-date` — exercises the missing-posted-at path (returns None)."""
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900006">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
        </div>
      </div>
    </li>
    """


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_parse_infojobs_job_id_extracts_offer_id_from_href() -> None:
    """The first card's id is the slug extracted from its media-link `href`.

    The real InfoJobs DOM (observed 2026-06-02) embeds the id in the
    media link's `href` shaped as `https://www.infojobs.net/{slug}/em-{id}`.
    The parser strips the `/em-` prefix to return the bare id. The
    title anchor has NO `href` in the real DOM (the title is wrapped
    in an `<h2>` without an anchor), so the parser targets the
    media link instead.
    """
    assert parse_infojobs_job_id(_card(0)) == "i98495453525856678980690018195550513554"


def test_parse_infojobs_job_id_works_for_every_fixture_card() -> None:
    """Every REAL offer card in the real-capture fixture has a distinct `em-` id.

    The InfoJobs SERP embeds promoted ad banners inside `<li>` elements
    that ALSO carry the `ij-OfferList-offerCardItem` class but are NOT
    real offer cards (they have no title heading, no media link, etc.).
    The parser's `_CARD_SELECTOR` requires the title heading
    (`h2.ij-OfferCardContent-description-title`) to disambiguate. The
    test mirrors that filter to verify the contract: every real offer
    card parses to a distinct id.
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = [
        c
        for c in soup.select("li.ij-OfferList-offerCardItem")
        if c.select_one("h2.ij-OfferCardContent-description-title") is not None
    ]
    ids = [parse_infojobs_job_id(c) for c in cards]
    assert len(ids) >= 1, "fixture must have at least one real offer card"
    assert len(ids) == len(set(ids)), "fixture has duplicate job ids"


def test_parse_infojobs_title_extracts_title() -> None:
    """The first card's title is the text content of the title heading."""
    assert (
        parse_infojobs_title(_card(0))
        == "Camarero/a, Ayudante Camarero/a - Hotel Es Figueral Nou 4* Sup"
    )


def test_parse_infojobs_company_extracts_company() -> None:
    """The first card's company comes from `.ij-OfferCardContent-description-subtitle-link`."""
    assert parse_infojobs_company(_card(0)) == "NYBAU HOTELS & RESTAURANTS"


def test_parse_infojobs_location_extracts_location() -> None:
    """The first card's location is the FIRST list-item in `.ij-OfferCardContent-description-list`."""
    assert parse_infojobs_location(_card(0)) == "Montuïri"


def test_parse_infojobs_url_builds_canonical_ofertas_url() -> None:
    """`parse_infojobs_url` builds the canonical `https://{domain}/ofertas-trabajo/oferta-{id}` URL."""
    url = parse_infojobs_url(_card(0), domain="www.infojobs.net")
    assert (
        url
        == "https://www.infojobs.net/ofertas-trabajo/oferta-i98495453525856678980690018195550513554"
    )


def test_parse_infojobs_url_respects_supplied_domain() -> None:
    """A different `domain` is reflected in the returned URL.

    The InfoJobs domain is configurable via `infojobs_domain` so
    multi-locale deployments (e.g. `br.infojobs.net`) don't bake the
    locale into the parser.
    """
    url = parse_infojobs_url(_card(0), domain="br.infojobs.net")
    assert url.startswith("https://br.infojobs.net/ofertas-trabajo/oferta-")


# ---------------------------------------------------------------------------
# parse_infojobs_posted_at — relative-time parsing (REQ-J-001/REQ-J-005)
# ---------------------------------------------------------------------------


def _today_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)


def test_parse_infojobs_posted_at_hoy_returns_today() -> None:
    """`Hoy` parses to today's date (UTC, midnight)."""
    result = parse_infojobs_posted_at(_card_with_date("Hoy"))
    assert result is not None
    assert result.date() == _today_utc().date()


def test_parse_infojobs_posted_at_recien_publicado_returns_today() -> None:
    """`Recién publicado` is a synonym for `Hoy`."""
    result = parse_infojobs_posted_at(_card_with_date("Recién publicado"))
    assert result is not None
    assert result.date() == _today_utc().date()


def test_parse_infojobs_posted_at_hace_2_horas_returns_two_hours_ago() -> None:
    """`Hace 2 horas` parses to `now - 2h` (within a small tolerance)."""
    result = parse_infojobs_posted_at(_card_with_date("Hace 2 horas"))
    assert result is not None
    delta = abs((datetime.now(UTC) - result).total_seconds() - 2 * 3600)
    assert delta < 60, f"expected ~2h ago, got {result!r}"


def test_parse_infojobs_posted_at_hace_3_dias_returns_three_days_ago() -> None:
    """`Hace 3 días` parses to `today - 3 days`."""
    result = parse_infojobs_posted_at(_card_with_date("Hace 3 días"))
    assert result is not None
    expected_date = (_today_utc() - timedelta(days=3)).date()
    assert result.date() == expected_date


def test_parse_infojobs_posted_at_hace_30_dias_returns_at_least_30_days_ago() -> None:
    """`hace 30+ días` parses to a date at least 30 days in the past.

    InfoJobs renders `30+` as `>= 30`; the parser picks a deterministic
    value (30 days) so the test is stable. The contract is documented
    in the parser docstring.
    """
    result = parse_infojobs_posted_at(_card_with_date("hace 30+ días"))
    assert result is not None
    days_ago = (_today_utc() - result).days
    assert days_ago >= 30, f"expected >=30 days ago, got {days_ago}"


def test_parse_infojobs_posted_at_missing_date_returns_none() -> None:
    """A card with no `.ij-OfferCardContent-date` element returns None — the
    spec's "missing field" path, distinct from "malformed"."""
    assert parse_infojobs_posted_at(_card_no_date()) is None


def test_parse_infojobs_posted_at_garbage_date_raises_parse_error() -> None:
    """A `<span data-testid="sincedate-tag">` with an unparseable string raises `InfoJobsParseError`."""
    fragment = """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-media">
                <a class="ij-OfferCardContent-media-link" href="https://www.infojobs.net/acme/em-999900099">
                  <img alt="Acme" />
                </a>
              </div>
              <div class="ij-OfferCardContent-description">
                <div class="ij-OfferCardContent-description-head">
                  <h2 class="ij-OfferCardContent-description-title">Title</h2>
                </div>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">Acme</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">Madrid</li>
                  <li class="ij-OfferCardContent-description-list-item">
                    <span data-testid="sincedate-tag">whenever the wind blows</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>
    """
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_posted_at"):
        parse_infojobs_posted_at(fragment)


# ---------------------------------------------------------------------------
# Helper for posted_at cases
# ---------------------------------------------------------------------------


def _card_with_date(date_text: str) -> str:
    """Wrap a relative-time string into a minimal valid card fragment.

    The fragment mirrors the real InfoJobs DOM (observed 2026-06-02):
    the date lives in `<span data-testid="sincedate-tag">` inside a
    list-item, NOT in a separate `.ij-OfferCardContent-date` div.
    The id is in the media-link's `href`, not the title anchor.
    """
    return f"""
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-media">
                <a class="ij-OfferCardContent-media-link" href="https://www.infojobs.net/acme/em-999900200">
                  <img alt="Acme" />
                </a>
              </div>
              <div class="ij-OfferCardContent-description">
                <div class="ij-OfferCardContent-description-head">
                  <h2 class="ij-OfferCardContent-description-title">Title</h2>
                </div>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">Acme</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">Madrid</li>
                  <li class="ij-OfferCardContent-description-list-item">
                    <span data-testid="sincedate-tag">{date_text}</span>
                    <span>Nueva</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>
    """


# ---------------------------------------------------------------------------
# Malformed inputs (each parser raises InfoJobsParseError)
# ---------------------------------------------------------------------------


def test_parse_infojobs_title_raises_on_missing_title() -> None:
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_title"):
        parse_infojobs_title(_card_missing_title())


def test_parse_infojobs_company_raises_on_missing_company() -> None:
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_company"):
        parse_infojobs_company(_card_missing_company())


def test_parse_infojobs_location_raises_on_missing_location() -> None:
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_location"):
        parse_infojobs_location(_card_missing_location())


def test_parse_infojobs_job_id_raises_on_missing_href() -> None:
    """A card with no `href` on the title anchor is the path that forces a raise."""
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_job_id"):
        parse_infojobs_job_id(_card_missing_job_id())


def test_parse_infojobs_job_id_raises_on_malformed_href() -> None:
    """A card with a `href` that does NOT match `/oferta-{id}` raises."""
    with pytest.raises(InfoJobsParseError, match="parse_infojobs_job_id"):
        parse_infojobs_job_id(_card_malformed_job_id())


# ---------------------------------------------------------------------------
# is_infojobs_blocked
# ---------------------------------------------------------------------------


def test_is_infojobs_blocked_false_for_search_results() -> None:
    """The placeholder search-results fixture is NOT a block page."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    assert is_infojobs_blocked(soup) is False


def test_is_infojobs_blocked_true_for_distil_browser_check_title() -> None:
    """A page whose `<title>` says 'No podemos identificar tu navegador' is a block page.

    Distil Networks' anti-bot challenge emits this exact title in
    Spanish. The detector must recognise it.
    """
    soup = BeautifulSoup(
        "<html><head><title>No podemos identificar tu navegador</title></head><body></body></html>",
        "html.parser",
    )
    assert is_infojobs_blocked(soup) is True


def test_is_infojobs_blocked_true_for_geetest_iframe() -> None:
    """A page with a Geetest iframe is a block page.

    Geetest's anti-bot iframe URL is the second canonical InfoJobs
    anti-bot signal (after Distil's title). The detector must
    recognise the iframe src.
    """
    soup = BeautifulSoup(
        "<html><head><title>InfoJobs - Verificación</title></head>"
        '<body><iframe src="https://api.geetest.com/get.php"></iframe></body></html>',
        "html.parser",
    )
    assert is_infojobs_blocked(soup) is True


def test_is_infojobs_blocked_true_for_synthetic_blocked_page_fixture() -> None:
    """The blocked-page fixture embeds the canonical Distil + Geetest markers."""
    soup = BeautifulSoup(BLOCKED_PAGE_HTML, "html.parser")
    assert is_infojobs_blocked(soup) is True


# ---------------------------------------------------------------------------
# Module purity (REQ-J-001/REQ-J-005: parsers are pure, no I/O, no Playwright)
# ---------------------------------------------------------------------------


def test_infojobs_parsers_module_has_no_playwright_or_async() -> None:
    """Parsers are pure: no Playwright, no async, no I/O.

    Uses AST to strip docstrings before scanning, so the module's own
    documentation may mention Playwright as a forbidden import without
    tripping the check. Mirrors the Indeed `test_indeed_parsers.py`
    `test_indeed_parsers_module_has_no_playwright_or_async` test.
    """
    from jobs_finder.infrastructure.infojobs import parsers  # noqa: PLC0415

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


def test_infojobs_parsers_accept_string_or_tag() -> None:
    """Helpers accept either an HTML fragment string or a `bs4.element.Tag`.

    The fragment mirrors the real InfoJobs DOM (observed 2026-06-02):
    id is in the media-link's `href` (shaped as `.../em-{id}`), title
    is the `<h2>`, company is the inner subtitle anchor, location is
    the first list item.
    """
    fragment = """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-media">
                <a class="ij-OfferCardContent-media-link" href="https://www.infojobs.net/acme/em-123456789">
                  <img alt="Acme" />
                </a>
              </div>
              <div class="ij-OfferCardContent-description">
                <div class="ij-OfferCardContent-description-head">
                  <h2 class="ij-OfferCardContent-description-title">X</h2>
                </div>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">Y</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">Z</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>
    """
    assert parse_infojobs_job_id(fragment) == "123456789"
    assert parse_infojobs_title(fragment) == "X"
    assert parse_infojobs_company(fragment) == "Y"
    assert parse_infojobs_location(fragment) == "Z"
    assert parse_infojobs_url(fragment, domain="www.infojobs.net") == (
        "https://www.infojobs.net/ofertas-trabajo/oferta-123456789"
    )


# ---------------------------------------------------------------------------
# Fixture sanity (the placeholder must satisfy the parser contract)
# ---------------------------------------------------------------------------


def test_real_capture_fixture_has_at_least_10_offer_or_banner_elements() -> None:
    """The T-010 real-capture fixture has 10+ card-like elements.

    The T-010 real capture against `?q=python&l=madrid` returned
    exactly 10 elements matching the `.ij-OfferList-offerCardItem`
    CSS class on the first page: 5 real offer cards + 5 promoted
    ad banners (which also carry the card class but lack a title
    heading and are filtered out by the parser's
    `_CARD_SELECTOR` via the `:has(h2.ij-OfferCardContent-description-title)`
    pseudo-class).

    The parser contract is unchanged: any number of cards ≥ 1 must
    parse correctly. This test is a sanity check that the fixture
    is not empty (a missing or corrupted capture would yield 0
    elements and the test would fail loudly).
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li.ij-OfferList-offerCardItem")
    assert len(cards) >= 10, f"expected 10+ card elements, got {len(cards)}"


def test_placeholder_fixture_file_path_is_loadable() -> None:
    """`tests/fixtures/infojobs_search.py` exists and is importable."""
    assert _FIXTURE_PATH.exists(), f"{_FIXTURE_PATH} must exist"


def test_placeholder_fixture_contains_required_markers() -> None:
    """The rendered fixture HTML contains the markers the parsers rely on.

    This pins the contract end-to-end at the rendered-HTML level: a
    refactor that removes (or renames) the fixture's CSS classes
    will fail here before the parser tests get a chance to surface
    cryptic BeautifulSoup `NoneType` errors.

    Markers updated for the T-010 real DOM:
    - `ij-OfferList-offerCardItem` (the card class — unchanged)
    - `ij-OfferCardContent-description-title` (the title heading)
    - `ij-OfferCardContent-description-subtitle-link` (the company
      anchor; the v1 placeholder had `description-subtitle` as a
      plain div, but the real DOM has an inner `<a>`)
    - `ij-OfferCardContent-description-list-item` (the list items —
      unchanged)
    - `data-testid="sincedate-tag"` (the relative-time span; the v1
      placeholder had `ij-OfferCardContent-date` as a separate div,
      but the real DOM nests the date in a list-item)
    - `ij-OfferCardContent-media-link` (the media link whose `href`
      contains the offer id; the v1 placeholder had the id on the
      title anchor, but the real DOM has the title without `href`
      and the id on the media link)
    - `/em-` (the URL pattern in the media-link `href`)
    """
    text = SEARCH_PAGE_HTML
    for marker in (
        "ij-OfferList-offerCardItem",
        "ij-OfferCardContent-description-title",
        "ij-OfferCardContent-description-subtitle-link",
        "ij-OfferCardContent-description-list-item",
        'data-testid="sincedate-tag"',
        "ij-OfferCardContent-media-link",
        "/em-",
    ):
        assert marker in text, f"fixture missing required marker {marker!r}"


# ---------------------------------------------------------------------------
# Blocked-page fixture sanity (REQ-J-001..J-006: detector must recognise
# both canonical anti-bot signals).
# ---------------------------------------------------------------------------


def test_blocked_page_fixture_contains_distil_title_and_geetest_iframe() -> None:
    """`BLOCKED_PAGE_HTML` contains BOTH canonical anti-bot signals.

    The fixture embeds the Distil title AND a Geetest iframe so the
    detector's "any one is sufficient" contract is satisfied even if
    the distil title string changes slightly in the future (the
    iframe is the second-line fallback).
    """
    text = BLOCKED_PAGE_HTML
    assert "No podemos identificar tu navegador" in text, (
        "blocked fixture must contain Distil's Spanish title"
    )
    assert "api.geetest.com" in text, "blocked fixture must contain a Geetest iframe"
    # No InfoJobs offer cards should be present (this is a block page, not a SERP).
    assert "ij-OfferList-offerCardItem" not in text, "blocked fixture must NOT contain offer cards"


# ---------------------------------------------------------------------------
# REQ-J-004: source-neutral use case name.
#
# NOTE: the use case SOURCE file's neutral-name contract is asserted in
# `test_infojobs_use_case.py` (T-005). The parsers file legitimately
# contains the substring "infojobs" everywhere (the class names,
# selectors, and module path are all InfoJobs-specific by design). The
# parsers are not a source-agnostic use case; they are a per-source
# adapter. The grep test below just confirms the contract is local to
# T-005 — the parsers do not claim to be source-agnostic.
# ---------------------------------------------------------------------------


def test_parsers_legitimately_contain_infojobs_marker() -> None:
    """`parsers.py` legitimately contains the substring `infojobs` (per-source adapter).

    This is the mirror assertion of the use-case grep test: where
    `search_infojobs_jobs.py` MUST NOT contain the source name,
    `parsers.py` MUST contain it (because the parsers are a
    per-source adapter and the source name is the whole point).
    """
    parsers_file = Path("src/jobs_finder/infrastructure/infojobs/parsers.py")
    assert parsers_file.exists()
    text = parsers_file.read_text(encoding="utf-8")
    matches = re.findall(r"infojobs", text)
    assert matches, "infojobs parsers must contain the source name (it IS the contract)"


def test_parsers_legitimately_pass_shell_grep_for_infojobs() -> None:
    """`grep -E 'infojobs' <parsers.py>` exits 0 (matches found) — by design."""
    parsers_file = Path("src/jobs_finder/infrastructure/infojobs/parsers.py")
    result = subprocess.run(
        ["grep", "-E", "infojobs", str(parsers_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"grep -E 'infojobs' {parsers_file} returned non-zero: {result.stderr!r}"
    )
    assert result.stdout, "grep stdout should contain matches"


# ---------------------------------------------------------------------------
# REQ-PARSER-INFOJOBS-001: parse_infojobs_description
#
# InfoJobs renders a job description in a `<p>` element with the
# class `ij-OfferCardContent-description-description` (real DOM,
# observed 2026-06-02 against es.infojobs.net). The `<p>` may also
# carry the `--hideOnMobile` modifier class — a CLASS-PREFIX match
# is used so the modifier doesn't break the match.
#
# The text content is multi-line (HTML rendered with newlines for
# readability) and the parser strips + collapses whitespace.
# ---------------------------------------------------------------------------


def _card_with_description(text: str, *, with_hide_on_mobile: bool = False) -> str:
    """Wrap a description string in a real-DOM-shaped InfoJobs card.

    Mirrors the real InfoJobs SERP (observed 2026-06-02):
        <p class="ij-OfferCardContent-description-description[--hideOnMobile]">
            ...text...
        </p>
    `with_hide_on_mobile=True` adds the `--hideOnMobile` modifier
    class so the class-prefix match is exercised.
    """
    class_attr = "ij-OfferCardContent-description-description"
    if with_hide_on_mobile:
        class_attr += " ij-OfferCardContent-description-description--hideOnMobile"
    return f"""
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-media">
                <a class="ij-OfferCardContent-media-link"
                   href="https://www.infojobs.net/acme/em-999900400">
                  <img alt="Acme" />
                </a>
              </div>
              <div class="ij-OfferCardContent-description">
                <div class="ij-OfferCardContent-description-head">
                  <h2 class="ij-OfferCardContent-description-title">Title</h2>
                </div>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">Acme</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">Madrid</li>
                </ul>
                <p class="{class_attr}">{text}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>
    """


def _card_missing_description() -> str:
    """A card with NO matching `<p class="ij-...-description">` element.

    The card has a title, subtitle, list, but the description
    `<p>` is absent — the parser MUST return `None`.
    """
    return """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-description">
                <h2 class="ij-OfferCardContent-description-title">Title</h2>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">Acme</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">Madrid</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>
    """


def test_parse_infojobs_description_extracts_text_from_p() -> None:
    """A card with a `<p class="...description-description">` returns the `<p>` text, stripped.

    The single-class shape (no `--hideOnMobile` modifier) is the
    baseline. The parser uses a class-prefix match so this card
    (the simpler one) is matched too — not just the variant.
    """
    fragment = _card_with_description("Se busca Técnico en Farmacia para hacer 36h semanales.")
    result = parse_infojobs_description(fragment)
    assert result == "Se busca Técnico en Farmacia para hacer 36h semanales."


def test_parse_infojobs_description_handles_hide_on_mobile_modifier() -> None:
    """A `<p class="...description-description ...--hideOnMobile">` is matched (class-prefix).

    The real InfoJobs SERP (observed 2026-06-02) renders the
    description `<p>` with TWO classes:
    `ij-OfferCardContent-description-description` AND
    `ij-OfferCardContent-description-description--hideOnMobile`.
    An exact class match (`p.ij-OfferCardContent-description-description`)
    would NOT match this shape; the parser MUST use a class-prefix
    match so the `--hideOnMobile` modifier doesn't break the
    extraction.
    """
    fragment = _card_with_description(
        "Vendedor/a 24h, CC Espai Gironés",
        with_hide_on_mobile=True,
    )
    result = parse_infojobs_description(fragment)
    assert result == "Vendedor/a 24h, CC Espai Gironés"


def test_parse_infojobs_description_strips_and_collapses_whitespace() -> None:
    """Leading / trailing / internal whitespace in the `<p>` text is collapsed.

    Real-DOM HTML from InfoJobs uses newlines for readability
    inside the `<p>` (e.g. `<p>Line 1\nLine 2\nLine 3</p>`).
    The parser strips outer whitespace and collapses internal
    runs of whitespace into a single space.
    """
    fragment = _card_with_description(
        "\n   Hotel ES FIGUERAL NOU 4* sup\n   En plena naturaleza\n   "
    )
    result = parse_infojobs_description(fragment)
    assert result == "Hotel ES FIGUERAL NOU 4* sup En plena naturaleza"


def test_parse_infojobs_description_absent_returns_none() -> None:
    """A card with no description `<p>` returns `None`.

    The parser MUST NOT raise on absent — `Job.description` is
    optional and defaults to `None`.
    """
    assert parse_infojobs_description(_card_missing_description()) is None


def test_parse_infojobs_description_empty_returns_none() -> None:
    """A `<p>` present but empty (`<p></p>`) returns `None`.

    "Empty == absent": the parser treats whitespace-only or
    empty content the same as a missing element. `Job.description`
    is `None`, NOT `""`.
    """
    fragment = _card_with_description("")
    assert parse_infojobs_description(fragment) is None


def test_parse_infojobs_description_handles_malformed_html() -> None:
    """Malformed HTML around the description `<p>` does NOT crash the parser.

    A broken nesting or unclosed attribute does NOT raise. The
    lenient BeautifulSoup parse + `get_text(strip=True)` is
    structural, not regex. The parser returns whatever text
    the lenient parse recovers.
    """
    # Unclosed `class` attribute — lenient parse still surfaces the `<p>`.
    fragment = (
        '<li><div class="ij-OfferCardContent-description">'
        '<p class="ij-OfferCardContent-description-description'
        # NO closing quote / `>` / `</p>` — truncated
        "Recovered text after malformed markup"
        # NO closing tags
    )
    # The lenient parse is "best effort": we assert the parser
    # does NOT raise. Whether the text is recovered depends on
    # the parser version; the contract is "no crash, return
    # the best-effort result".
    result = parse_infojobs_description(fragment)
    # When the parse recovers at least the `<p>` text, we
    # expect a non-None result containing the recovered text.
    # If the parse loses the text entirely, `None` is also
    # acceptable — the contract is "no exception + sane return".
    assert result is None or "Recovered text" in result


# ---------------------------------------------------------------------------
# Regression: `_MONTH_MAP` dict has no duplicate keys (REQ-MAINT-009..011).
# Bug surfaced by `ruff check` as F601 (multi-value-repeated-key-literal) at
# `parsers.py:342` — a redundant `"jul": 7` entry duplicated line 335's
# `"jul": 7`. Python silently collapses duplicates (the second value wins,
# which here equals the first), so runtime behavior was unchanged; the
# regression test asserts the structural invariant so a future re-introduction
# of the duplicate fails the test before it ever reaches production.
# ---------------------------------------------------------------------------


def test_month_map_has_no_duplicate_keys() -> None:
    """`_MONTH_MAP` MUST have the canonical 28-entry set of month keys.

    The dict literal at `parsers.py:328-343` originally had a
    duplicate `"jul"` key (line 342), which ruff flagged as F601.
    After the fix the literal has exactly one entry per key,
    yielding the canonical 28-entry dict: 12 months × 2 forms
    (with and without trailing dot) + 2 extras (`sept`,
    `sept.`). The runtime invariant — `len(_MONTH_MAP) == 28`
    AND `set(_MONTH_MAP) == expected_keys` — is preserved
    before AND after the fix because Python collapses the
    duplicate at construction time. The literal-level check
    is delegated to the ruff F601 test below.
    """
    expected_keys = {
        "ene",
        "ene.",
        "feb",
        "feb.",
        "mar",
        "mar.",
        "abr",
        "abr.",
        "may",
        "may.",
        "jun",
        "jun.",
        "jul",
        "jul.",
        "ago",
        "ago.",
        "sep",
        "sep.",
        "sept",
        "sept.",
        "oct",
        "oct.",
        "nov",
        "nov.",
        "dic",
        "dic.",
        "jan",
        "jan.",
    }
    assert len(_MONTH_MAP) == 28
    assert set(_MONTH_MAP) == expected_keys
    assert _MONTH_MAP["jul"] == 7
    assert _MONTH_MAP["jul."] == 7


def test_parse_relative_date_with_04_jul_resolves_to_july() -> None:
    """`_parse_relative_date("04 jul")` returns a datetime in July.

    This is the downstream-behavior test: even though the
    duplicate `"jul": 7` had no runtime impact (both values
    were 7), we pin the behavior so a future regression
    (e.g., accidentally mapping "jul" to 8) is caught.
    """
    from jobs_finder.infrastructure.infojobs.parsers import _parse_relative_date

    result = _parse_relative_date("04 jul")
    assert result.month == 7


def test_ruff_check_emits_zero_F601_on_parsers_module() -> None:
    """`ruff check` reports zero F601 diagnostics on `parsers.py`.

    The bug was a literal-level duplicate; ruff F601 is the
    only linter that catches it. This test re-runs ruff on
    the parsers module and asserts the count is 0. If a
    future change re-introduces a duplicate key, this fails.
    """
    import subprocess  # local import: ruff is only needed for this test
    from pathlib import Path

    parsers_py = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "jobs_finder"
        / "infrastructure"
        / "infojobs"
        / "parsers.py"
    )
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "--select", "F601", str(parsers_py)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(parsers_py.parent.parent.parent.parent),
    )
    assert "F601" not in result.stdout, (
        f"F601 detected in {parsers_py.name}:\n{result.stdout}\n{result.stderr}"
    )
