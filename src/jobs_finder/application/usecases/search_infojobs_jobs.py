"""Use case: orchestrate a single job-search call against any port.

Spec: REQ-J-004, REQ-C-001..REQ-C-006.

This module is the per-source binding entry point for the presentation
layer. The class is intentionally named generically and the input
type is an inline Protocol (not the DTO dataclass) so the file is
100% source-agnostic per REQ-J-004. The file path provides the
per-source binding for FastAPI dependency injection; the
implementation is identical for every source, so leaking the source
name into the code would be a smell that something is wrong.

The use case is a thin orchestrator: it does not parse HTML, does not
know about Playwright, and does not catch exceptions from the port.

T-004 (cache-ttl): the public `SearchJobsUseCase` is now a
re-export of `CachedJobSearchUseCase` (the cached wrapper). The
raw orchestrator is exposed as `RawSearchJobsUseCase` for tests
that exercise the unwrapped implementation.
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

    The optional `geo_id: int | None` (added in
    `fix-linkedin-geoid`) is the LinkedIn-specific numeric
    `geoId`; the other per-source ports ignore it. The attribute
    is optional so pre-WU3 DTOs (which don't have the field)
    still satisfy the protocol.
    """

    @property
    def keywords(self) -> str: ...

    @property
    def location(self) -> str: ...

    @property
    def limit(self) -> int: ...

    @property
    def geo_id(self) -> int | None: ...


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

        Spec: REQ-J-004. Exceptions from the port (`JobSearchError`
        and subclasses) propagate to the caller — the use case does
        not swallow them, does not retry, and does not return an
        empty list on failure.

        The `input.geo_id` (optional, defaults to `None`) is
        forwarded to the port. The other per-source ports ignore
        the kwarg; the LinkedIn port uses it in the URL formula.
        """
        return await self._port.search(
            input.keywords, input.location, input.limit, geo_id=input.geo_id
        )

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        """Structural `JobSearchPort` shim.

        `CachedJobSearchUseCase` is typed against `JobSearchPort`,
        whose `search` method is the seam. Exposing `search` on
        the raw use case lets the cached wrapper compose the raw
        use case as its inner port. The body forwards to
        `execute` via a duck-typed input object so the existing
        DTO path is unchanged.

        The 4th `geo_id: int | None = None` kwarg (added in
        WU3) is forwarded via the `_InlineInput` shim's
        `geo_id` field. The other per-source ports ignore it.
        """
        return await self.execute(_InlineInput(keywords, location, limit, geo_id))


class _InlineInput:
    """Duck-typed `_SearchInput` for the `search` shim.

    Implements the `keywords` / `location` / `limit` /
    `geo_id` read-only attributes the use case's `execute`
    consumes. Used only by the `search` shim — production
    callers go through the DTO.
    """

    __slots__ = ("geo_id", "keywords", "limit", "location")

    def __init__(self, keywords: str, location: str, limit: int, geo_id: int | None = None) -> None:
        self.keywords = keywords
        self.location = location
        self.limit = limit
        self.geo_id = geo_id


# Public re-export. `SearchJobsUseCase` is the cached wrapper
# (`CachedJobSearchUseCase`) so existing imports resolve to the
# type the route consumes. Tests that need the raw orchestrator
# should import `RawSearchJobsUseCase` directly.
SearchJobsUseCase = CachedJobSearchUseCase
