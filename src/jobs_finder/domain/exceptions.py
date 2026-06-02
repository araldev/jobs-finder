"""Base exceptions for the domain layer.

`DomainError` is the root of every domain-level exception. `JobSearchError`
is the immediate parent of every source-specific scraper exception (LinkedIn,
InfoJobs, future sources). Keeping a stable parent at the domain boundary lets
the application and presentation layers catch a single type while still
preserving the specific subclass for diagnostics.
"""

from __future__ import annotations


class DomainError(Exception):
    """Root of the domain exception hierarchy."""


class JobSearchError(DomainError):
    """Base for any job-search source (LinkedIn, InfoJobs, ...) failure.

    Catching this in the presentation layer maps to 502 — the source is
    unreachable, blocked, or returned an unparseable payload.
    """
