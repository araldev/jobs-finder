"""Unit tests for the InfoJobs use case wiring.

Spec: REQ-J-004.

The InfoJobs use case is a structural twin of the Indeed use case:
it accepts a source-agnostic port, forwards the validated DTO, and
returns the port's result unchanged. The class name and file path
are the only per-source markers — the IMPLEMENTATION is 100%
source-neutral so the grep test below can pin that contract.

The grep test (REQ-J-004) is the spec's hard rule: the source file
`src/jobs_finder/application/usecases/search_infojobs_jobs.py` MUST
NOT contain the string `infojobs` or `InfoJobs` anywhere — not in
docstrings, not in class names, not in comments. The Indeed use
case file has the same contract (REQ-I-005); the InfoJobs file
mirrors it. The asymmetry is deliberate — the InfoJobs use case IS
100% source-agnostic code, so leaking `InfoJobs` into the source
would be a smell that something is wrong.

The DTO `SearchInfoJobsInput` lives in `application/dto.py` (the
DTO is intentionally NOT subject to the grep test — the DTO is the
per-source marker the route handler converts from a Pydantic
schema).
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path

import pytest

from jobs_finder.application.dto import SearchInfoJobsInput
from jobs_finder.application.ports import JobSearchPort
from jobs_finder.application.usecases.search_infojobs_jobs import (
    RawSearchJobsUseCase,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_port(sample_infojobs_jobs: list[Job]) -> FakeJobSearchPort:
    """A `FakeJobSearchPort` primed with the 3 sample InfoJobs jobs (T-001 conftest)."""
    return FakeJobSearchPort(jobs=sample_infojobs_jobs)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


def test_search_infojobs_input_carries_all_fields() -> None:
    """The DTO bundles keywords, location, and limit into a single value."""
    dto = SearchInfoJobsInput(keywords="python", location="madrid", limit=5)
    assert dto.keywords == "python"
    assert dto.location == "madrid"
    assert dto.limit == 5


def test_search_infojobs_input_default_limit_is_20() -> None:
    """REQ-J-004 analog: limit defaults to 20 when omitted."""
    dto = SearchInfoJobsInput(keywords="python", location="madrid")
    assert dto.limit == 20


def test_search_infojobs_input_is_frozen() -> None:
    """The DTO is immutable: assigning to a field raises."""
    dto = SearchInfoJobsInput(keywords="python", location="madrid")
    with pytest.raises((AttributeError, TypeError)):  # frozen dataclass
        dto.keywords = "rust"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Use case — happy path
# ---------------------------------------------------------------------------


async def test_use_case_returns_jobs_from_port_unchanged(
    fake_port: FakeJobSearchPort,
    sample_infojobs_jobs: list[Job],
) -> None:
    """REQ-J-004: use case returns the port's list unchanged (3 sample jobs)."""
    use_case = RawSearchJobsUseCase(port=fake_port)

    result = await use_case.execute(
        SearchInfoJobsInput(keywords="python", location="madrid", limit=20)
    )

    assert result == sample_infojobs_jobs
    assert len(result) == 3


async def test_use_case_forwards_input_fields_to_port() -> None:
    """The use case forwards keywords/location/limit to the port unchanged."""
    port = FakeJobSearchPort(jobs=[])
    use_case = RawSearchJobsUseCase(port=port)

    await use_case.execute(SearchInfoJobsInput(keywords="rust", location="barcelona", limit=7))

    assert port.calls == [("rust", "barcelona", 7)]


async def test_use_case_returns_empty_list_when_port_returns_empty() -> None:
    """An empty result is not failure — the use case does NOT mask it."""
    port = FakeJobSearchPort(jobs=[])
    use_case = RawSearchJobsUseCase(port=port)

    result = await use_case.execute(SearchInfoJobsInput(keywords="nothing", location="nowhere"))

    assert result == []


# ---------------------------------------------------------------------------
# Use case — error propagation
# ---------------------------------------------------------------------------


async def test_use_case_propagates_infojobs_blocked_error() -> None:
    """REQ-J-004: an `InfoJobsBlockedError` from the port propagates unchanged.

    This is the source-specific exception path: the use case does NOT
    catch and re-raise as a generic error, the actual
    `InfoJobsBlockedError` type reaches the caller. The presentation
    layer uses the type to decide between 502 (blocked) and 500
    (anything else).
    """
    from jobs_finder.infrastructure.infojobs.exceptions import (  # noqa: PLC0415
        InfoJobsBlockedError,
    )

    port = FakeJobSearchPort(error=InfoJobsBlockedError("distil challenge"))
    use_case = RawSearchJobsUseCase(port=port)

    with pytest.raises(InfoJobsBlockedError, match="distil challenge"):
        await use_case.execute(SearchInfoJobsInput(keywords="python", location="madrid"))


