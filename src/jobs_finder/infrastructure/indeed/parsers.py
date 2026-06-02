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
  `parse_indeed_posted_at` parser still looks for `span.date`; when
  absent, it returns `None` and the scraper falls back to
  `datetime.now(UTC)`. The grammar is preserved for the date
  strings Indeed historically used (`Hoy`, `Hace 2 horas`,
  `hace 30+ días`, `Hace 3 días`, `Recién publicado`) so older
  fixtures and any future DOM that DOES render an inline date
  continue to parse correctly.

`parse_indeed_posted_at` is the only non-trivial parser: it maps
the Spanish relative-time strings Indeed historically emitted to a
UTC `datetime`. The grammar is small and documented inline; an
unparseable string raises `IndeedParseError` so the scraper can
fail closed.
"""

from __future__ import annotations

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


def parse_indeed_posted_at(card: str | Tag) -> datetime | None:
    """Return the card's posting datetime, or None when the field is absent.

    Indeed cards emit a relative-time string in Spanish (e.g.
    `Hoy`, `Hace 2 horas`, `hace 30+ días`, `Recién publicado`).
    The parser maps the string to a UTC `datetime` based on
    `datetime.now(UTC)` — this is a parser-level convention that
    makes the test deterministic without freezing `now`.

    A `span.date` element that is present but unparseable raises
    `IndeedParseError` — that is "malformed", not "missing".
    """
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
