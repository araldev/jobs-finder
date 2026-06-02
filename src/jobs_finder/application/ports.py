"""Outbound port: the application layer's contract with any job-search
source (LinkedIn, InfoJobs, ...).

Spec: REQ-008.
"""

from __future__ import annotations

from typing import Protocol

from jobs_finder.domain.job import Job


class JobSearchPort(Protocol):
    """A job-search source. Implementations live in `infrastructure/`.

    The default value on `limit` is duplicated in the Pydantic schema at the
    presentation boundary; the application trusts the caller to pass an
    already-validated value.
    """

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        """Search the source for jobs matching the criteria."""
        ...
