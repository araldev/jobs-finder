"""Unit tests for the Indeed HTML parsers.

Spec: REQ-I-006, REQ-I-009.

The fixture in `tests/fixtures/indeed_search.py` is a SYNTHETIC
placeholder. It exists so the parsers can land RED → GREEN without
the network. T-010 (later batch) replaces the placeholder with the
REAL captured HTML and re-runs these tests against the live DOM;
any selector assumption that disagrees with the real DOM is fixed in
the parser, not the test.

The fixture provides 15+ synthetic job cards shaped like the public
Indeed SERP, with relative-time strings covering the `parse_indeed_posted_at`
contract: `Hoy`, `Hace 2 horas`, `hace 30+ días`, `Hace 3 días`,
`Recién publicado`. Per the test-driven-development skill, the
fixture is built to match the parser contract, not vice-versa.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from jobs_finder.infrastructure.indeed.exceptions import IndeedParseError
from jobs_finder.infrastructure.indeed.parsers import (
    is_indeed_blocked,
    parse_indeed_company,
    parse_indeed_job_id,
    parse_indeed_location,
    parse_indeed_posted_at,
    parse_indeed_title,
    parse_indeed_url,
)
from tests.fixtures.indeed_search import BLOCKED_PAGE_HTML, SEARCH_PAGE_HTML

# ---------------------------------------------------------------------------
# Helpers — load cards out of the shared fixture
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path("tests/fixtures/indeed_search.py")


def _card(idx: int) -> Tag:
    """Return the `idx`-th (0-based) job card from the placeholder fixture."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div.job_seen_beacon")
    assert len(cards) >= 15, f"placeholder fixture must have 15+ cards; got {len(cards)}"
    assert idx < len(cards), f"fixture does not have card index {idx}"
    return cards[idx]


def _card_missing_title() -> str:
    """A card with no `h2.jobTitle a` — exercises the missing-title path."""
    return """
    <div class="job_seen_beacon" data-jk="999900001">
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
    </div>
    """


def _card_missing_company() -> str:
    """A card with no `span.companyName` — exercises the missing-company path."""
    return """
    <div class="job_seen_beacon" data-jk="999900002">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900002&fromage=1">Title</a>
      </h2>
      <div class="companyLocation">Madrid</div>
    </div>
    """


def _card_missing_location() -> str:
    """A card with no `div.companyLocation` — exercises the missing-location path."""
    return """
    <div class="job_seen_beacon" data-jk="999900003">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900003">Title</a>
      </h2>
      <span class="companyName">Acme</span>
    </div>
    """


def _card_missing_job_id() -> str:
    """A card with no `data-jk` — the only way to force `parse_indeed_job_id` to raise."""
    return """
    <div class="job_seen_beacon">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900004">Title</a>
      </h2>
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
    </div>
    """


def _card_missing_url_anchor() -> str:
    """A card with `data-jk` but no anchor inside `h2.jobTitle`."""
    return """
    <div class="job_seen_beacon" data-jk="999900005">
      <h2 class="jobTitle"></h2>
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
    </div>
    """


def _card_no_date() -> str:
    """A card with no `span.date` — exercises the missing-posted-at path (returns None)."""
    return """
    <div class="job_seen_beacon" data-jk="999900006">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900006">Title</a>
      </h2>
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_parse_indeed_job_id_extracts_data_jk() -> None:
    """The first card's id is the value of its `data-jk` attribute.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    puts `data-jk` on the title anchor `<a class="jcs-JobTitle">`,
    NOT on the card div. The first card's `data-jk` is
    `dd6cc0f5b0f0cfc9` (hex-shaped, not 9-digit decimal — Indeed
    uses a 16-char hex id in the live SERP).
    """
    assert parse_indeed_job_id(_card(0)) == "dd6cc0f5b0f0cfc9"


def test_parse_indeed_job_id_works_for_every_fixture_card() -> None:
    """Every card in the 15+ fixture has a distinct `data-jk` — all parse correctly."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div.job_seen_beacon")
    ids = [parse_indeed_job_id(c) for c in cards]
    assert len(ids) == len(set(ids)), "fixture has duplicate job ids"


def test_parse_indeed_title_extracts_title() -> None:
    """The first card's title is the text content of the title anchor.

    Real DOM card 0 renders the title as
    "Desarrollador Python Junior (Madrid) | Sigma AI" (the
    `| Sigma AI` is Indeed's SERP rendering quirk for this card;
    the other 15 cards in the fixture have clean titles without
    the trailing company).
    """
    assert parse_indeed_title(_card(0)) == "Desarrollador Python Junior (Madrid) | Sigma AI"