async def test_use_case_propagates_generic_job_search_error() -> None:
    """A generic `JobSearchError` from the port propagates unchanged."""
    port = FakeJobSearchPort(error=JobSearchError("upstream is down"))
    use_case = RawSearchJobsUseCase(port=port)

    with pytest.raises(JobSearchError, match="upstream is down"):
        await use_case.execute(SearchInfoJobsInput(keywords="python", location="madrid"))


# ---------------------------------------------------------------------------
# Use case — async shape
# ---------------------------------------------------------------------------


def test_use_case_execute_is_coroutine_function(fake_port: FakeJobSearchPort) -> None:
    """`execute` is a coroutine function (awaitable)."""
    use_case = RawSearchJobsUseCase(port=fake_port)
    assert inspect.iscoroutinefunction(use_case.execute) is True


# ---------------------------------------------------------------------------
# Port conformance
# ---------------------------------------------------------------------------


def test_fake_port_satisfies_job_search_port_structurally(
    fake_port: FakeJobSearchPort,
) -> None:
    """The fake exposes an async `search`, satisfying the structural Protocol."""
    assert callable(getattr(fake_port, "search", None))
    assert inspect.iscoroutinefunction(fake_port.search)
    # The port attribute is in the protocol's `__protocol_attrs__`.
    protocol_attrs: set[str] = getattr(JobSearchPort, "__protocol_attrs__", set())
    assert "search" in protocol_attrs


# ---------------------------------------------------------------------------
# REQ-J-004 — source neutrality (CRITICAL)
# ---------------------------------------------------------------------------


_USE_CASE_SOURCE = Path("src/jobs_finder/application/usecases/search_infojobs_jobs.py")


def test_use_case_source_contains_no_infojobs_identifier() -> None:
    """REQ-J-004 (CRITICAL): `search_infojobs_jobs.py` contains no `infojobs` or `InfoJobs`.

    The grep is on the FILE CONTENTS — the file PATH may contain
    `infojobs` (the path is the per-source binding for FastAPI), but
    the source code itself must be 100% source-agnostic. The class
    name, docstrings, comments, and identifiers must not leak
    `InfoJobs` anywhere.
    """
    assert _USE_CASE_SOURCE.exists(), f"{_USE_CASE_SOURCE} must exist"
    text = _USE_CASE_SOURCE.read_text(encoding="utf-8")
    matches = re.findall(r"infojobs|InfoJobs", text)
    assert not matches, (
        f"{_USE_CASE_SOURCE} must contain no 'infojobs' or 'InfoJobs' (found: {matches!r})"
    )


def test_use_case_source_passes_shell_grep() -> None:
    """REQ-J-004 (CRITICAL): `grep -E 'infojobs|InfoJobs' <file>` exits non-zero.

    Runs the actual shell command, not a Python re, to mirror the
    spec's literal assertion. The grep exit code is 1 when there
    are no matches and 0 when there is at least one match.
    """
    result = subprocess.run(
        ["grep", "-E", "infojobs|InfoJobs", str(_USE_CASE_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"grep -E 'infojobs|InfoJobs' {_USE_CASE_SOURCE} returned 0 (matches found): "
        f"{result.stdout!r}"
    )
    assert result.stdout == "", f"grep stdout must be empty: {result.stdout!r}"


# ---------------------------------------------------------------------------
# Dependency rule (REQ: application MUST NOT import infrastructure)
# ---------------------------------------------------------------------------


def test_use_case_does_not_import_infrastructure() -> None:
    """`search_infojobs_jobs.py` does not import from `infrastructure` or `presentation`.

    The InfoJobs use case is the application boundary. Pinned at the
    AST level so docstrings/comments cannot trip the check.
    """
    import ast  # noqa: PLC0415

    assert _USE_CASE_SOURCE.exists()
    tree = ast.parse(_USE_CASE_SOURCE.read_text(encoding="utf-8"), filename=str(_USE_CASE_SOURCE))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "infrastructure" not in joined, f"{_USE_CASE_SOURCE} imports infrastructure"
    assert "presentation" not in joined, f"{_USE_CASE_SOURCE} imports presentation"
    assert "playwright" not in joined, f"{_USE_CASE_SOURCE} imports playwright"
    assert "fastapi" not in joined, f"{_USE_CASE_SOURCE} imports fastapi"


# ---------------------------------------------------------------------------
# Module shape
# ---------------------------------------------------------------------------


def test_use_case_module_exports_search_jobs_use_case() -> None:
    """The module exports the source-neutral `SearchJobsUseCase` class.

    The class name is intentionally NOT `SearchInfoJobsJobsUseCase`
    because the file must be 100% source-agnostic (REQ-J-004). The
    file PATH provides the per-source binding (`search_infojobs_jobs.py`)
    for FastAPI dependency injection; the class itself is generic
    and could be reused for any future source.
    """
    import jobs_finder.application.usecases.search_infojobs_jobs as mod  # noqa: PLC0415

    assert hasattr(mod, "SearchJobsUseCase")
    assert inspect.isclass(mod.SearchJobsUseCase)
