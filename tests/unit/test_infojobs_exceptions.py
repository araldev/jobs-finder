"""Unit tests for the InfoJobs-specific exception hierarchy.

Spec: REQ-J-001..J-006 (partial — exceptions are a building block, not
a user-facing requirement on their own; the consuming scraper code
lands in T-006). The full set of linked requirements is enumerated
in `tests/integration/test_infojobs_api.py` when the route is wired.

Each subclass must:
    - Inherit from `JobSearchError` (and therefore `DomainError`).
    - Be instantiable with a message and an optional `details` dict.
    - Provide a useful `__str__` representation.

Mirrors the Indeed `test_indeed_exceptions.py` test layout: one
parametrize over the three subclasses for the hierarchy /
instantiation / `__str__` / catchability checks, plus a few
distinct-subclass checks at the bottom. The InfoJobs block detector
is stricter than Cloudflare (Distil + Geetest), so the
`InfoJobsBlockedError` docstring explicitly calls out those signals.
"""

from __future__ import annotations

from typing import Any

import pytest

from jobs_finder.domain.exceptions import DomainError, JobSearchError
from jobs_finder.infrastructure.infojobs.exceptions import (
    InfoJobsBlockedError,
    InfoJobsParseError,
    InfoJobsTimeoutError,
)

# All three subclasses share the same constructor signature:
# `(message: str, details: dict[str, Any] | None = None)`. The test
# parametrize uses `Any` for the class type to bypass mypy's nominal
# typing — the tests themselves pin the contract.
ALL_EXCEPTIONS: list[type[JobSearchError]] = [
    InfoJobsBlockedError,
    InfoJobsParseError,
    InfoJobsTimeoutError,
]


# ---------------------------------------------------------------------------
# Class hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_subclasses_job_search_error(cls: Any) -> None:
    """Every InfoJobs exception is a JobSearchError (and therefore a DomainError)."""
    assert issubclass(cls, JobSearchError)
    assert issubclass(cls, DomainError)
    assert issubclass(cls, Exception)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_instantiable_with_message_only(cls: Any) -> None:
    """Each exception is constructible with a bare message."""
    exc = cls("boom")
    assert exc.args == ("boom",)
    assert exc.details is None


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_instantiable_with_details(cls: Any) -> None:
    """Each exception carries an optional `details` dict for diagnostics."""
    details = {"url": "https://www.infojobs.net/ofertas-trabajo?q=python&l=madrid"}
    exc = cls("boom", details=details)
    assert exc.args == ("boom",)
    assert exc.details == details


# ---------------------------------------------------------------------------
# __str__ shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_str_includes_message(cls: Any) -> None:
    """`str(exc)` includes the original message."""
    exc = cls("distil challenge")
    assert "distil challenge" in str(exc)


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_str_includes_details_when_present(cls: Any) -> None:
    """When `details` is set, `str(exc)` includes the payload."""
    exc = cls("boom", details={"card_html": "<li>...</li>"})
    rendered = str(exc)
    assert "boom" in rendered
    assert "<li>...</li>" in rendered


# ---------------------------------------------------------------------------
# Catchability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_infojobs_exception_is_catchable_as_job_search_error(cls: Any) -> None:
    """Each subclass can be caught via the JobSearchError base class."""
    with pytest.raises(JobSearchError, match="caught-as-base"):
        raise cls("caught-as-base")


def test_distinct_subclasses_are_not_interchangeable() -> None:
    """An `InfoJobsBlockedError` is NOT an `InfoJobsTimeoutError`."""
    assert not issubclass(InfoJobsBlockedError, InfoJobsTimeoutError)
    assert not issubclass(InfoJobsTimeoutError, InfoJobsBlockedError)
    assert not issubclass(InfoJobsParseError, InfoJobsBlockedError)