def test_parse_indeed_company_extracts_company() -> None:
    """The first card's company comes from `[data-testid="company-name"]`."""
    assert parse_indeed_company(_card(0)) == "Sigma Group"


def test_parse_indeed_location_extracts_location() -> None:
    """The first card's location comes from `[data-testid="text-location"]`."""
    assert parse_indeed_location(_card(0)) == "Madrid, Madrid provincia"


def test_parse_indeed_url_builds_canonical_viewjob_url() -> None:
    """`parse_indeed_url` builds the canonical `https://{domain}/viewjob?jk={id}` URL."""
    url = parse_indeed_url(_card(0), domain="es.indeed.com")
    assert url == "https://es.indeed.com/viewjob?jk=dd6cc0f5b0f0cfc9"


def test_parse_indeed_url_respects_supplied_domain() -> None:
    """A different `domain` is reflected in the returned URL (per REQ-I-016)."""
    url = parse_indeed_url(_card(0), domain="fr.indeed.com")
    assert url.startswith("https://fr.indeed.com/viewjob?jk=")


# ---------------------------------------------------------------------------
# parse_indeed_posted_at — relative-time parsing (REQ-I-006)
# ---------------------------------------------------------------------------


def _today_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)


def test_parse_indeed_posted_at_hoy_returns_today() -> None:
    """`Hoy` parses to today's date (UTC, midnight)."""
    result = parse_indeed_posted_at(_card_with_date("Hoy"))
    assert result is not None
    assert result.date() == _today_utc().date()


def test_parse_indeed_posted_at_recien_publicado_returns_today() -> None:
    """`Recién publicado` is a synonym for `Hoy`."""
    result = parse_indeed_posted_at(_card_with_date("Recién publicado"))
    assert result is not None
    assert result.date() == _today_utc().date()


def test_parse_indeed_posted_at_hace_2_horas_returns_two_hours_ago() -> None:
    """`Hace 2 horas` parses to `now - 2h` (within a small tolerance)."""
    result = parse_indeed_posted_at(_card_with_date("Hace 2 horas"))
    assert result is not None
    delta = abs((datetime.now(UTC) - result).total_seconds() - 2 * 3600)
    assert delta < 60, f"expected ~2h ago, got {result!r}"


def test_parse_indeed_posted_at_hace_3_dias_returns_three_days_ago() -> None:
    """`Hace 3 días` parses to `today - 3 days`."""
    result = parse_indeed_posted_at(_card_with_date("Hace 3 días"))
    assert result is not None
    expected_date = (_today_utc() - timedelta(days=3)).date()
    assert result.date() == expected_date


def test_parse_indeed_posted_at_hace_30_dias_returns_at_least_30_days_ago() -> None:
    """`hace 30+ días` parses to a date at least 30 days in the past.

    Indeed renders `30+` as `>= 30`; the parser picks a deterministic
    value (30 days) so the test is stable. The contract is
    documented in the parser docstring.
    """
    result = parse_indeed_posted_at(_card_with_date("hace 30+ días"))
    assert result is not None
    days_ago = (_today_utc() - result).days
    assert days_ago >= 30, f"expected >=30 days ago, got {days_ago}"


def test_parse_indeed_posted_at_missing_date_returns_none() -> None:
    """A card with no `span.date` element returns None — the spec's
    "missing field" path, distinct from "malformed"."""
    assert parse_indeed_posted_at(_card_no_date()) is None


def test_parse_indeed_posted_at_garbage_date_raises_parse_error() -> None:
    """A `span.date` with an unparseable string raises `IndeedParseError`."""
    fragment = """
    <div class="job_seen_beacon" data-jk="999900099">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900099">Title</a>
      </h2>
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
      <span class="date">whenever the wind blows</span>
    </div>
    """
    with pytest.raises(IndeedParseError, match="parse_indeed_posted_at"):
        parse_indeed_posted_at(fragment)


# ---------------------------------------------------------------------------
# Helper for posted_at cases
# ---------------------------------------------------------------------------


def _card_with_date(date_text: str) -> str:
    """Wrap a relative-time string into a minimal valid card fragment."""
    return f"""
    <div class="job_seen_beacon" data-jk="999900200">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=999900200">Title</a>
      </h2>
      <span class="companyName">Acme</span>
      <div class="companyLocation">Madrid</div>
      <span class="date">{date_text}</span>
    </div>
    """


# ---------------------------------------------------------------------------
# Malformed inputs (each parser raises IndeedParseError)
# ---------------------------------------------------------------------------


def test_parse_indeed_title_raises_on_missing_title() -> None:
    with pytest.raises(IndeedParseError, match="parse_indeed_title"):
        parse_indeed_title(_card_missing_title())


