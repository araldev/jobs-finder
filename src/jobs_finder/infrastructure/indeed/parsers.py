"""Pure HTML parsers for Indeed job search results.

Spec: REQ-I-006, REQ-I-009.

Each parser is a pure function on a `bs4.element.Tag` (or a small
HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field
only affects one function. The fixture used by tests lives in
`tests/fixtures/indeed_search.py` and is a SYNTHETIC placeholder
until T-010 replaces it with a real Playwright capture of the
public `es.indeed.com` SERP.

Card structure (mirrors the public SERP):
    <div class="job_seen_beacon" data-jk="<id>">
      <h2 class="jobTitle">
        <a href="/viewjob?jk=<id>"><title></a>
      </h2>
      <span class="companyName"><company></span>
      <div class="companyLocation"><location></div>
      <span class="date"><relative-time string></span>
    </div>

`parse_indeed_posted_at` is the only non-trivial parser: it maps
the Spanish relative-time strings Indeed emits to a UTC `datetime`.
The grammar is small and documented inline; an unparseable string
raises `IndeedParseError` so the scraper can fail closed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup, Tag

from .exceptions import IndeedParseError

# Private selectors. Each function touches exactly one selector, so
# a DOM change to one field only affects one function. Names match
# the public Indeed SERP DOM as observed in live captures of
# `es.indeed.com/jobs` (and mirrored in the placeholder fixture
# until T-010 lands the real capture).
_CARD_SELECTOR = "div.job_seen_beacon"
_JOB_ID_ATTR = "data-jk"
_TITLE_SELECTOR = "h2.jobTitle a"
_COMPANY_SELECTOR = "span.companyName"
_LOCATION_SELECTOR = "div.companyLocation"
_URL_SELECTOR = "h2.jobTitle a"
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
    """Extract the Indeed job id from the card's `data-jk` attribute."""
    tag = _to_tag(card)
    jk = tag.get(_JOB_ID_ATTR)
    if not jk:
        raise _parse_error("parse_indeed_job_id", "missing data-jk attribute", tag)
    jk_str = str(jk).strip()
    if not jk_str:
        raise _parse_error("parse_indeed_job_id", "empty data-jk attribute", tag)
    return jk_str


def parse_indeed_title(card: str | Tag) -> str:
    """Extract the job title from `h2.jobTitle a`."""
    tag = _to_tag(card)
    el = tag.select_one(_TITLE_SELECTOR)
    if el is None:
        raise _parse_error("parse_indeed_title", "missing element", tag)
    return el.get_text(strip=True)


def parse_indeed_company(card: str | Tag) -> str:
    """Extract the company name from `span.companyName`."""
    tag = _to_tag(card)
    el = tag.select_one(_COMPANY_SELECTOR)
    if el is None:
        raise _parse_error("parse_indeed_company", "missing element", tag)
    return el.get_text(strip=True)


def parse_indeed_location(card: str | Tag) -> str:
    """Extract the location from `div.companyLocation`."""
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
    """
    tag = _to_tag(card)
    jk = parse_indeed_job_id(tag)
    a = tag.select_one(_URL_SELECTOR)
    if a is None:
        raise _parse_error("parse_indeed_url", "missing h2.jobTitle a", tag)
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
