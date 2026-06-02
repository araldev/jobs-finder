"""Unit tests for the Indeed-specific exception hierarchy.

Spec: REQ-I-010.

Each subclass must:
    - Inherit from `JobSearchError` (and therefore `DomainError`).
    - Be instantiable with a message and an optional `details` dict.
    - Provide a useful `__str__` representation.

Mirrors the LinkedIn `test_exceptions.py` test layout: one parametrize
over the three subclasses for the hierarchy / instantiation / `__str__`
/ catchability checks, plus a few distinct-subclass checks at the
bottom.
"""

from __future__ import annotations

from typing import Any

import pytest

from jobs_finder.domain.exceptions import DomainError, JobSearchError
from jobs_finder.infrastructure.indeed.exceptions import (
    IndeedBlockedError,
    IndeedParseError,
    IndeedTimeoutError,
)

# All three subclasses share the same constructor signature:
# `(message: str, details: dict[str, Any] | None = None)`. The test
# parametrize uses `Any` for the class type to bypass mypy's nominal
# typing — the tests themselves pin the contract.
ALL_EXCEPTIONS: list[type[JobSearchError]] = [
    IndeedBlockedError,
    IndeedParseError,
    IndeedTimeoutError,
]


# ---------------------------------------------------------------------------
# Class hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_subclasses_job_search_error(cls: Any) -> None:
    """Every Indeed exception is a JobSearchError (and therefore a DomainError)."""
    assert issubclass(cls, JobSearchError)
    assert issubclass(cls, DomainError)
    assert issubclass(cls, Exception)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_instantiable_with_message_only(cls: Any) -> None:
    """Each exception is constructible with a bare message."""
    exc = cls("boom")
    assert exc.args == ("boom",)
    assert exc.details is None


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_instantiable_with_details(cls: Any) -> None:
    """Each exception carries an optional `details` dict for diagnostics."""
    details = {"url": "https://es.indeed.com/jobs?q=python&l=madrid"}
    exc = cls("boom", details=details)
    assert exc.args == ("boom",)
    assert exc.details == details


# ---------------------------------------------------------------------------
# __str__ shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_str_includes_message(cls: Any) -> None:
    """`str(exc)` includes the original message."""
    exc = cls("rate limit hit")
    assert "rate limit hit" in str(exc)


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_str_includes_details_when_present(cls: Any) -> None:
    """When `details` is set, `str(exc)` includes the payload."""
    exc = cls("boom", details={"card_html": "<li>...</li>"})
    rendered = str(exc)
    assert "boom" in rendered
    assert "<li>...</li>" in rendered


# ---------------------------------------------------------------------------
# Catchability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_EXCEPTIONS)
def test_indeed_exception_is_catchable_as_job_search_error(cls: Any) -> None:
    """Each subclass can be caught via the JobSearchError base class."""
    with pytest.raises(JobSearchError, match="caught-as-base"):
        raise cls("caught-as-base")


def test_distinct_subclasses_are_not_interchangeable() -> None:
    """An `IndeedBlockedError` is NOT an `IndeedTimeoutError`."""
    assert not issubclass(IndeedBlockedError, IndeedTimeoutError)
    assert not issubclass(IndeedTimeoutError, IndeedBlockedError)
    assert not issubclass(IndeedParseError, IndeedBlockedError)
