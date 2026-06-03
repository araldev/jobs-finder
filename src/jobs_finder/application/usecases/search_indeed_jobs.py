"""Use case: orchestrate a single job-search call against any port.

Spec: REQ-I-004, REQ-I-005, REQ-C-001..REQ-C-006.

This module is the per-source binding entry point for the presentation
layer. The class is intentionally named generically and the input
type is an inline Protocol (not the DTO dataclass) so the file is
100% source-agnostic per REQ-I-005. The file path provides the
per-source binding for FastAPI dependency injection; the
implementation is identical for every source, so leaking the source
name into the code would be a smell that something is wrong.

The use case is a thin orchestrator: it does not parse HTML, does not
know about Playwright, and does not catch exceptions from the port.

T-004 (cache-ttl): the public `SearchJobsUseCase` is now a
re-export of `CachedJobSearchUseCase` (the cached wrapper). The
raw orchestrator is exposed as `RawSearchJobsUseCase` for tests
that exercise the unwrapped implementation. The cached wrapper
exposes `search(keywords, location, limit) -> SearchResult`; the
raw use case exposes `execute(input) -> list[Job]`.
"""

from __future__ import annotations

from typing import Protocol

from jobs_finder.application.ports import JobSearchPort
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
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


class RawSearchJobsUseCase:
    """Orchestrates a single job-search call against any `JobSearchPort`.

    Renamed from the original `SearchJobsUseCase` in the
    `cache-ttl` change (T-004). The public `SearchJobsUseCase`
    (re-exported below) is the cached wrapper. This class is the
    raw orchestrator that the cached wrapper composes as its
    inner port.
    """

    def __init__(self, port: JobSearchPort) -> None:
        self._port = port

    async def execute(self, input: _SearchInput) -> list[Job]:
        """Run the search and return the port's result unchanged.

        Spec: REQ-I-004. Exceptions from the port (`JobSearchError`
        and subclasses) propagate to the caller — the use case does
        not swallow them, does not retry, and does not return an
        empty list on failure.
        """
        return await self._port.search(input.keywords, input.location, input.limit)

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        """Structural `JobSearchPort` shim.

        `CachedJobSearchUseCase` is typed against `JobSearchPort`,
        whose `search` method is the seam. Exposing `search` on
        the raw use case lets the cached wrapper compose the raw
        use case as its inner port. The body forwards to
        `execute` via a duck-typed input object so the existing
        DTO path is unchanged.
        """
        return await self.execute(_InlineInput(keywords, location, limit))


class _InlineInput:
    """Duck-typed `_SearchInput` for the `search` shim.

    Implements the `keywords` / `location` / `limit` read-only
    attributes the use case's `execute` consumes. Used only by
    the `search` shim — production callers go through the DTO.
    """

    __slots__ = ("keywords", "location", "limit")

    def __init__(self, keywords: str, location: str, limit: int) -> None:
        self.keywords = keywords
        self.location = location
        self.limit = limit


# Public re-export. `SearchJobsUseCase` is the cached wrapper
# (`CachedJobSearchUseCase`) so existing imports resolve to the
# type the route consumes. Tests that need the raw orchestrator
# should import `RawSearchJobsUseCase` directly.
SearchJobsUseCase = CachedJobSearchUseCase
