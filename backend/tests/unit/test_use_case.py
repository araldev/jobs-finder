"""Unit tests for the application layer.

Spec: REQ-008, REQ-009, REQ-010, REQ-011, REQ-012.
Design: `application/` defines the `JobSearchPort` Protocol, the
`SearchLinkedInInput` DTO, and the `RawLinkedInJobsUseCase` (renamed
from the original `SearchLinkedInJobsUseCase` in the `cache-ttl`
change — the public LinkedIn use case is now a re-export of
`CachedJobSearchUseCase`). The raw use case trusts the input is
already validated by the presentation layer.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime

import pytest

from jobs_finder.application.dto import SearchLinkedInInput
from jobs_finder.application.ports import JobSearchPort
from jobs_finder.application.usecases.search_linkedin_jobs import (
    RawLinkedInJobsUseCase,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job

# ---------------------------------------------------------------------------
# Fakes (the only acceptable "mocks" per design — see test design rules)
# ---------------------------------------------------------------------------


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort`.

    Records every call to `search` so tests can assert the use case forwarded
    the input correctly. Can be primed to return a fixed list, raise a fixed
    exception, or both (exception wins).
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        self.calls.append((keywords, location, limit))
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _sample_job(idx: int = 1) -> Job:
    return Job(
        id=str(idx),
        title=f"Title {idx}",
        company=f"Company {idx}",
        location="Madrid",
        url=f"https://www.linkedin.com/jobs/view/{idx}/",
        posted_at=datetime(2026, 1, idx, tzinfo=UTC),
        source="linkedin",
    )


# ---------------------------------------------------------------------------
# Port shape
# ---------------------------------------------------------------------------


def test_job_search_port_is_a_protocol() -> None:
    """REQ-008: `JobSearchPort` is a `typing.Protocol` declaring `search`."""
    assert getattr(JobSearchPort, "_is_protocol", None) is True
    protocol_attrs: set[str] = getattr(JobSearchPort, "__protocol_attrs__", set())
    assert "search" in protocol_attrs


def test_fake_satisfies_job_search_port_protocol_structurally() -> None:
    """Structural conformance: the fake has an async `search` member.

    `typing.Protocol` is structural — `isinstance(fake, JobSearchPort)` only
    returns True if the port is decorated with `@runtime_checkable`. We
    instead check the attribute directly.
    """
    fake = FakeJobSearchPort(jobs=[_sample_job()])
    assert callable(getattr(fake, "search", None))
    assert inspect.iscoroutinefunction(fake.search)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


def test_search_linkedin_input_carries_all_fields() -> None:
    """The DTO bundles keywords, location, and limit into a single value."""
    dto = SearchLinkedInInput(keywords="python", location="madrid", limit=5)
    assert dto.keywords == "python"
    assert dto.location == "madrid"
    assert dto.limit == 5


def test_search_linkedin_input_default_limit_is_20() -> None:
    """REQ-009: limit defaults to 20 when omitted."""
    dto = SearchLinkedInInput(keywords="python", location="madrid")
    assert dto.limit == 20


# ---------------------------------------------------------------------------
# Use case — happy path
# ---------------------------------------------------------------------------


async def test_use_case_returns_jobs_from_port_unchanged() -> None:
    """REQ-010: use case returns the port's list unchanged."""
    jobs = [_sample_job(1), _sample_job(2), _sample_job(3)]
    port = FakeJobSearchPort(jobs=jobs)
    use_case = RawLinkedInJobsUseCase(port=port)

    result = await use_case.execute(
        SearchLinkedInInput(keywords="python", location="madrid", limit=20)
    )

    assert result == jobs
    assert len(result) == 3


async def test_use_case_forwards_input_fields_to_port() -> None:
    """The use case forwards keywords/location/limit to the port unchanged."""
    port = FakeJobSearchPort(jobs=[])
    use_case = RawLinkedInJobsUseCase(port=port)

    await use_case.execute(SearchLinkedInInput(keywords="rust", location="barcelona", limit=7))

    assert port.calls == [("rust", "barcelona", 7)]


