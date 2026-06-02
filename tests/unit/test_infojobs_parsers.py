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
    is_infojobs_blocked,
    parse_infojobs_company,
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
    """Return the `idx`-th (0-based) job card from the placeholder fixture."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li.ij-OfferList-offerCardItem")
    assert len(cards) >= 15, f"placeholder fixture must have 15+ cards; got {len(cards)}"
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
    """The first card's id is the slug extracted from its title-anchor `href`.

    The placeholder uses `href="/ofertas-trabajo/oferta-{id}"` and the
    parser strips the `/oferta-` prefix to return the bare id.
    """
    assert parse_infojobs_job_id(_card(0)) == "abc123001"


def test_parse_infojobs_job_id_works_for_every_fixture_card() -> None:
    """Every card in the 15+ fixture has a distinct `oferta-` id — all parse correctly."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li.ij-OfferList-offerCardItem")
    ids = [parse_infojobs_job_id(c) for c in cards]
    assert len(ids) == len(set(ids)), "fixture has duplicate job ids"


def test_parse_infojobs_title_extracts_title() -> None:
    """The first card's title is the text content of the title heading."""
    assert parse_infojobs_title(_card(0)) == "Senior Python Developer"


def test_parse_infojobs_company_extracts_company() -> None:
    """The first card's company comes from `.ij-OfferCardContent-description-subtitle`."""
    assert parse_infojobs_company(_card(0)) == "InfoJobs Co 1"


def test_parse_infojobs_location_extracts_location() -> None:
    """The first card's location is the FIRST list-item in `.ij-OfferCardContent-description-list`."""
    assert parse_infojobs_location(_card(0)) == "Madrid, Spain"


def test_parse_infojobs_url_builds_canonical_ofertas_url() -> None:
    """`parse_infojobs_url` builds the canonical `https://{domain}/ofertas-trabajo/oferta-{id}` URL."""
    url = parse_infojobs_url(_card(0), domain="www.infojobs.net")
    assert url == "https://www.infojobs.net/ofertas-trabajo/oferta-abc123001"


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
    """A `.ij-OfferCardContent-date` with an unparseable string raises `InfoJobsParseError`."""
    fragment = """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900099">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
          <div class="ij-OfferCardContent-date">whenever the wind blows</div>
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
    """Wrap a relative-time string into a minimal valid card fragment."""
    return f"""
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-999900200">
              <h2 class="ij-OfferCardContent-description-title">Title</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Acme</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Madrid</li>
          </ul>
          <div class="ij-OfferCardContent-date">{date_text}</div>
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

    The fragment mirrors the placeholder DOM: id is in the title
    anchor's `href`, title is the `<h2>`, company is the subtitle
    div, location is the first list item.
    """
    fragment = """
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link" href="/ofertas-trabajo/oferta-123456789">
              <h2 class="ij-OfferCardContent-description-title">X</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">Y</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">Z</li>
          </ul>
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


def test_placeholder_fixture_has_at_least_15_cards() -> None:
    """The placeholder must have 15+ cards per the design's REQ-J-005.

    Real InfoJobs SERPs return 10-15 cards per page; the placeholder
    overshoots so the test exercises pagination later (T-006).
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("li.ij-OfferList-offerCardItem")
    assert len(cards) >= 15, f"expected 15+ cards, got {len(cards)}"


def test_placeholder_fixture_file_path_is_loadable() -> None:
    """`tests/fixtures/infojobs_search.py` exists and is importable."""
    assert _FIXTURE_PATH.exists(), f"{_FIXTURE_PATH} must exist"


def test_placeholder_fixture_contains_required_markers() -> None:
    """The rendered fixture HTML contains the markers the parsers rely on.

    This pins the contract end-to-end at the rendered-HTML level: a
    refactor that removes (or renames) the placeholder's CSS classes
    will fail here before the parser tests get a chance to surface
    cryptic BeautifulSoup `NoneType` errors.
    """
    text = SEARCH_PAGE_HTML
    for marker in (
        "ij-OfferList-offerCardItem",
        "ij-OfferCardContent-description-title-link",
        "ij-OfferCardContent-description-title",
        "ij-OfferCardContent-description-subtitle",
        "ij-OfferCardContent-description-list-item",
        "ij-OfferCardContent-date",
        "oferta-abc123",
    ):
        assert marker in text, f"placeholder missing required marker {marker!r}"


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