def test_parse_indeed_company_raises_on_missing_company() -> None:
    with pytest.raises(IndeedParseError, match="parse_indeed_company"):
        parse_indeed_company(_card_missing_company())


def test_parse_indeed_location_raises_on_missing_location() -> None:
    with pytest.raises(IndeedParseError, match="parse_indeed_location"):
        parse_indeed_location(_card_missing_location())


def test_parse_indeed_job_id_raises_on_missing_data_jk() -> None:
    """A card with no `data-jk` is the only path that forces a raise."""
    with pytest.raises(IndeedParseError, match="parse_indeed_job_id"):
        parse_indeed_job_id(_card_missing_job_id())


def test_parse_indeed_url_raises_on_missing_anchor() -> None:
    """`data-jk` is present but the `h2.jobTitle a` anchor is absent."""
    with pytest.raises(IndeedParseError, match="parse_indeed_url"):
        parse_indeed_url(_card_missing_url_anchor(), domain="es.indeed.com")


# ---------------------------------------------------------------------------
# is_indeed_blocked
# ---------------------------------------------------------------------------


def test_is_indeed_blocked_false_for_search_results() -> None:
    """The placeholder search-results fixture is NOT a block page."""
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    assert is_indeed_blocked(soup) is False


def test_is_indeed_blocked_true_for_cloudflare_security_check() -> None:
    """A synthetic Cloudflare 'Security Check' body is a block page.

    The blocked-page fixture (`BLOCKED_PAGE_HTML`) embeds the canonical
    Cloudflare challenge markers: a `cf-mitigated: challenge` header
    hint via `<meta>` AND a title containing `Security Check`. The
    detector accepts either signal (and the test ensures at least one
    is present in the fixture).
    """
    soup = BeautifulSoup(BLOCKED_PAGE_HTML, "html.parser")
    assert is_indeed_blocked(soup) is True


def test_is_indeed_blocked_true_for_access_denied_title() -> None:
    """A page whose `<title>` says 'Access Denied' is a block page.

    This is a defensive check for when Indeed's anti-bot gate renders
    a different copy than the Cloudflare default. The detector must
    recognise both shapes.
    """
    soup = BeautifulSoup(
        "<html><head><title>Access Denied</title></head><body></body></html>",
        "html.parser",
    )
    assert is_indeed_blocked(soup) is True


# ---------------------------------------------------------------------------
# Module purity (REQ-I-006: parsers are pure, no I/O, no Playwright)
# ---------------------------------------------------------------------------


def test_indeed_parsers_module_has_no_playwright_or_async() -> None:
    """Parsers are pure: no Playwright, no async, no I/O.

    Uses AST to strip docstrings before scanning, so the module's own
    documentation may mention Playwright as a forbidden import without
    tripping the check. Mirrors the LinkedIn `test_parsers.py`
    `test_parsers_module_has_no_playwright_or_async` test.
    """
    from jobs_finder.infrastructure.indeed import parsers  # noqa: PLC0415

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


def test_indeed_parsers_accept_string_or_tag() -> None:
    """Helpers accept either an HTML fragment string or a `bs4.element.Tag`.

    The fragment mirrors the real DOM observed 2026-06-02 against
    real es.indeed.com HTML: `data-jk` is on the title anchor
    `<a class="jcs-JobTitle">`; company uses
    `[data-testid="company-name"]`; location uses
    `[data-testid="text-location"]`.
    """
    fragment = """
    <div class="job_seen_beacon">
      <h3 class="jobTitle">
        <a class="jcs-JobTitle" data-jk="123456789">X</a>
      </h3>
      <span data-testid="company-name">Y</span>
      <div data-testid="text-location">Z</div>
    </div>
    """
    assert parse_indeed_job_id(fragment) == "123456789"
    assert parse_indeed_title(fragment) == "X"
    assert parse_indeed_company(fragment) == "Y"
    assert parse_indeed_location(fragment) == "Z"
    assert parse_indeed_url(fragment, domain="es.indeed.com") == (
        "https://es.indeed.com/viewjob?jk=123456789"
    )


# ---------------------------------------------------------------------------
# Fixture sanity (the placeholder must satisfy the parser contract)
# ---------------------------------------------------------------------------


