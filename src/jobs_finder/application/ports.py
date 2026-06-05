"""Outbound ports: the application layer's contracts with any job-search
source (LinkedIn, Indeed, InfoJobs, ...) and with any TTL cache
(in-memory v1, future Redis / Memcached).

Spec: REQ-008 (search port), REQ-C-001 (cache port), REQ-C-005
(per-source key isolation).
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, TypeVar

from jobs_finder.domain.job import Job

K_co = TypeVar("K_co", contravariant=True)  # noqa: PLC0105
V = TypeVar("V")


class JobSearchPort(Protocol):
    """A job-search source. Implementations live in `infrastructure/`.

    The default value on `limit` is duplicated in the Pydantic schema at the
    presentation boundary; the application trusts the caller to pass an
    already-validated value.
    """

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        """Search the source for jobs matching the criteria."""
        ...


class CachePort(Protocol[K_co, V]):
    """A typed key/value cache with TTL semantics.

    Implementations MUST be safe for concurrent use in a single
    process. Cross-process / cross-host caching is out of scope
    for v1 (the `cache-ttl` change ships an in-memory
    implementation only; the Protocol is the seam that lets a
    future change swap in Redis / Memcached without touching the
    application layer).
    """

    async def get(self, key: K_co) -> V | None:
        """Return the stored value if not expired, else `None`."""
        ...

    async def set(self, key: K_co, value: V) -> None:
        """Store the value with the configured TTL. Overwrites prior."""
        ...

    async def delete(self, key: K_co) -> None:
        """Remove the key (no-op if absent)."""
        ...

    async def clear(self) -> None:
        """Remove all keys. Used by tests; not exposed in production."""
        ...


class JobSearchCacheKey(NamedTuple):
    """The cache key tuple for the 3 source use cases.

    The `source` field is a string literal in
    `{"linkedin", "indeed", "infojobs"}` so a query on
    `/jobs/linkedin?keywords=python&location=madrid` does NOT
    share a cache entry with the same query on `/jobs/indeed`
    (REQ-C-005 — per-source isolation).

    Tuple equality and hashing are exact for `NamedTuple`, so
    there is no key collision risk.
    """

    source: str
    keywords: str
    location: str
    limit: int
