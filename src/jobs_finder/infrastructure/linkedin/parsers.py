"""Pure HTML parsers for LinkedIn job search results.

Spec: REQ-015. Each parser is a pure function on a `bs4.element.Tag` (or a
small HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field only
affects one function. The fixture used by tests lives in
`tests/fixtures/linkedin_search.py` and is best-effort — live verification
is the only signal that confirms the fixture matches the real DOM.
The current selectors match the structure observed in live captures of
the public LinkedIn job search (cards rendered inside an `<ul>` of
`<div class="base-card ... base-search-card ... job-search-card"
data-entity-urn="urn:li:jobPosting:<id>">` elements).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from jobs_finder.domain.job import Job

from .exceptions import LinkedInParseError

# Private selectors. Each function touches exactly one selector, so a
# DOM change to one field only affects one function. Names match the
# real LinkedIn DOM as captured from the public job search page.
_TITLE_SELECTOR = ".base-search-card__title"
_COMPANY_SELECTOR = ".base-search-card__subtitle"
_LOCATION_SELECTOR = ".job-search-card__location"
_URL_SELECTOR = "a.base-card__full-link"
_TIME_SELECTOR = "time.job-search-card__listdate"
_URN_ATTR = "data-entity-urn"


def _ensure_tag(fragment: str | Tag) -> Tag:
    """Coerce an HTML fragment string to a `Tag`, or return the Tag as-is."""
    if isinstance(fragment, Tag):
        return fragment
    return BeautifulSoup(fragment, "html.parser")


def _parse_error(parser: str, message: str, tag: Tag) -> LinkedInParseError:
    """Build a `LinkedInParseError` with the card snippet in `details`."""
    return LinkedInParseError(
        f"{parser}: {message}",
        details={"card_html": str(tag)[:200]},
    )


def parse_job_id(card: str | Tag) -> str:
    """Extract the LinkedIn job id from the card's `data-entity-urn`.

    The URN format (`urn:li:jobPosting:<id>`) is more stable than the
    URL slug. Falls back to URL extraction only if the URN is missing,
    which should not happen on LinkedIn's public job search.
    """
    tag = _ensure_tag(card)
    urn = tag.get(_URN_ATTR)
    if urn:
        try:
            return Job.from_urn(str(urn))
        except ValueError:
            # URN present but malformed; fall through to URL fallback.
            pass
    a = tag.select_one(_URL_SELECTOR)
    if a is None or not a.get("href"):
        raise _parse_error("parse_job_id", "no URN or /jobs/view/ link in card", tag)
    try:
        return Job.from_url(str(a["href"]))
    except ValueError as e:
        raise _parse_error("parse_job_id", str(e), tag) from e


def parse_title(card: str | Tag) -> str:
    tag = _ensure_tag(card)
    el = tag.select_one(_TITLE_SELECTOR)
    if el is None:
        raise _parse_error("parse_title", "missing element", tag)
    return el.get_text(strip=True)


def parse_company(card: str | Tag) -> str:
    tag = _ensure_tag(card)
    el = tag.select_one(_COMPANY_SELECTOR)
    if el is None:
        raise _parse_error("parse_company", "missing element", tag)
    return el.get_text(strip=True)


def parse_location(card: str | Tag) -> str:
    tag = _ensure_tag(card)
    el = tag.select_one(_LOCATION_SELECTOR)
    if el is None:
        raise _parse_error("parse_location", "missing element", tag)
    return el.get_text(strip=True)


def parse_url(card: str | Tag) -> str:
    tag = _ensure_tag(card)
    a = tag.select_one(_URL_SELECTOR)
    if a is None or not a.get("href"):
        raise _parse_error("parse_url", "missing element", tag)
    return str(a["href"])


def parse_posted_at(card: str | Tag) -> datetime | None:
    """Return the card's posting datetime, or None when the field is absent.

    A `<time>` element with a `datetime` attribute that does not parse
    raises `LinkedInParseError` — that is "malformed", not "missing".

    Real LinkedIn cards emit a DATE-only value (e.g. `2025-04-29`) with
    no time and no timezone. We coerce date-only and naive datetimes
    to UTC, because LinkedIn does not expose a per-card timezone and
    treating the absence as a hard error would mark every real card
    as malformed. The coercion is documented as a parser-level
    convention: the domain layer still rejects naive datetimes that
    flow in from other sources, so the invariant is preserved at
    the boundary.
    """
    tag = _ensure_tag(card)
    el = tag.select_one(_TIME_SELECTOR)
    if el is None:
        return None
    raw = el.get("datetime")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError as e:
        raise _parse_error("parse_posted_at", f"malformed datetime {raw!r}", tag) from e
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # Date-only (`2025-04-29`) or naive datetime — interpret as UTC.
        # This is the parser-level convention; callers MUST NOT pass a
        # naive datetime into `Job(...)` from anywhere else.
        dt = dt.replace(tzinfo=UTC)
    return dt


def is_block_page(soup: BeautifulSoup) -> bool:
    """Return True ONLY if the page is a true auth-wall with no results.

    The public LinkedIn SERP (search results page) ALWAYS contains
    a hidden sign-in modal in its HTML — the modal is hidden by
    CSS (`opacity-0 invisible pointer-events-none`) but its
    `<form id="login">` element is in the DOM. A naive check that
    looks for that form will mis-classify the entire SERP as a
    blocked page and the route will 502 even when the page has
    legitimate results.

    The fix is a short-circuit: when real job cards are present
    (`div[data-entity-urn]`) the page is the SERP, not a block
    page, full stop. We only fall through to the legacy signals
    (auth-wall class, challenge page, sign-in title) when there
    are zero cards. The partner test
    `test_is_block_page_true_for_login_form_without_any_cards`
    pins the contract from the other side.
    """
    # Cards present == the page is the SERP, not a block page.
    if soup.select("div[data-entity-urn]"):
        return False

    # No cards; check the legacy auth-wall signals.
    if soup.select_one(".auth-wall, .challenge-page"):
        return True
    if soup.select_one("form#login, form.sign-in-form"):
        return True
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    return any(token in title for token in ("sign in", "authenticate", "verify"))
