"""Pure HTML parsers for InfoJobs job search results.

Spec: REQ-J-001, REQ-J-005.

Each parser is a pure function on a `bs4.element.Tag` (or a small
HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field
only affects one function. The fixture used by tests lives in
`tests/fixtures/infojobs_search.py` and is currently a SYNTHETIC
placeholder (mirrors the InfoJobs SERP DOM observed via `webfetch`
in the proposal phase); T-010 (later batch) replaces the placeholder
with REAL captured HTML and re-runs these tests against the live DOM.
Any selector assumption that disagrees with the real DOM is fixed
in the parser, not the test.

Card structure (placeholder, from the InfoJobs SERP observation):
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="ij-OfferCardContent">
        <div class="ij-OfferCardContent-description">
          <div class="ij-OfferCardContent-description-head">
            <a class="ij-OfferCardContent-description-title-link"
               href="/ofertas-trabajo/oferta-{id}">
              <h2 class="ij-OfferCardContent-description-title">{title}</h2>
            </a>
          </div>
          <div class="ij-OfferCardContent-description-subtitle">{company}</div>
          <ul class="ij-OfferCardContent-description-list">
            <li class="ij-OfferCardContent-description-list-item">{location}</li>
            <li class="ij-OfferCardContent-description-list-item">{salary_or_other}</li>
          </ul>
          <div class="ij-OfferCardContent-date">{posted_at}</div>
        </div>
      </div>
    </li>

Notable design decisions:
- The id is extracted from the title-anchor's `href` attribute (the
  href is `/ofertas-trabajo/oferta-{id}`), NOT from a `data-*`
  attribute. The parser strips the `/oferta-` prefix to return the
  bare id. The canonical URL is rebuilt from the id + the configured
  domain so multi-locale deployments don't bake the locale into the
  parser.
- The company is on `.ij-OfferCardContent-description-subtitle`
  (a `<div>`), NOT on a `<span>` or a `data-testid` attribute.
- The location is the FIRST `.ij-OfferCardContent-description-list-item`
  in the description list. The second list-item is salary or other
  metadata, which the parser does NOT extract (it is the scraper's
  concern to decide whether to surface it).
- InfoJobs DOES render an inline posted-date on the card (the design
  calls this out). The placeholder uses Spanish relative-time
  strings (`Hoy`, `Hace 2 horas`, `hace 30+ días`, `Hace 3 días`,
  `Recién publicado`) — same grammar as the Indeed parser — and the
  parser's `_parse_relative_date` mirrors Indeed's implementation.

`parse_infojobs_posted_at` is the only non-trivial parser: it maps
the Spanish relative-time strings InfoJobs emits to a UTC `datetime`.
The grammar is small and documented inline; an unparseable string
raises `InfoJobsParseError` so the scraper can fail closed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup, Tag

from .exceptions import InfoJobsParseError

# Private selectors. Each function touches exactly one selector, so
# a DOM change to one field only affects one function. Names mirror
# the InfoJobs SERP DOM observed via `webfetch` during the proposal
# phase of the `infojobs_platform` change; the real capture in T-010
# will confirm or correct these.
_CARD_SELECTOR = "li.ij-OfferList-offerCardItem"
_TITLE_ANCHOR_SELECTOR = "a.ij-OfferCardContent-description-title-link"
_TITLE_SELECTOR = "h2.ij-OfferCardContent-description-title"
_COMPANY_SELECTOR = ".ij-OfferCardContent-description-subtitle"
_LOCATION_SELECTOR = ".ij-OfferCardContent-description-list-item"
_URL_SELECTOR = "a.ij-OfferCardContent-description-title-link"
_DATE_SELECTOR = ".ij-OfferCardContent-date"

# The id is embedded in the title-anchor's `href` attribute, prefixed
# with `/oferta-`. The slug may contain lowercase letters, digits, and
# dashes. The regex is anchored to the end of the href so a path like
# `/ofertas-trabajo/some-other-path` does NOT match (the
# `parse_infojobs_job_id` test exercises that path).
_JOB_ID_HREF_RE = re.compile(r"/oferta-([a-zA-Z0-9-]+)$")


def _to_tag(fragment: str | Tag) -> Tag:
    """Coerce an HTML fragment string to a `Tag`, or return the Tag as-is.

    When the input is a string, parse it with the stdlib parser and
    return the first TAG descendant of the document root. BeautifulSoup
    wraps every parsed fragment in a document root, and the document's
    `.contents` include interleaved whitespace `NavigableString` nodes
    that are NOT `Tag` instances — so `soup.contents[0]` is usually
    the leading whitespace, not the wrapped element. Using
    `soup.find()` skips the whitespace and returns the first real
    `Tag`. This means `tag.get(...)` works the same whether the caller
    passed a string fragment or a real `Tag`.

    The unwrap is safe because the parsers are designed to be called
    on ONE card at a time; tests pass either a single-root fragment
    (an `<li class="ij-OfferList-offerCardItem">...</li>`) or a real
    `Tag` already extracted via `soup.select(...)`.
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


def _parse_error(parser: str, message: str, tag: Tag) -> InfoJobsParseError:
    """Build an `InfoJobsParseError` with the card snippet in `details`."""
    return InfoJobsParseError(
        f"{parser}: {message}",
        details={"card_html": str(tag)[:200]},
    )


