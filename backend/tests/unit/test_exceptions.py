"""Unit tests for the LinkedIn-specific exception hierarchy.

Spec: REQ-016.

The exception classes themselves are landed across T-005 (parse) and T-006
(blocked, timeout); T-007 covers the hierarchy with tests only. Each
subclass must:
    - Inherit from `JobSearchError` (and therefore `DomainError`).
    - Be instantiable with a message and an optional `details` dict.
    - Provide a useful `__str__` representation.
"""

from __future__ import annotations

from typing import Any

import pytest

from jobs_finder.domain.exceptions import (
    AllSourcesFailedError,
    DomainError,
    JobSearchError,
)
from jobs_finder.infrastructure.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInParseError,
    LinkedInTimeoutError,
)

# All three subclasses share the same constructor signature:
# `(message: str, details: dict[str, Any] | None = None)`. The test
# parametrize uses `Any` for the class type to bypass mypy's nominal
# typing — the tests themselves pin the contract.
ALL_EXCEPTIONS: list[type[JobSearchError]] = [
    LinkedInBlockedError,
    LinkedInParseError,
    LinkedInTimeoutError,
]


# ---------------------------------------------------------------------------
# Class hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_subclasses_job_search_error(cls: Any) -> None:
    """Every LinkedIn exception is a JobSearchError (and therefore a DomainError)."""
    assert issubclass(cls, JobSearchError)
    assert issubclass(cls, DomainError)
    assert issubclass(cls, Exception)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_instantiable_with_message_only(cls: Any) -> None:
    """Each exception is constructible with a bare message."""
    exc = cls("boom")
    assert exc.args == ("boom",)
    assert exc.details is None


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_instantiable_with_details(cls: Any) -> None:
    """Each exception carries an optional `details` dict for diagnostics."""
    details = {"url": "https://www.linkedin.com/jobs/search/?keywords=python"}
    exc = cls("boom", details=details)
    assert exc.args == ("boom",)
    assert exc.details == details


# ---------------------------------------------------------------------------
# __str__ shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_str_includes_message(cls: Any) -> None:
    """`str(exc)` includes the original message."""
    exc = cls("rate limit hit")
    assert "rate limit hit" in str(exc)


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_str_includes_details_when_present(cls: Any) -> None:
    """When `details` is set, `str(exc)` includes the payload."""
    exc = cls("boom", details={"card_html": "<li>...</li>"})
    rendered = str(exc)
    assert "boom" in rendered
    assert "<li>...</li>" in rendered


# ---------------------------------------------------------------------------
# Catchability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_linkedin_exception_is_catchable_as_job_search_error(cls: Any) -> None:
    """Each subclass can be caught via the JobSearchError base class."""
    with pytest.raises(JobSearchError, match="caught-as-base"):
        raise cls("caught-as-base")


def test_distinct_subclasses_are_not_interchangeable() -> None:
    """A `LinkedInBlockedError` is NOT a `LinkedInTimeoutError`."""
    assert not issubclass(LinkedInBlockedError, LinkedInTimeoutError)
    assert not issubclass(LinkedInTimeoutError, LinkedInBlockedError)
    assert not issubclass(LinkedInParseError, LinkedInBlockedError)


# ---------------------------------------------------------------------------
# `AllSourcesFailedError` (REQ-DEFENSIVE-001, T-005)
#
# A new `JobSearchError` subclass raised by the aggregator when
# the 3 per-source use cases ALL fail. The registered
# `JobSearchError` handler maps it to HTTP 502 (the same as
# every other `JobSearchError`).
# ---------------------------------------------------------------------------


def test_all_sources_failed_error_subclasses_job_search_error() -> None:
    """`AllSourcesFailedError` is a `JobSearchError` (and `DomainError`)."""
    assert issubclass(AllSourcesFailedError, JobSearchError)
    assert issubclass(AllSourcesFailedError, DomainError)
    assert issubclass(AllSourcesFailedError, Exception)


def test_all_sources_failed_error_is_instantiable() -> None:
    """`AllSourcesFailedError("all sources failed")` constructs with a message."""
    exc = AllSourcesFailedError("all sources failed")
    assert exc.args == ("all sources failed",)
    assert "all sources failed" in str(exc)


def test_all_sources_failed_error_is_catchable_as_job_search_error() -> None:
    """`AllSourcesFailedError` is catchable via the `JobSearchError` base class."""
    with pytest.raises(JobSearchError, match="caught-as-base"):
        raise AllSourcesFailedError("caught-as-base")
