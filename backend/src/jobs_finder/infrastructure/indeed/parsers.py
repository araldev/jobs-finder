"""Pure HTML parsers for Indeed job search results.

Spec: REQ-I-006, REQ-I-009, REQ-S-003.

Each parser is a pure function on a `bs4.element.Tag` (or a small
HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field
only affects one function. The fixture used by tests lives in
`tests/fixtures/indeed_search.py` and is a REAL Playwright capture
of the public `es.indeed.com` SERP (the v1 synthetic placeholder
was replaced in the `indeed-real-fixture` change, observed
2026-06-02 against real es.indeed.com HTML).

Card structure (real DOM as of 2026-06-02):
    <div class="job_seen_beacon">
      <table class="mainContentTable">
        <tr><td class="resultContent">
          <h3 class="jobTitle">
            <a class="jcs-JobTitle" data-jk="<id>">
              <span title="<title>"><title></span>
            </a>
          </h3>
          <div class="company_location">
            <span data-testid="company-name"><company></span>
            <div data-testid="text-location"><location></div>
          </div>
          <div class="jobMetaDataGroup">
            <ul class="metadataContainer">
              <li data-testid="attribute_snippet_testid">...</li>
            </ul>
          </div>
        </td></tr>
      </table>
    </div>

Notable differences from the v1 placeholder:
- `data-jk` is on the `<a class="jcs-JobTitle">` anchor, NOT on the
  card div. The `parse_indeed_job_id` parser looks for the anchor
  first, then falls back to the card div for backward-compat with
  older fixtures.
- The job-title heading is `<h3>` (was `<h2>` in the placeholder).
- The company uses `data-testid="company-name"` (was
  `span.companyName`).
- The location uses `data-testid="text-location"` (was
  `div.companyLocation`).
- Indeed does NOT render an inline relative-time string on the
  card anymore (the date is loaded asynchronously). The
  `parse_indeed_posted_at` parser reads the timestamp from the
  document-level `mosaic-provider-jobcards` JSON blob
  (primary path) and falls back to the legacy `span.date`
  relative-time grammar (preserved for backward-compat). The
  legacy grammar is retained for the date strings Indeed
  historically used (`Hoy`, `Hace 2 horas`, `hace 30+ días`,
  `Hace 3 días`, `Recién publicado`) so older fixtures and any
  future DOM that DOES render an inline date continue to parse
  correctly.

`parse_indeed_posted_at` is the only non-trivial parser: it
first reads the `pubDate` (epoch ms) for the card from the
embedded mosaic JSON (when a `BeautifulSoup` is supplied), and
falls back to mapping the Spanish relative-time strings Indeed
historically emitted to a UTC `datetime` based on
`datetime.now(UTC)`. The grammar is small and documented inline;
an unparseable legacy string raises `IndeedParseError` so the
scraper can fail closed. The JSON path NEVER raises; it returns
`None` on any error and lets the legacy path (or the scraper's
`datetime.now(UTC)` fallback) take over.

MUST read `pubDate` (the original posting date), NEVER
`createDate` (the crawler index date). Pinned by
`tests/unit/test_indeed_parsers.py::test_real_fixture_pins_pubdate_value`.
If Indeed renames the JSON variable, the AGENTS.md rule-#1
sanctioned exception allows a one-time manual Playwright refresh
of `tests/fixtures/indeed_search.py` to capture the new shape;
this module returns `None` from the JSON path until then.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup, Tag

from .exceptions import IndeedParseError

# Private selectors. Each function touches exactly one selector, so
# a DOM change to one field only affects one function. Names match
# the public Indeed SERP DOM as observed in a real Playwright
# capture of `es.indeed.com/jobs?q=python&l=madrid` on 2026-06-02
# (see `tests/fixtures/indeed_search.py` for the captured HTML).
_CARD_SELECTOR = "div.job_seen_beacon"
_TITLE_ANCHOR_SELECTOR = "a.jcs-JobTitle"
_JOB_ID_ATTR = "data-jk"
_TITLE_SELECTOR = "a.jcs-JobTitle"
_COMPANY_SELECTOR = '[data-testid="company-name"]'
_LOCATION_SELECTOR = '[data-testid="text-location"]'
_URL_SELECTOR = "a.jcs-JobTitle"
_DATE_SELECTOR = "span.date"
# `belowJobSnippet` is the actual description block (per the real
# Indeed SERP observed 2026-06-02 against es.indeed.com). Note:
# `data-testid="attribute_snippet_testid"` is a different element
# (JOB METADATA like "Jornada completa") and MUST NOT be confused
# with the description. The parser targets ONLY `belowJobSnippet`.
_DESCRIPTION_SELECTOR = '[data-testid="belowJobSnippet"]'
# Camino 1 (full description extraction): the full job description
# is NOT in the SERP card — it lives in the detail panel that
# Indeed renders when a user clicks a card. The panel is anchored
# by `#jobDescriptionText` (real capture 2026-06-11 against
# es.indeed.com). The parser reads that element and joins its
# children into a single scrubbable string.
_DETAIL_PANEL_SELECTOR = "#jobDescriptionText"

# Substring anchor for the document-level JSON blob that holds the
# per-result `pubDate` (epoch ms). Indeed's stable cross-locale
# surface is the variable name (observed in es/fr/uk/de captures).
# Defensive substring match — if Indeed renames the variable, the
# parser returns `None` and the scraper falls back to
# `datetime.now(UTC)` (fail-closed).
_MOSAIC_ANCHOR = "mosaic-provider-jobcards"


def _to_tag(fragment: str | Tag) -> Tag:
    """Coerce an HTML fragment string to a `Tag`, or return the Tag as-is.

    When the input is a string, parse it with the stdlib parser and
    return the first TAG descendant of the document root. BeautifulSoup
    wraps every parsed fragment in a document root, and the document's
    `.contents` include interleaved whitespace `NavigableString` nodes
    that are NOT `Tag` instances — so `soup.contents[0]` is usually
    the leading whitespace, not the wrapped element. Using
    `soup.find()` skips the whitespace and returns the first real
    `Tag`. This means `tag.get(_JOB_ID_ATTR)` works the same
    whether the caller passed a string fragment or a real `Tag`.

    The unwrap is safe because the parsers are designed to be called
    on ONE card at a time; tests pass either a single-root fragment
    (`<div class="job_seen_beacon" data-jk="...">...</div>`) or a
    real `Tag` already extracted via `soup.select(...)`.
    """
    if isinstance(fragment, Tag):
        return fragment
    soup = BeautifulSoup(fragment, "html.parser")
    first = soup.find()
    if isinstance(first, Tag):
        return first
    # Empty fragment: BeautifulSoup is itself a `Tag` subclass, so the
    # document root is a valid return value when no real Tag was found.
    return soup


def _parse_error(parser: str, message: str, tag: Tag) -> IndeedParseError:
    """Build an `IndeedParseError` with the card snippet in `details`."""
    return IndeedParseError(
        f"{parser}: {message}",
        details={"card_html": str(tag)[:200]},
    )


def parse_indeed_job_id(card: str | Tag) -> str:
    """Extract the Indeed job id from the card's title anchor.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    places the `data-jk` attribute on the title anchor
    `<a class="jcs-JobTitle" data-jk="<id>">`, NOT on the card div.
    The parser looks for the anchor first; if absent, it falls back
    to the card div for backward-compat with older fixtures that
    put `data-jk` on the card div directly.
    """
    tag = _to_tag(card)
    anchor = tag.select_one(_TITLE_ANCHOR_SELECTOR)
    raw_jk: Any = None
    if anchor is not None:
        raw_jk = anchor.get(_JOB_ID_ATTR)
    if not raw_jk:
        raw_jk = tag.get(_JOB_ID_ATTR)
    if not raw_jk:
        raise _parse_error("parse_indeed_job_id", "missing data-jk attribute", tag)
    jk_str = str(raw_jk).strip()
    if not jk_str:
        raise _parse_error("parse_indeed_job_id", "empty data-jk attribute", tag)
    return jk_str


def parse_indeed_title(card: str | Tag) -> str:
    """Extract the job title from the title anchor.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    uses `<a class="jcs-JobTitle">` inside `<h3 class="jobTitle">`;
    the v1 placeholder used `<h2 class="jobTitle"><a>`. The parser
    uses the class-based anchor selector `a.jcs-JobTitle` so it
    works against both the real DOM and any older DOM that put the
    anchor inside the same `jobTitle` class.
    """
    tag = _to_tag(card)
    el = tag.select_one(_TITLE_SELECTOR)
    if el is None:
        raise _parse_error("parse_indeed_title", "missing element", tag)
    return el.get_text(strip=True)


def parse_indeed_company(card: str | Tag) -> str:
    """Extract the company name from `[data-testid="company-name"]`.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    uses `data-testid="company-name"` on a `<span>`; the v1 placeholder
    used `span.companyName`. The parser uses the data-testid selector
    so it tracks the live SERP, not the placeholder.
    """
    tag = _to_tag(card)
    el = tag.select_one(_COMPANY_SELECTOR)
    if el is None:
        raise _parse_error("parse_indeed_company", "missing element", tag)
    return el.get_text(strip=True)


def parse_indeed_location(card: str | Tag) -> str:
    """Extract the location from `[data-testid="text-location"]`.

    The real DOM (observed 2026-06-02 against real es.indeed.com HTML)
    uses `data-testid="text-location"` on a `<div>`; the v1 placeholder
    used `div.companyLocation`. The parser uses the data-testid
    selector so it tracks the live SERP, not the placeholder.
    """
    tag = _to_tag(card)
    el = tag.select_one(_LOCATION_SELECTOR)
    if el is None:
        raise _parse_error("parse_indeed_location", "missing element", tag)
    return el.get_text(strip=True)


def parse_indeed_url(card: str | Tag, domain: str = "es.indeed.com") -> str:
    """Build the canonical `https://{domain}/viewjob?jk={data-jk}` URL.

    The `domain` parameter lets the scraper pass the configured
    `Settings.indeed_domain` (e.g. `es.indeed.com`, `fr.indeed.com`)
    so multi-locale deployments don't bake the locale into the
    parser. Per REQ-I-016, the URL is the canonical viewjob link,
    NOT a SERP `/rc/clk` or `vjk=`-pinned URL.

    The job id is read from the title anchor (which carries
    `data-jk` in the real DOM, observed 2026-06-02 against real
    es.indeed.com HTML). The presence of the anchor itself is
    asserted by `_URL_SELECTOR` so a card with `data-jk` but no
    title link still fails closed.
    """
    tag = _to_tag(card)
    jk = parse_indeed_job_id(tag)
    a = tag.select_one(_URL_SELECTOR)
    if a is None:
        raise _parse_error("parse_indeed_url", "missing a.jcs-JobTitle", tag)
    return f"https://{domain}/viewjob?jk={jk}"


# Relative-time grammar for the `span.date` element.
#
# The Spanish strings Indeed emits are case-INSENSITIVE in the
# wild: the first letter may be upper or lower depending on
# whether the word starts the sentence. The grammar below matches
# both shapes. It is intentionally narrow — anything that doesn't
# match raises `IndeedParseError` so the scraper fails closed on
# a future Indeed copy change rather than silently producing
# wrong dates.
_TODAY_PATTERNS = (r"^hoy$", r"^reci[ée]n publicado$", r"^just posted$", r"^today$")
_HOURS_PATTERN = re.compile(r"^hace\s+(\d+)\s+hora(?:s)?$", re.IGNORECASE)
_DAYS_PATTERN = re.compile(r"^hace\s+(\d+)\s+d[íi]a(?:s)?$", re.IGNORECASE)
_DAYS_PLUS_PATTERN = re.compile(r"^hace\s+(\d+)\+\s*d[íi]as$", re.IGNORECASE)
_DAYS_OLD_PATTERN = re.compile(r"^hace\s+m[áa]s\s+de\s+(\d+)\s+d[íi]as$", re.IGNORECASE)


def _parse_relative_date(raw: str) -> datetime:
    """Map a Spanish relative-time string to a UTC `datetime`.

    The grammar is narrow on purpose: it accepts the 5 strings the
    placeholder fixture guarantees and a small handful of obvious
    variants (`hoy`, `today`, `just posted`, `más de N días`).
    Anything else raises `IndeedParseError` so the scraper fails
    closed. All returned datetimes are UTC and tz-aware.
    """
    text = raw.strip().lower()
    for pat in _TODAY_PATTERNS:
        if re.match(pat, text):
            return datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)
    m = _HOURS_PATTERN.match(text)
    if m:
        hours = int(m.group(1))
        return datetime.now(UTC) - timedelta(hours=hours)
    m = _DAYS_PATTERN.match(text)
    if m:
        days = int(m.group(1))
        today = datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)
        return today - timedelta(days=days)
    m = _DAYS_PLUS_PATTERN.match(text)
    if m:
        # `30+` means "at least 30". The parser picks a deterministic
        # value of 30 days so the test is stable; downstream code
        # MUST NOT interpret this as an exact date.
        days = int(m.group(1))
        today = datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)
        return today - timedelta(days=days)
    m = _DAYS_OLD_PATTERN.match(text)
    if m:
        # `más de N días` (more than N days). Use N+1 as the
        # deterministic floor.
        days = int(m.group(1)) + 1
        today = datetime.now(UTC).replace(microsecond=0, second=0, minute=0, hour=0)
        return today - timedelta(days=days)
    raise ValueError(f"unparseable relative date: {raw!r}")


def parse_indeed_posted_at(
    card: str | Tag,
    soup: BeautifulSoup | None = None,
    *,
    posted_at_map: dict[str, datetime] | None = None,
) -> datetime | None:
    """Return the card's posting datetime, or None when the field is absent.

    Strategy:
        1. If `posted_at_map` is provided, look up the card's
           `data-jk` in the pre-extracted `{data_jk: datetime}`
           map (REQ-IDF-001). This is the page-level
           optimization: the scraper extracts the map ONCE per
           page and threads it into every per-card call,
           avoiding the per-card `<script>` walk + JSON parse.
        2. Else if `soup` is provided, try `_posted_at_from_mosaic`
           to read the `pubDate` from the document-level
           `mosaic-provider-jobcards` JSON, matched by the
           card's `data-jk`. The JSON lookup is the V1 path;
           it is preserved for backward-compat (the 35
           pre-existing parser tests use it).
        3. Otherwise, try the legacy `span.date` relative-time
           grammar. This is preserved for backward-compat with
           older fixtures and any future DOM that DOES render
           an inline date.
        4. Return `None` when nothing resolves. The scraper
           falls back to `datetime.now(UTC)` for the
           `posted_at` field.

    A `span.date` element that is present but unparseable raises
    `IndeedParseError` — that is "malformed", not "missing". The
    JSON paths (V1 and V2) NEVER raise; they return `None` on
    any error so the parser fails closed.

    MUST read `pubDate` (the original posting date), NEVER
    `createDate` (the crawler index date). See
    `tests/unit/test_indeed_parsers.py::test_real_fixture_pins_pubdate_value`
    for the contract pin.

    The `posted_at_map` kwarg is keyword-only to keep the
    signature self-documenting at the call site (the scraper
    reads `parse_indeed_posted_at(card, posted_at_map=map)`
    which is obviously a page-level optimization, NOT a
    per-card soup lookup).
    """
    # V2 path (REQ-IDF-001): page-level map lookup. When the
    # caller provides a pre-extracted {data_jk: datetime} map,
    # use it directly — no <script> walk, no JSON parse, no
    # per-card soup parameter. This is the production hot path
    # for the scraper (extracted once per page in
    # `_parse_cards`).
    if posted_at_map is not None:
        data_jk = _extract_data_jk(card)
        if data_jk is not None:
            result = posted_at_map.get(data_jk)
            if result is not None:
                return result
    # V1 path: read `pubDate` from the document-level
    # `mosaic-provider-jobcards` JSON. Only attempted when the
    # caller supplies the full `BeautifulSoup` (the legacy
    # scraper path; new code uses `posted_at_map` instead).
    if soup is not None:
        data_jk = _extract_data_jk(card)
        if data_jk is not None:
            result = _posted_at_from_mosaic(soup, data_jk)
            if result is not None:
                return result
    # Legacy fallback: `span.date` relative-time grammar. The
    # selector and helper are reused unchanged so the existing
    # raise-on-malformed semantic is preserved.
    tag = _to_tag(card)
    el = tag.select_one(_DATE_SELECTOR)
    if el is None:
        return None
    raw = el.get_text(strip=True)
    if not raw:
        return None
    try:
        return _parse_relative_date(raw)
    except ValueError as e:
        raise _parse_error("parse_indeed_posted_at", str(e), tag) from e


def parse_indeed_description(card: str | Tag) -> str | None:
    """Extract the job description snippet from `[data-testid="belowJobSnippet"]`.

    The real Indeed SERP (observed 2026-06-02 against es.indeed.com
    HTML) renders a job snippet inside a
    `<div data-testid="belowJobSnippet" class="...">` block that
    typically wraps a `<ul style="list-style-type:circle;...">` of
    `<li>` bullet points. The parser finds the description block,
    collects every `<li>` inside, strips each, and joins them with
    ` | ` so the LLM downstream gets a single scrubbable string.

    IMPORTANT: the `data-testid="attribute_snippet_testid"` selector
    is a DIFFERENT element (JOB METADATA like "Jornada completa" or
    "Hace 3 días" — see `parse_indeed_posted_at`'s legacy grammar)
    and MUST NOT be confused with the description. The parser
    targets ONLY `belowJobSnippet`.

    Contract (REQ-PARSER-INDEED-001):
    - Returns the concatenated `<li>` text (each item stripped),
      joined with ` | `, when the description block has at least
      one `<li>`.
    - Returns `None` when the description element is absent OR
      when the element is present but has no `<li>` children
      (`<ul></ul>` empty == absent).
    - Does NOT raise on malformed HTML; the lenient BeautifulSoup
      parse + `get_text()` is structural, not regex.
    - The metadata `attribute_snippet_testid` element is
      NOT matched (negative contract pinned by
      `test_parse_indeed_description_does_not_match_metadata_selector`).
    """
    tag = _to_tag(card)
    container = tag.select_one(_DESCRIPTION_SELECTOR)
    if container is None:
        return None
    items = container.find_all("li")
    if not items:
        return None
    parts = [item.get_text(strip=True) for item in items]
    joined = " | ".join(parts)
    return joined.strip() or None


def parse_indeed_detail_description(card: str | Tag) -> str | None:
    """Extract the FULL job description from Indeed's detail panel.

    Spec: REQ-PARSER-INDEED-DETAIL-001 (Camino 1, 2026-06-11).

    Real capture (2026-06-11, es.indeed.com SERP) shows the
    following:

    - The SERP card's `[data-testid="belowJobSnippet"]` block is
      EMPTY in the new layout (no `<li>` children). The card
      parser returns `None` and the LLM downstream gets a null.
    - The full description lives in a separate detail panel that
      Indeed renders when a user clicks a card. The panel is
      anchored by:

          <div id="jobDescriptionText" class="jobsearch-JobComponent-description ...">
            <h2><b>Descripción:</b></h2>
            <p>...</p>
            <ul><li>...</li></ul>
            ...
          </div>

    This parser reads the panel and returns a single scrubbable
    string: top-level `<p>` and `<li>` children are joined with
    ` | ` (so the LLM gets a single line, easy to embed in a
    prompt). HTML entities are preserved (the LLM handles
    decoding). The `Descripción:` header is INCLUDED so the LLM
    sees the section labels.

    Contract:
    - Returns the joined text when the panel is present and has
      at least one non-empty `<p>` or `<li>` child.
    - Returns `None` when the panel is absent.
    - Returns `None` when the panel is present but has no
      `<p>` or `<li>` children (empty / placeholder).
    - Does NOT raise on malformed HTML.
    """
    tag = _to_tag(card)
    # The `card` arg is EITHER the panel itself (e.g. the
    # caller passed `page.eval_on_selector("#jobDescriptionText",
    # "el => el.outerHTML")` and re-parsed it) OR a containing
    # element (e.g. the whole page). Match either: if the
    # arg has id=jobDescriptionText, treat it as the panel;
    # otherwise search for the panel inside.
    tag_id = tag.get("id") if hasattr(tag, "get") else None
    if tag_id == "jobDescriptionText":
        container: Tag = tag
    else:
        found = tag.select_one(_DETAIL_PANEL_SELECTOR)
        if found is None:
            return None
        container = found
    # Collect top-level <p> and <li> children. Skip empty ones.
    parts: list[str] = []
    for child in container.find_all(["p", "li"], recursive=True):
        text = child.get_text(separator=" ", strip=True)
        if text:
            parts.append(text)
    if not parts:
        return None
    joined = " | ".join(parts)
    return joined.strip() or None


def _extract_data_jk(card: str | Tag) -> str | None:
    """Return the card's `data-jk` attribute, or `None` when absent.

    Looks at the title anchor first (real DOM shape observed
    2026-06-02 against real es.indeed.com HTML:
    `<a class="jcs-JobTitle" data-jk="<id>">`), then falls back
    to the card div (backward-compat with older fixtures that
    put `data-jk` on the card div directly).

    Returns `None` (NOT raises) on missing — the JSON path is
    opportunistic, and the caller can fall through to the
    legacy `span.date` grammar. Contrast with
    `parse_indeed_job_id` which raises `IndeedParseError` on
    missing because the `id` field is required.
    """
    tag = _to_tag(card)
    anchor = tag.select_one(_TITLE_ANCHOR_SELECTOR)
    raw_jk: Any = None
    if anchor is not None:
        raw_jk = anchor.get(_JOB_ID_ATTR)
    if not raw_jk:
        raw_jk = tag.get(_JOB_ID_ATTR)
    if not raw_jk:
        return None
    jk_str = str(raw_jk).strip()
    if not jk_str:
        return None
    return jk_str


def _find_record_by_jobkey(payload: object, target_jk: str) -> dict[str, Any] | None:
    """Walk a JSON payload (dict / list / scalar) and return the
    first dict whose `jobkey` matches `target_jk`.

    Tolerant to Indeed's schema drift: the contract is "a
    record anywhere in the payload that has
    `jobkey == data-jk`", NOT a hard-coded path like
    `payload["metaData"]["mosaicProviderJobCardsModel"]["jobs"]`.
    The path is internal Indeed detail; the lookup is path-free.

    Returns `None` on no match.
    """
    if isinstance(payload, dict):
        if str(payload.get("jobkey", "")) == target_jk:
            return payload
        for value in payload.values():
            found = _find_record_by_jobkey(value, target_jk)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_record_by_jobkey(item, target_jk)
            if found is not None:
                return found
    return None


def _posted_at_from_mosaic(soup: BeautifulSoup, data_jk: str) -> datetime | None:
    """Read the `pubDate` (epoch ms) for the given `data_jk` from
    the document-level `mosaic-provider-jobcards` JSON blob.

    Algorithm:
        1. Walk all `<script>` tags in the document.
        2. Pick each one whose text contains the anchor
           `"mosaic-provider-jobcards"` and look for the JSON
           assignment specifically (`["<anchor>"]=<value>`
           or `['<anchor>']=<value>`). The other
           occurrences of the anchor in the script (e.g.
           inside `getElementById("...")` or
           `publicPaths["..."]="..."` string assignments) are
           NOT followed by `"]=` / `']=` and are skipped.
        3. Locate the first `{` after the assignment and
           brace-count (with string-literal awareness) to the
           matching `}`. The captured substring is the JSON
           value of the mosaic entry.
        4. `json.loads` the substring and recursively walk
           the payload to find a dict whose `jobkey` matches
           `data_jk`.
        5. Read `pubDate` (NOT `createDate`); convert epoch
           ms to a UTC `datetime` via `datetime.fromtimestamp(
           pubDate / 1000, tz=UTC)`.

    Returns `None` on ANY error (missing script, malformed
    JSON, no `jobkey` match, missing or non-numeric `pubDate`,
    `datetime` overflow). The caller falls through to the
    legacy `span.date` grammar or the scraper's
    `datetime.now(UTC)` fallback. The JSON path NEVER raises.
    """
    if soup is None:
        return None
    for script in soup.find_all("script"):
        text = script.get_text() or ""
        if _MOSAIC_ANCHOR not in text:
            continue
        result = _try_extract_pub_date_from_script(text, data_jk)
        if result is not None:
            return result
    return None


def _try_extract_pub_date_from_script(text: str, data_jk: str) -> datetime | None:
    """Try to extract the `pubDate` for `data_jk` from a single
    `<script>` text. Returns `None` if this script has the
    anchor but no matching assignment / JSON / record.
    """
    idx = -1
    anchor_len = len(_MOSAIC_ANCHOR)
    while True:
        idx = text.find(_MOSAIC_ANCHOR, idx + 1)
        if idx < 0:
            return None
        after = text[idx + anchor_len :]
        # Two valid assignment shapes for the JSON value:
        # 1. Real Indeed SERP (observed 2026-06-02):
        #      providerData["mosaic-provider-jobcards"]=<json>
        #    The `"]=` (or `']=') signature distinguishes the
        #    JSON assignment from incidental occurrences
        #    (`getElementById("...")`, `publicPaths["..."]="..."`).
        # 2. Object-literal shorthand (used in test helpers):
        #      providerData: { "mosaic-provider-jobcards": <json> }
        #    The `":` (or `':`) signature marks the key.
        # In BOTH cases, the value starts with `{` after
        # skipping whitespace — a string assignment like
        # `publicPaths["..."]="<url>"` has `"` (not `{`) after
        # the `=`, so the parser correctly skips it.
        start = -1
        if after.startswith('"]=') or after.startswith("']="):
            start = _find_json_value_start_after(text, idx + anchor_len, "=")
        elif after.startswith('":') or after.startswith("':"):
            start = _find_json_value_start_after(text, idx + anchor_len, ":")
        if start < 0:
            continue
        json_text = _extract_balanced_json(text, start)
        if json_text is None:
            continue
        try:
            payload = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            continue
        record = _find_record_by_jobkey(payload, data_jk)
        if record is None:
            continue
        pub_date = record.get("pubDate")
        # `bool` is a subclass of `int` in Python; explicitly
        # reject `True` / `False` to keep the contract tight.
        if not isinstance(pub_date, (int, float)) or isinstance(pub_date, bool):
            continue
        try:
            return datetime.fromtimestamp(float(pub_date) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            continue


def _find_json_value_start_after(text: str, after: int, delim: str) -> int:
    """Return the index of the first `{` after `text[after]` that
    is preceded (after optional whitespace) by the given
    delimiter (`=` or `:`). Returns `-1` if no such `{` exists.
    """
    eq_pos = text.find(delim, after)
    if eq_pos < 0:
        return -1
    pos = eq_pos + 1
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "{":
        return -1
    return pos


def _extract_balanced_json(text: str, start: int) -> str | None:
    """Return the balanced JSON object starting at `text[start]`.

    String-literal aware: braces inside `"..."` (with
    backslash-escape handling) are NOT counted. The first
    character MUST be `{`; the returned substring includes the
    matching closing `}`. Returns `None` if the braces don't
    balance (truncated or malformed input).
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _iter_records(payload: object) -> list[dict[str, Any]]:
    """Walk a JSON payload and return every dict in the tree (DFS).

    Used by `_extract_posted_at_map` to extract all records from
    a single JSON parse. Tolerates Indeed's schema drift: the
    structure may change (e.g. `mosaicProviderJobCardsModel` →
    `results` → list of records), but every record is a dict
    somewhere in the tree. Returns a flat list of all dicts
    found, with the outer-most dicts first (pre-order traversal).

    The walker returns EVERY dict (not just the leaf dicts) so
    the caller can also pick up records that nest their
    metadata inline. The caller is responsible for filtering
    by `jobkey` and `pubDate`.
    """
    result: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        result.append(payload)
        for value in payload.values():
            result.extend(_iter_records(value))
    elif isinstance(payload, list):
        for item in payload:
            result.extend(_iter_records(item))
    return result


def _parse_mosaic_script_to_map(text: str) -> dict[str, datetime] | None:
    """Parse a single `<script>` text and return its `{data_jk: datetime}` map.

    Walks the script looking for the `mosaic-provider-jobcards`
    anchor, extracts the JSON assignment, parses it, and converts
    the payload to a map via `_build_record_map`. Returns `None`
    on any error (no valid anchor, malformed JSON). The caller
    (`_extract_posted_at_map`) iterates over `<script>` tags until
    one yields a non-`None` result.
    """
    idx = -1
    anchor_len = len(_MOSAIC_ANCHOR)
    while True:
        idx = text.find(_MOSAIC_ANCHOR, idx + 1)
        if idx < 0:
            return None
        after = text[idx + anchor_len :]
        # Two valid assignment shapes (same as
        # `_try_extract_pub_date_from_script`):
        # 1. Real Indeed SERP: `"]=` (or `']=')
        # 2. Test-helper shorthand: `":` (or `':`)
        start = -1
        if after.startswith('"]=') or after.startswith("']="):
            start = _find_json_value_start_after(text, idx + anchor_len, "=")
        elif after.startswith('":') or after.startswith("':"):
            start = _find_json_value_start_after(text, idx + anchor_len, ":")
        if start < 0:
            continue
        json_text = _extract_balanced_json(text, start)
        if json_text is None:
            continue
        try:
            payload = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            continue
        return _build_record_map(payload)


def _build_record_map(payload: object) -> dict[str, datetime]:
    """Convert a parsed mosaic JSON payload into a `{data_jk: datetime}` map.

    Skips records missing `jobkey` or with non-numeric `pubDate`.
    First `jobkey` match wins (mirrors `_find_record_by_jobkey`'s
    "return the first match" semantic); subsequent records with
    the same `jobkey` are ignored defensively. Never raises —
    returns the partial map on any record-level error.
    """
    result: dict[str, datetime] = {}
    for record in _iter_records(payload):
        jobkey = str(record.get("jobkey", ""))
        if not jobkey or jobkey in result:
            continue
        pub_date = record.get("pubDate")
        # `bool` is a subclass of `int` in Python; reject
        # `True` / `False` to keep the contract tight.
        if not isinstance(pub_date, (int, float)) or isinstance(pub_date, bool):
            continue
        try:
            result[jobkey] = datetime.fromtimestamp(float(pub_date) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            continue
    return result


def _extract_posted_at_map(soup: BeautifulSoup) -> dict[str, datetime]:
    """Build a `{data_jk: posted_at_datetime}` map for the page.

    The page-level optimization for `parse_indeed_posted_at`
    (REQ-IDF-001): walk all `<script>` tags ONCE, find the
    `mosaic-provider-jobcards` JSON assignment, parse it, and
    extract every record's `pubDate` (epoch ms) into a flat
    dict keyed by the record's `jobkey` (which equals the
    card's `data-jk`).

    Reuses the existing helpers — `_find_json_value_start_after`,
    `_extract_balanced_json`, `json.loads`, `_iter_records` — to
    stay consistent with the v1 `_posted_at_from_mosaic` /
    `_try_extract_pub_date_from_script` path. No new parsing
    logic; just one extra loop over the records.

    Defensive: returns `{}` on ANY error (missing script,
    malformed JSON, no records, no `pubDate`, `datetime`
    overflow). The caller falls through to the v1 soup path,
    the legacy `span.date` grammar, or the scraper's
    `datetime.now(UTC)` fallback. The page-level map is an
    optimization, NOT a new hard requirement.
    """
    for script in soup.find_all("script"):
        text = script.get_text() or ""
        if _MOSAIC_ANCHOR not in text:
            continue
        record_map = _parse_mosaic_script_to_map(text)
        if record_map is not None:
            return record_map
    return {}


def is_indeed_blocked(soup: BeautifulSoup) -> bool:
    """Return True ONLY if the page is a Cloudflare / anti-bot challenge.

    The public Indeed SERP may render real results behind a JS
    challenge. The detector recognises three signals, any one of
    which is sufficient:
        1. A `<meta name="cf-mitigated" content="challenge">` hint.
        2. A `<title>` containing `Security Check`, `Access Denied`,
           or `Just a moment`.
        3. A `<meta http-equiv="refresh">` that points at the
           Cloudflare CDP URL.

    Cards present on the page (a `div.job_seen_beacon` match) means
    the page is the SERP, not a block page; in that case the
    detector returns False regardless of any incidental challenge
    markers. This mirrors the LinkedIn `is_block_page` short-circuit
    so future Indeed copy changes cannot flip the contract silently.
    """
    # Cards present == the page is the SERP, not a block page.
    if soup.select(_CARD_SELECTOR):
        return False

    # Signal 1: cf-mitigated meta tag.
    for meta in soup.select('meta[name="cf-mitigated"]'):
        content = str(meta.get("content") or "").lower()
        if "challenge" in content or "block" in content:
            return True

    # Signal 2: title contains a known anti-bot token.
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    if any(token in title for token in ("security check", "access denied", "just a moment")):
        return True

    # Signal 3: meta refresh into the Cloudflare CDP URL.
    for meta in soup.select('meta[http-equiv="refresh"]'):
        content = str(meta.get("content") or "").lower()
        if "cdn-cgi/challenge-cd" in content or "/cdp" in content:
            return True

    return False