def parse_infojobs_job_id(card: str | Tag) -> str:
    """Extract the InfoJobs offer id from the card's title-anchor `href`.

    The href is shaped as `/ofertas-trabajo/oferta-<id>` and the
    parser strips the `/oferta-` prefix to return the bare id. If
    the anchor is absent, the href is missing, or the href does
    not match the `/oferta-<id>` pattern, an `InfoJobsParseError`
    is raised.
    """
    tag = _to_tag(card)
    anchor = tag.select_one(_TITLE_ANCHOR_SELECTOR)
    if anchor is None:
        raise _parse_error("parse_infojobs_job_id", "missing title anchor", tag)
    raw_href: Any = anchor.get("href")
    if not raw_href:
        raise _parse_error("parse_infojobs_job_id", "missing href on title anchor", tag)
    href_str = str(raw_href).strip()
    m = _JOB_ID_HREF_RE.search(href_str)
    if m is None:
        raise _parse_error(
            "parse_infojobs_job_id",
            f"href {href_str!r} does not match /oferta-<id>",
            tag,
        )
    job_id = m.group(1).strip()
    if not job_id:
        raise _parse_error("parse_infojobs_job_id", "empty offer id in href", tag)
    return job_id


def parse_infojobs_title(card: str | Tag) -> str:
    """Extract the job title from the title heading.

    The placeholder DOM uses `<h2 class="ij-OfferCardContent-description-title">`
    inside the title anchor. The parser uses a class-based heading
    selector so it tracks the placeholder shape (the real T-010
    capture may need to update the heading tag if InfoJobs changes
    from `<h2>` to `<h3>`).
    """
    tag = _to_tag(card)
    el = tag.select_one(_TITLE_SELECTOR)
    if el is None:
        raise _parse_error("parse_infojobs_title", "missing element", tag)
    return el.get_text(strip=True)


def parse_infojobs_company(card: str | Tag) -> str:
    """Extract the company name from `.ij-OfferCardContent-description-subtitle`."""
    tag = _to_tag(card)
    el = tag.select_one(_COMPANY_SELECTOR)
    if el is None:
        raise _parse_error("parse_infojobs_company", "missing element", tag)
    return el.get_text(strip=True)


def parse_infojobs_location(card: str | Tag) -> str:
    """Extract the location from the FIRST `.ij-OfferCardContent-description-list-item`.

    The location is the first item in the description list. The
    second item is salary or other metadata, which the parser does
    NOT extract (it is the scraper's concern to decide whether to
    surface it).
    """
    tag = _to_tag(card)
    items = tag.select(_LOCATION_SELECTOR)
    if not items:
        raise _parse_error("parse_infojobs_location", "missing element", tag)
    return items[0].get_text(strip=True)


def parse_infojobs_url(card: str | Tag, domain: str = "www.infojobs.net") -> str:
    """Build the canonical `https://{domain}/ofertas-trabajo/oferta-{id}` URL.

    The `domain` parameter lets the scraper pass the configured
    `Settings.infojobs_domain` (e.g. `www.infojobs.net`, `br.infojobs.net`)
    so multi-locale deployments don't bake the locale into the
    parser. Per REQ-J-001, the URL is the canonical oferta link,
    NOT a SERP-pathed form.
    """
    tag = _to_tag(card)
    job_id = parse_infojobs_job_id(tag)
    return f"https://{domain}/ofertas-trabajo/oferta-{job_id}"


# Relative-time grammar for the `.ij-OfferCardContent-date` element.
#
# The Spanish strings InfoJobs emits are case-INSENSITIVE in the
# wild: the first letter may be upper or lower depending on
# whether the word starts the sentence. The grammar below matches
# both shapes. It is intentionally narrow — anything that doesn't
# match raises `InfoJobsParseError` so the scraper fails closed on
# a future InfoJobs copy change rather than silently producing
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
    Anything else raises `ValueError` so the caller can convert it
    to an `InfoJobsParseError` with parser context. All returned
    datetimes are UTC and tz-aware.
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


def parse_infojobs_posted_at(card: str | Tag) -> datetime | None:
    """Return the card's posting datetime, or None when the field is absent.

    InfoJobs cards emit a relative-time string in Spanish (e.g.
    `Hoy`, `Hace 2 horas`, `hace 30+ días`, `Recién publicado`).
    The parser maps the string to a UTC `datetime` based on
    `datetime.now(UTC)` — this is a parser-level convention that
    makes the test deterministic without freezing `now`.

    A `.ij-OfferCardContent-date` element that is present but
    unparseable raises `InfoJobsParseError` — that is "malformed",
    not "missing".
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
        raise _parse_error("parse_infojobs_posted_at", str(e), tag) from e


def is_infojobs_blocked(soup: BeautifulSoup) -> bool:
    """Return True ONLY if the page is a Distil / Geetest anti-bot challenge.

    InfoJobs' anti-bot surface is stricter than Indeed's Cloudflare:
    the very first request from a clean browser can be challenged.
    The detector recognises two signals, any one of which is
    sufficient:
        1. A `<title>` containing the Distil Spanish string
           `No podemos identificar tu navegador`.
        2. A `<iframe>` whose `src` matches the Geetest API URL
           (`api.geetest.com`).

    Cards present on the page (an `li.ij-OfferList-offerCardItem`
    match) means the page is the SERP, not a block page; in that
    case the detector returns False regardless of any incidental
    challenge markers. This mirrors the Indeed `is_indeed_blocked`
    short-circuit so future InfoJobs copy changes cannot flip the
    contract silently.
    """
    # Cards present == the page is the SERP, not a block page.
    if soup.select(_CARD_SELECTOR):
        return False

    # Signal 1: Distil's Spanish title.
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    if "no podemos identificar tu navegador" in title:
        return True

    # Signal 2: Geetest iframe (anywhere in the document).
    for iframe in soup.select("iframe[src]"):
        src = str(iframe.get("src") or "").lower()
        if "api.geetest.com" in src:
            return True

    return False