def test_placeholder_fixture_has_at_least_15_cards() -> None:
    """The placeholder must have 15+ cards per the design's REQ-I-006.

    Real Indeed SERPs return 10-15 cards per page; the placeholder
    overshoots so the test exercises pagination later (T-006).
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div.job_seen_beacon")
    assert len(cards) >= 15, f"expected 15+ cards, got {len(cards)}"


def test_real_fixture_has_no_inline_relative_time_strings() -> None:
    """The real Indeed SERP (observed 2026-06-02) does NOT render
    an inline `span.date` element per card — the date is loaded
    asynchronously and is not in the first-page HTML.

    Fixture contract: the legacy `span.date` relative-time grammar
    is NOT exercised by the real fixture. The negative assertion
    (`assert date_spans == []`) pins this.

    As of `indeed-date-fix` (T-001, 2026-06-06), the parser's
    primary path is the JSON-lookup against
    `mosaic-provider-jobcards`, NOT the legacy `span.date` grammar.
    The real fixture's cards DO have a real `posted_at` value —
    the `pubDate` from the JSON — which the parser now returns.
    The dedicated `test_real_fixture_pins_pubdate_value` test
    pins the positive contract.
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div.job_seen_beacon")
    assert len(cards) >= 15, f"expected 15+ cards, got {len(cards)}"
    # No card has an inline `span.date`; assert the contract.
    date_spans = soup.select("div.job_seen_beacon span.date")
    assert date_spans == [], (
        f"real fixture should not have inline span.date elements; found {len(date_spans)}"
    )


def test_placeholder_fixture_file_path_is_loadable() -> None:
    """`tests/fixtures/indeed_search.py` exists and is importable."""
    assert _FIXTURE_PATH.exists(), f"{_FIXTURE_PATH} must exist"


# ---------------------------------------------------------------------------
# parse_indeed_posted_at — JSON path (REQ-I-009 delta, indeed-date-fix)
# ---------------------------------------------------------------------------


def _card_with_data_jk(jk: str) -> Tag:
    """Return a card `Tag` whose title anchor carries `data-jk=jk` (real DOM shape).

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    places the `data-jk` attribute on the title anchor
    `<a class="jcs-JobTitle" data-jk="<id>">`, NOT on the card div. The
    helper mirrors the real shape so the JSON-path tests exercise the
    same code path as the live capture.
    """
    soup = BeautifulSoup(
        f"""
        <div class="job_seen_beacon">
          <h3 class="jobTitle">
            <a class="jcs-JobTitle" data-jk="{jk}">Title</a>
          </h3>
        </div>
        """,
        "html.parser",
    )
    card = soup.find("div", class_="job_seen_beacon")
    assert card is not None, "test helper must produce a card Tag"
    return card


def _soup_with_mosaic_script(payload_json: str) -> BeautifulSoup:
    """Return a BeautifulSoup wrapping a `<script>` whose body contains
    `mosaic-provider-jobcards` plus the given JSON payload as its value.

    The shape mirrors the real capture (a `<script>` tag in the
    document body) so the parser exercises the same substring-match
    and brace-counting path it would on the live DOM. The payload
    is what the parser should see as the value of
    `window.mosaic.providerData["mosaic-provider-jobcards"]`.
    """
    return BeautifulSoup(
        f"""
        <html><body>
          <script id="mosaic-data">
            window.mosaic = {{ providerData: {{ "mosaic-provider-jobcards": {payload_json} }} }};
          </script>
        </body></html>
        """,
        "html.parser",
    )


def test_json_happy_path_returns_pub_date() -> None:
    """A card whose `data-jk` matches a record in the mosaic JSON returns
    the record's `pubDate` (epoch ms) as a UTC `datetime`.

    Pins the JSON happy path with `pubDate=1758690000000` →
    `datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)`. The assertion is
    not a hardcoded return — the parser must divide by 1000 and
    apply the UTC timezone for the test to pass.
    """
    soup = _soup_with_mosaic_script('{"jobs": [{"jobkey": "abc123", "pubDate": 1758690000000}]}')
    result = parse_indeed_posted_at(_card_with_data_jk("abc123"), soup)
    assert result == datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)


def test_data_jk_not_in_json_returns_none() -> None:
    """A card whose `data-jk` is NOT in the JSON returns `None`.

    The parser's contract is "JSON record with matching `jobkey`
    wins; otherwise return `None` so the scraper falls back to
    `datetime.now(UTC)`". The card `data-jk="zzz999"` is absent
    from the JSON, so no match.
    """
    soup = _soup_with_mosaic_script('{"jobs": [{"jobkey": "other456", "pubDate": 1758690000000}]}')
    result = parse_indeed_posted_at(_card_with_data_jk("zzz999"), soup)
    assert result is None


