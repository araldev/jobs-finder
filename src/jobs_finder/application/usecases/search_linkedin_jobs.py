"""Use case: search LinkedIn for jobs matching a validated input.

Spec: REQ-008, REQ-010, REQ-011, REQ-012.
The use case is a thin orchestrator: it does not parse HTML, does not know
about Playwright, and does not catch exceptions from the port.
"""

from __future__ import annotations

from jobs_finder.application.dto import SearchLinkedInInput
from jobs_finder.application.ports import JobSearchPort
from jobs_finder.domain.job import Job


class SearchLinkedInJobsUseCase:
    """Orchestrates a single job-search call against any `JobSearchPort`."""

    def __init__(self, port: JobSearchPort) -> None:
        self._port = port

    async def execute(self, input: SearchLinkedInInput) -> list[Job]:
        """Run the search and return the port's result unchanged.

        Spec: REQ-012. Exceptions from the port (`JobSearchError` and
        subclasses) propagate to the caller — the use case does not swallow
        them, does not retry, and does not return an empty list on failure.
        """
        return await self._port.search(input.keywords, input.location, input.limit)
