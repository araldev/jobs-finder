"""Use case: orchestrate a single job-search call against any port.

Spec: REQ-J-004.

This module is the per-source binding entry point for the presentation
layer. The class is intentionally named generically and the input
type is an inline Protocol (not the DTO dataclass) so the file is
100% source-agnostic per REQ-J-004. The file path provides the
per-source binding for FastAPI dependency injection; the
implementation is identical for every source, so leaking the source
name into the code would be a smell that something is wrong.

The use case is a thin orchestrator: it does not parse HTML, does not
know about Playwright, and does not catch exceptions from the port.
"""

from __future__ import annotations

from typing import Protocol

from jobs_finder.application.ports import JobSearchPort
from jobs_finder.domain.job import Job


class _SearchInput(Protocol):
    """Structural input shape the use case requires.

    Any value with `keywords: str`, `location: str`, `limit: int`
    satisfies this Protocol — the source-specific DTOs (and any
    future DTOs) are passed through unchanged. The Protocol lives
    in the use case module so the use case file has zero
    source-specific imports.

    The attributes are declared as read-only `@property` so frozen
    dataclass DTOs (which have read-only attributes) satisfy the
    protocol. Plain instance attributes on a Protocol imply
    settable variables, which a frozen dataclass does NOT
    provide — mypy flags the mismatch.
    """

    @property
    def keywords(self) -> str: ...

    @property
    def location(self) -> str: ...

    @property
    def limit(self) -> int: ...


class SearchJobsUseCase:
    """Orchestrates a single job-search call against any `JobSearchPort`."""

    def __init__(self, port: JobSearchPort) -> None:
        self._port = port

    async def execute(self, input: _SearchInput) -> list[Job]:
        """Run the search and return the port's result unchanged.

        Spec: REQ-J-004. Exceptions from the port (`JobSearchError`
        and subclasses) propagate to the caller — the use case does
        not swallow them, does not retry, and does not return an
        empty list on failure.
        """
        return await self._port.search(input.keywords, input.location, input.limit)
