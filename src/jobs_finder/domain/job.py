"""Job value object — the canonical representation of a job posting across
all sources (LinkedIn, InfoJobs, ...).

Spec: REQ-007.
Design: `domain/job.py` is a frozen dataclass. `posted_at` MUST be
timezone-aware (naive is rejected in `__post_init__`). `id` is the
source-specific job id (LinkedIn numeric id, etc.). `from_url` extracts the
id from a LinkedIn URL — used by parsers that already have the URL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# A LinkedIn job id is a 7-10 digit decimal in the canonical path. The path
# segment is the source of truth; `currentJobId` is a fallback used by
# search-result pages that link to a job with the id only in the query.
_PATH_ID_RE = re.compile(r"/jobs/view/(\d+)")
_QUERY_ID_RE = re.compile(r"(?:^|[?&])currentJobId=(\d+)")


@dataclass(frozen=True, slots=True)
class Job:
    """Immutable value object representing one job posting."""

    id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime

    def __post_init__(self) -> None:
        if self.posted_at.tzinfo is None or self.posted_at.tzinfo.utcoffset(
            self.posted_at
        ) is None:
            raise ValueError("posted_at must be timezone-aware")

    @classmethod
    def from_url(cls, url: str) -> str:
        """Extract the LinkedIn job id from a job URL.

        Order of preference:
            1. Path segment: `/jobs/view/<id>` (with or without trailing slash)
            2. Query param: `currentJobId=<id>` (search-result pages)

        Raises `ValueError` if neither is present.
        """
        path_match = _PATH_ID_RE.search(url)
        if path_match is not None:
            return path_match.group(1)
        query_match = _QUERY_ID_RE.search(url)
        if query_match is not None:
            return query_match.group(1)
        raise ValueError(f"Could not extract LinkedIn job id from URL: {url!r}")
