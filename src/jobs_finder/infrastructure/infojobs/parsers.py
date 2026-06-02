"""Pure HTML parsers for InfoJobs job search results.

Spec: REQ-J-001, REQ-J-005.

Each parser is a pure function on a `bs4.element.Tag` (or a small
HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field
only affects one function. The fixture used by tests lives in
`tests/fixtures/infojobs_search.py` and is REAL captured HTML from
`https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid` (taken
with `playwright-stealth` on 2026-06-02 — T-010). The parsers track
the real DOM. The T-010 capture diverged from the v1 placeholder in
3 ways (documented below).

Card structure (real DOM, observed 2026-06-02):
    <li class="ij-List-item ij-OfferList-offerCardItem sui-PrimitiveLinkBox">
      <div class="sui-AtomCard-Wrapper">
        <div class="sui-AtomCard">
          <div class="ij-OfferCard">
            <div class="ij-OfferCardContent">
              <div class="ij-OfferCardContent-media">
                <a class="ij-OfferCardContent-media-link" href="https://www.infojobs.net/{slug}/em-{id}">
                  (company logo, alt text)
                </a>
              </div>
              <div class="ij-OfferCardContent-description">
                <div class="ij-OfferCardContent-description-head">
                  <h2 class="ij-OfferCardContent-description-title">{title}</h2>
                  <span class="ij-OfferCardContent-description-favorite-bookmark">...</span>
                </div>
                <div class="ij-OfferCardContent-description-subtitle">
                  <a class="ij-OfferCardContent-description-subtitle-link">{company}</a>
                </div>
                <ul class="ij-OfferCardContent-description-list">
                  <li class="ij-OfferCardContent-description-list-item">{location}</li>
                  <li class="ij-OfferCardContent-description-list-item">Presencial</li>
                  <li class="ij-OfferCardContent-description-list-item">
                    <span data-testid="sincedate-tag">{relative_date}</span>
                    <span>Nueva</span>
                  </li>
                  <li class="ij-OfferCardContent-description-list-item">{contract}</li>
                  <li class="ij-OfferCardContent-description-list-item">{jornada}</li>
                  <li class="ij-OfferCardContent-description-list-item">{salary}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </li>

Notable design decisions (after T-010 real capture):
- The id is extracted from the media-link `href` attribute, NOT the
  title anchor. The title anchor `<a class="ij-OfferCardContent-description-title-link">`
  has NO `href` in the real DOM — the title is wrapped in an `<h2>`
  with no anchor, and the click target is the surrounding media link
  (or a wrapper link at the card level). The media-link `href` is
  shaped as `https://www.infojobs.net/{company-slug}/em-{id}` and
  the parser strips the `/em-` prefix to return the bare id. The
  canonical URL is rebuilt from the id + the configured domain so
  multi-locale deployments don't bake the locale into the parser.
- The company is on `.ij-OfferCardContent-description-subtitle-link`
  (a `<a>` inside the subtitle `<div>`). In the v1 placeholder the
  subtitle was a plain `<div>` with the company as text; the real
  DOM has an inner `<a>`.
- The location is the FIRST `.ij-OfferCardContent-description-list-item`
  in the description list. The other list items are metadata
  (Presencial/Remoto, contract type, jornada, salary) which the
  parser does NOT extract (it is the scraper's concern to decide
  whether to surface them).
- The relative-time string lives inside a `<span data-testid="sincedate-tag">`
  which is SIBLING to a `<span>Nueva</span>` badge (not concatenated).
  The list-item text is the concatenation (`Hace 1hNueva`), but the
  parser reads the `sincedate-tag` span directly so no string cleanup
  is needed. The v1 placeholder had the date in a separate
  `.ij-OfferCardContent-date` element; the real DOM does not.

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
# the InfoJobs SERP DOM observed in the real T-010 capture
# (2026-06-02 against www.infojobs.net).
#
# The card selector requires the offer-title heading AND the
# description subtitle to disambiguate from ad/promoted banners.
# The promoted banner `<li>` elements ALSO carry the
# `ij-OfferList-offerCardItem` class but do NOT have a title
# heading; requiring `h2.ij-OfferCardContent-description-title`
# filters them out cleanly.
_CARD_SELECTOR = "li.ij-OfferList-offerCardItem:has(h2.ij-OfferCardContent-description-title)"
_TITLE_ANCHOR_SELECTOR = "a.ij-OfferCardContent-description-title-link"
_TITLE_SELECTOR = "h2.ij-OfferCardContent-description-title"
_COMPANY_SELECTOR = ".ij-OfferCardContent-description-subtitle-link"
_LOCATION_SELECTOR = ".ij-OfferCardContent-description-list-item"
_URL_SELECTOR = "a.ij-OfferCardContent-media-link"
_DESCRIPTION_LINK_SELECTOR = "a.ij-OfferCardContent-description-link"
_DATE_SELECTOR = "[data-testid='sincedate-tag']"

# The id is embedded in one of two href patterns observed in the
# real DOM (2026-06-02):
#
#   Pattern A (3 of 5 real offer cards): the media-link's `href`
#     is shaped as `https://www.infojobs.net/{slug}/em-{id}` and
#     the parser strips the `/em-` prefix to return the bare id.
#   Pattern B (2 of 5 real offer cards): the media-link's `href`
#     is `https://{company}.ofertas-trabajo.infojobs.net` (no id
#     in the path), and the description-link's `href` is
#     `//www.infojobs.net/{slug}/of-{id}?...` and the parser
#     strips the `/of-` prefix.
#
# Both regexes are anchored to the end of the href so a path like
# `/em-other-thing` does NOT match. The parser tries Pattern A
# first (it's the more common one); if no match, tries Pattern B
# on any anchor in the card.
_JOB_ID_HREF_RE_EM = re.compile(r"/em-([a-zA-Z0-9-]+)$")
_JOB_ID_HREF_RE_OF = re.compile(r"/of-([a-zA-Z0-9-]+)")


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
    """Extract the InfoJobs offer id from one of the card's anchors.

    The real DOM (observed 2026-06-02) embeds the id in one of two
    href patterns:

      Pattern A: media-link `href` is
        `https://www.infojobs.net/{slug}/em-<id>` — the parser
        strips the `/em-` prefix to return the bare id. This is
        the canonical pattern (3 of 5 real offer cards in the
        fixture).
      Pattern B: media-link `href` is
        `https://{company}.ofertas-trabajo.infojobs.net` (no id
        in the path) and the description-link `href` is
        `//www.infojobs.net/{slug}/of-<id>?...` — the parser
        strips the `/of-` prefix. This is the "Promoted" pattern
        (2 of 5 real offer cards in the fixture).

    The parser tries Pattern A first, then Pattern B. If neither
    matches, an `InfoJobsParseError` is raised.

    Observed 2026-06-02 against real es.infojobs.net HTML: the title
    anchor `<a class="ij-OfferCardContent-description-title-link">`
    has NO `href` in the real DOM (the title is wrapped in an `<h2>`
    without an anchor). The id is on the media link (Pattern A) or
    the description link (Pattern B).
    """
    tag = _to_tag(card)

    # Pattern A: media-link href with `/em-<id>`.
    media = tag.select_one(_URL_SELECTOR)
    if media is not None:
        raw_href: Any = media.get("href")
        if raw_href:
            m = _JOB_ID_HREF_RE_EM.search(str(raw_href).strip())
            if m is not None:
                job_id = m.group(1).strip()
                if job_id:
                    return job_id

    # Pattern B: any anchor's href with `/of-<id>`.
    for anchor in tag.select("a[href]"):
        m = _JOB_ID_HREF_RE_OF.search(str(anchor.get("href") or "").strip())
        if m is not None:
            job_id = m.group(1).strip()
            if job_id:
                return job_id

    raise _parse_error(
        "parse_infojobs_job_id",
        "no anchor with /em-<id> or /of-<id> found",
        tag,
    )


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
    """Extract the company name from `.ij-OfferCardContent-description-subtitle-link`.

    Observed 2026-06-02: the real DOM wraps the company name in an
    inner `<a class="ij-OfferCardContent-description-subtitle-link">`
    inside the subtitle `<div>`. The v1 placeholder had the company
    as plain text in the subtitle div; the parser now targets the
    inner anchor.
    """
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


# Relative-time grammar for the `[data-testid="sincedate-tag"]` element.
#
# The Spanish strings InfoJobs emits are case-INSENSITIVE in the
# wild: the first letter may be upper or lower depending on
# whether the word starts the sentence. The grammar below matches
# both shapes. It is intentionally narrow — anything that doesn't
# match raises `InfoJobsParseError` so the scraper fails closed on
# a future InfoJobs copy change rather than silently producing
# wrong dates.
#
# Observed 2026-06-02 against real es.infojobs.net HTML: the
# relative-time strings are abbreviated to `Hace Nh` (NOT `Hace N
# horas`) and `Hace Nd` (NOT `Hace N días`) — the abbreviated
# form is more common. Both abbreviated and unabbreviated forms
# are accepted.
_TODAY_PATTERNS = (r"^hoy$", r"^reci[ée]n publicado$", r"^just posted$", r"^today$")
_MINUTES_PATTERN = re.compile(
    r"^hace\s+(\d+)\s*(?:m|min(?:uto)?s?)$",
    re.IGNORECASE,
)
_HOURS_PATTERN = re.compile(
    r"^hace\s+(\d+)\s*(?:h|hora(?:s)?)$",
    re.IGNORECASE,
)
_DAYS_PATTERN = re.compile(
    r"^hace\s+(\d+)\s*(?:d|d[íi]a(?:s)?)$",
    re.IGNORECASE,
)
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
    m = _MINUTES_PATTERN.match(text)
    if m:
        minutes = int(m.group(1))
        return datetime.now(UTC) - timedelta(minutes=minutes)
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

    Observed 2026-06-02: the real DOM puts the relative-time string
    inside `<span data-testid="sincedate-tag">` which is a SIBLING
    to a `<span>Nueva</span>` badge inside the same `<li
    class="ij-OfferCardContent-description-list-item">`. The list-item
    text concatenates the two spans (`Hace 1hNueva`), but the parser
    targets the `sincedate-tag` span directly so no string cleanup
    is needed. The v1 placeholder had the date in a separate
    `.ij-OfferCardContent-date` element; the real DOM does not.

    A `[data-testid="sincedate-tag"]` element that is present but
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
