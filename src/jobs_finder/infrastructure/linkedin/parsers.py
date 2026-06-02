"""Pure HTML parsers for LinkedIn job search results.

Spec: REQ-015. Each parser is a pure function on a `bs4.element.Tag` (or a
small HTML fragment string for tests). No I/O, no Playwright, no async,
no `Job` construction — those concerns belong to the scraper (T-006).

Selectors are private module constants; a DOM change to one field only
affects one function. The fixture used by tests lives in
`tests/fixtures/linkedin_search.py` and is best-effort — live verification
in T-010 is the only signal that confirms the fixture matches the real DOM.
"""

from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup, Tag

from jobs_finder.domain.job import Job

from .exceptions import LinkedInParseError

# Private selectors. The fixture uses these class names; live verification
# may force adjustments. Each function touches exactly one selector, so a
# DOM change to one field only affects one function.
_TITLE_SELECTOR = ".base-card__title"
_COMPANY_SELECTOR = ".base-card__subtitle"
_LOCATION_SELECTOR = ".job-search-card__location"
_URL_SELECTOR = "a.base-card__full-link"
_TIME_SELECTOR = "time"


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
    """Extract the LinkedIn job id from the card's link element.

    Reuses `Job.from_url` so the id extraction logic is not duplicated.
    """
    tag = _ensure_tag(card)
    a = tag.select_one(_URL_SELECTOR)
    if a is None or not a.get("href"):
        raise _parse_error("parse_job_id", "no /jobs/view/ link in card", tag)
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
    A naive datetime is also rejected (matches the `Job` invariant).
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
        raise _parse_error(
            "parse_posted_at", f"malformed datetime {raw!r}", tag
        ) from e
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise _parse_error("parse_posted_at", "naive datetime", tag)
    return dt


def is_block_page(soup: BeautifulSoup) -> bool:
    """Return True if the page is LinkedIn's auth-wall / verification challenge.

    Signals: a login form, an `auth-wall` or `challenge-page` class, or a
    `<title>` whose text contains `sign in`, `authenticate`, or `verify`.
    """
    if soup.select_one("form#login, form.sign-in-form, .auth-wall, .challenge-page"):
        return True
    title = (
        soup.title.string.strip().lower()
        if soup.title and soup.title.string
        else ""
    )
    return any(token in title for token in ("sign in", "authenticate", "verify"))
