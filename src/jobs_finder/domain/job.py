"""Job value object — the canonical representation of a job posting across
all sources (LinkedIn, InfoJobs, ...).

Spec: REQ-007.
Design: `domain/job.py` is a frozen dataclass. `posted_at` MUST be
timezone-aware (naive is rejected in `__post_init__`). `id` is the
source-specific job id (LinkedIn numeric id, etc.).

Id extraction has two entry points:
- `from_urn(urn)`: the primary, robust path. LinkedIn's public job
  search puts the id in `data-entity-urn="urn:li:jobPosting:<id>"`
  on every card, and the URN format is far more stable than the URL
  slug.
- `from_url(url)`: a fallback. LinkedIn's URL format is
  `/jobs/view/<slug>-<id>` (with the slug being a SEO-friendly
  rewrite that the user can change). The fallback regex finds the
  trailing numeric id, robust to the slug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# A LinkedIn job id is a 7-10 digit decimal.
#
# Primary entry: `urn:li:jobPosting:<id>` on the card's
# `data-entity-urn` attribute. Format-stable.
_URN_ID_RE = re.compile(r"urn:li:jobPosting:(\d+)")
_FALLBACK_NUMERIC_RE = re.compile(r"(\d{7,})")

# Fallback entry: extract from the URL. The URL pattern is
# `/jobs/view/<slug>-<id>` where the slug is whatever LinkedIn's
# SEO rewrite chose. The trailing numeric segment is the id.
_PATH_ID_RE = re.compile(r"/jobs/view/[^\d]*?[-/](\d{7,})(?:[?#/]|$)")
# Older URLs (still in the wild): `/jobs/view/<id>/`.
_LEGACY_PATH_ID_RE = re.compile(r"/jobs/view/(\d{7,})(?:[?#/]|$)")
_QUERY_ID_RE = re.compile(r"(?:^|[?&])currentJobId=(\d{7,})")


@dataclass(frozen=True, slots=True)
class Job:
    """Immutable value object representing one job posting."""

    id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime
    description: str | None = None

    def __post_init__(self) -> None:
        if self.posted_at.tzinfo is None or self.posted_at.tzinfo.utcoffset(self.posted_at) is None:
            raise ValueError("posted_at must be timezone-aware")

    @classmethod
    def from_urn(cls, urn: str) -> str:
        """Extract the LinkedIn job id from a `urn:li:jobPosting:<id>` string.

        The URN is the most stable surface LinkedIn exposes for the job
        id: it does not depend on URL slugging, locale, or query
        parameters. Use this whenever the URN is available (i.e. for
        search-result cards that have `data-entity-urn`).
        """
        match = _URN_ID_RE.search(urn)
        if match is None:
            raise ValueError(f"Could not extract LinkedIn job id from URN: {urn!r}")
        return match.group(1)

    @classmethod
    def from_url(cls, url: str) -> str:
        """Extract the LinkedIn job id from a job URL.

        Order of preference:
            1. New-style path: `/jobs/view/<slug>-<id>` (current format).
            2. Legacy path: `/jobs/view/<id>` (older format still in the wild).
            3. Query param: `currentJobId=<id>` (search-result pages).

        Raises `ValueError` if none match. Prefer `from_urn` whenever a
        `data-entity-urn` attribute is available; URL parsing is a
        fallback because the slug can change without notice.
        """
        for regex in (_PATH_ID_RE, _LEGACY_PATH_ID_RE, _QUERY_ID_RE):
            match = regex.search(url)
            if match is not None:
                return match.group(1)
        raise ValueError(f"Could not extract LinkedIn job id from URL: {url!r}")