def test_no_script_tag_returns_none() -> None:
    """A soup with NO `<script>` tag at all returns `None` (defensive fail-closed).

    The parser must NOT raise on a scriptless document; it must
    return `None` so the scraper's `datetime.now(UTC)` fallback
    applies. (A page without a mosaic script is, by definition,
    not an Indeed SERP — but a generic HTML page may have no
    `<script>` at all, and the parser must not crash.)
    """
    soup = BeautifulSoup("<html><body><p>no scripts here</p></body></html>", "html.parser")
    result = parse_indeed_posted_at(_card_with_data_jk("abc123"), soup)
    assert result is None


def test_record_missing_pubdate_returns_none() -> None:
    """A matching `jobkey` without a `pubDate` returns `None` (MUST NOT
    fall back to `createDate`).

    Indeed returns BOTH `pubDate` (the original posting date) and
    `createDate` (the crawler index date). The parser MUST read
    `pubDate` ONLY — falling back to `createDate` would silently
    regress the freshness signal (a job posted in 2025-09 would
    appear to be posted in 2026-02). The negative contract is
    pinned here.
    """
    soup = _soup_with_mosaic_script('{"jobs": [{"jobkey": "abc123", "createDate": 1758690000000}]}')
    result = parse_indeed_posted_at(_card_with_data_jk("abc123"), soup)
    assert result is None


def test_malformed_pubdate_returns_none() -> None:
    """A non-numeric `pubDate` returns `None` (defensive fail-closed, no crash).

    If Indeed ever changes the field type to a string (e.g. ISO
    timestamp), the parser must not raise — it must return `None`
    so the scraper falls back to `datetime.now(UTC)` rather than
    crashing the whole response.
    """
    soup = _soup_with_mosaic_script('{"jobs": [{"jobkey": "abc123", "pubDate": "not-a-number"}]}')
    result = parse_indeed_posted_at(_card_with_data_jk("abc123"), soup)
    assert result is None


def test_legacy_span_date_still_works_when_soup_is_none() -> None:
    """The legacy `span.date` relative-time grammar is preserved as a
    fallback when the new `soup` parameter is not provided.

    Regression-protection: the parser must NOT remove the legacy
    `span.date` path when the JSON path is added. The signature
    `parse_indeed_posted_at(card)` (no `soup` arg) MUST continue
    to parse the 5 Spanish relative-time strings the existing
    grammar tests pin (`Hoy`, `Hace 2 horas`, `hace 30+ días`,
    `Recién publicado`, `Hace 3 días`).
    """
    # `_card_with_date("Hoy")` wraps the string into a minimal
    # fragment with a `<span class="date">Hoy</span>` element —
    # the legacy path is the ONLY way to get a non-`None` result
    # here because no `soup` is provided.
    result = parse_indeed_posted_at(_card_with_date("Hoy"))
    assert result is not None
    assert result.date() == _today_utc().date()


def test_json_path_wins_when_both_present() -> None:
    """When BOTH a matching JSON record AND an inline `span.date` are
    present, the JSON path's `pubDate` is returned (NOT the legacy
    grammar's value).

    Pins the "JSON wins" semantic. The card has a `data-jk` that
    matches a record with `pubDate=1758690000000` (2025-09-24)
    AND an inline `span.date` with "Hace 3 días" (today minus
    3 days). The JSON value must be returned, not the legacy
    value — the legacy value would be wrong for this test (the
    card's real posting date is 2025-09-24, not "today minus 3").
    """
    soup = _soup_with_mosaic_script('{"jobs": [{"jobkey": "abc123", "pubDate": 1758690000000}]}')
    card_html = """
    <div class="job_seen_beacon">
      <h3 class="jobTitle">
        <a class="jcs-JobTitle" data-jk="abc123">Title</a>
      </h3>
      <span class="date">Hace 3 días</span>
    </div>
    """
    card = BeautifulSoup(card_html, "html.parser").find("div", class_="job_seen_beacon")
    assert card is not None
    result = parse_indeed_posted_at(card, soup)
    assert result == datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)


def test_real_fixture_pins_pubdate_value() -> None:
    """The real `SEARCH_PAGE_HTML` capture (2026-06-02) has a first card
    with `data-jk="dd6cc0f5b0f0cfc9"` and a JSON record with
    `pubDate=1758690000000`. Calling `parse_indeed_posted_at` on
    that card must round-trip to
    `datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)`.

    Pins the contract against the live capture. If Indeed renames
    the JSON variable or moves the `pubDate` field, this test
    fails — a real regression that triggers the AGENTS.md
    rule-#1 sanctioned manual fixture refresh.
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    cards = soup.select("div.job_seen_beacon")
    assert len(cards) >= 1, "real fixture must have at least one card"
    first_card = cards[0]
    result = parse_indeed_posted_at(first_card, soup)
    assert result == datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)