async def test_use_case_returns_empty_list_when_port_returns_empty() -> None:
    """An empty result is not failure — the use case does NOT mask it."""
    port = FakeJobSearchPort(jobs=[])
    use_case = RawLinkedInJobsUseCase(port=port)

    result = await use_case.execute(SearchLinkedInInput(keywords="nothing", location="nowhere"))

    assert result == []


# ---------------------------------------------------------------------------
# Use case — error propagation (REQ-012)
# ---------------------------------------------------------------------------


async def test_use_case_propagates_job_search_error() -> None:
    """A `JobSearchError` from the port propagates unchanged."""
    port = FakeJobSearchPort(error=JobSearchError("upstream is down"))
    use_case = RawLinkedInJobsUseCase(port=port)

    with pytest.raises(JobSearchError, match="upstream is down"):
        await use_case.execute(SearchLinkedInInput(keywords="python", location="madrid"))


async def test_use_case_propagates_subclass_of_job_search_error() -> None:
    """A subclass of `JobSearchError` propagates as its actual type (REQ-012)."""

    class CustomBlockedError(JobSearchError):
        pass

    port = FakeJobSearchPort(error=CustomBlockedError("auth wall"))
    use_case = RawLinkedInJobsUseCase(port=port)

    with pytest.raises(CustomBlockedError, match="auth wall"):
        await use_case.execute(SearchLinkedInInput(keywords="python", location="madrid"))


# ---------------------------------------------------------------------------
# Use case — async shape (REQ-011)
# ---------------------------------------------------------------------------


def test_use_case_execute_is_coroutine_function() -> None:
    """REQ-011: `execute` is a coroutine function (awaitable)."""
    use_case = RawLinkedInJobsUseCase(port=FakeJobSearchPort())
    assert inspect.iscoroutinefunction(use_case.execute) is True


# ---------------------------------------------------------------------------
# Dependency rule (REQ-008: application MUST NOT import infrastructure)
# ---------------------------------------------------------------------------


def test_application_does_not_import_infra_or_presentation() -> None:
    """REQs: application has no infrastructure or presentation imports.

    Pinned at the AST level so docstrings/comments cannot trip the check.
    """
    for path in (
        "src/jobs_finder/application/ports.py",
        "src/jobs_finder/application/dto.py",
        "src/jobs_finder/application/usecases/search_linkedin_jobs.py",
    ):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        joined = " ".join(imported)
        assert "infrastructure" not in joined, f"{path} imports infrastructure"
        assert "presentation" not in joined, f"{path} imports presentation"
        assert "playwright" not in joined, f"{path} imports playwright"
        assert "fastapi" not in joined, f"{path} imports fastapi"


def test_use_case_source_has_no_source_specific_parsing() -> None:
    """REQ-010: the use case contains no source-specific parsing primitives.

    The use case must remain source-agnostic so the same code can drive an
    InfoJobs port later. Docstrings and identifiers may name the source
    (the use case is, after all, *for* LinkedIn); the rule is about CODE,
    not documentation. We strip docstrings/strings via AST before scanning.
    """
    with open(
        "src/jobs_finder/application/usecases/search_linkedin_jobs.py",
        encoding="utf-8",
    ) as fh:
        source = fh.read()
    tree = ast.parse(source)
    # Erase all string literals and docstrings so identifier/doc-only mentions
    # of "linkedin" are not flagged; the rule targets code paths.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    cleaned = ast.unparse(tree)
    lowered = cleaned.lower()
    assert "playwright" not in lowered
    assert "chromium" not in lowered
    assert "beautifulsoup" not in lowered
    assert "bs4" not in lowered
    # No LinkedIn-specific selectors in code.
    assert "data-entity-urn" not in cleaned
    # No HTML literal in code (docstrings already stripped).
    assert "<div" not in lowered
    assert "<a " not in lowered
