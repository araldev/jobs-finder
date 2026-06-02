# Test fixtures and shared configuration for the jobs-finder test suite.
#
# The conftest grows as the project grows. The T-001 batch of the
# `indeed_platform` change adds two shared fixtures here so future
# batches (T-005 onward) can consume them without redefining the same
# fake port + sample jobs in every test file:
#
#   - `sample_indeed_jobs`: 3 deterministic, source-agnostic `Job`
#     instances with Indeed-style canonical viewjob URLs.
#   - `fake_indeed_port`: an in-memory `FakeJobSearchPort` primed with
#     `sample_indeed_jobs`; structural-conformant with the
#     `JobSearchPort` Protocol (cite REQ-I-003 / REQ-I-005).
#   - `FakeJobSearchPort` class: shared by both fixtures and by any
#     future test that wants to construct a fresh port instance.
#   - `app` (T-007): a FastAPI app whose ALL THREE use cases
#     (LinkedIn + Indeed + InfoJobs) are wired to fake ports, so
#     each per-source integration test can drive its route against
#     a `FakeJobSearchPort` without launching Chromium. The LinkedIn
#     port is fresh + empty so the existing LinkedIn integration
#     tests (which define their own `app` fixture locally) are not
#     affected.
#
# The prior `linkedin-endpoint` change defined its `FakeJobSearchPort`
# and sample `Job` factories inline in each test file. The Indeed
# path starts with a conftest-level definition so the duplication
# stays bounded as more tests are added.

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from jobs_finder.application.usecases.search_indeed_jobs import (
    SearchJobsUseCase as IndeedSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_infojobs_jobs import (
    SearchJobsUseCase as InfoJobsSearchJobsUseCase,
)
from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.presentation.app_factory import build_app


class FakeJobSearchPort:
    """In-memory fake of `JobSearchPort` for tests.

    Records every call so tests can assert the route/use case forwarded
    the input correctly. Can be primed (or mutated) to raise an
    exception on the next call. Cite REQ-I-005.

    NOTE: a structurally-identical `FakeJobSearchPort` is defined
    inline in `tests/integration/test_api.py` (the LinkedIn
    integration test). Keeping the duplication is intentional: the
    LinkedIn file pre-dates the conftest fixture and refactoring it
    is out of scope for the `indeed_platform` change. When a future
    change consolidates the integration tests, the two definitions
    should collapse into the one in this module.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        self.calls.append((keywords, location, limit))
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _make_indeed_sample_jobs() -> list[Job]:
    """Build 3 deterministic, Indeed-style `Job` instances.

    The ids are 9-digit numbers mirroring Indeed's `data-jk` shape.
    Each URL is the canonical `https://es.indeed.com/viewjob?jk=<id>`
    form (not a SERP `/rc/clk` or `vjk=`-pinned URL). `posted_at` is
    tz-aware UTC to satisfy the `Job.__post_init__` invariant.
    """
    return [
        Job(
            id="100000001",
            title="Indeed Title 1",
            company="Indeed Co 1",
            location="Madrid, Spain",
            url="https://es.indeed.com/viewjob?jk=100000001",
            posted_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
        Job(
            id="100000002",
            title="Indeed Title 2",
            company="Indeed Co 2",
            location="Barcelona, Spain",
            url="https://es.indeed.com/viewjob?jk=100000002",
            posted_at=datetime(2026, 5, 2, tzinfo=UTC),
        ),
        Job(
            id="100000003",
            title="Indeed Title 3",
            company="Indeed Co 3",
            location="Valencia, Spain",
            url="https://es.indeed.com/viewjob?jk=100000003",
            posted_at=datetime(2026, 5, 3, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def sample_indeed_jobs() -> list[Job]:
    """3 deterministic, source-agnostic `Job` instances shaped for Indeed tests.

    Each job has the canonical `https://es.indeed.com/viewjob?jk=<id>`
    URL. The 3 jobs have unique ids, titles, companies, and locations so
    tests that assert field-by-field can identify which one they're
    looking at.
    """
    return _make_indeed_sample_jobs()


@pytest.fixture
def fake_indeed_port(sample_indeed_jobs: list[Job]) -> FakeJobSearchPort:
    """An in-memory `FakeJobSearchPort` primed with `sample_indeed_jobs`.

    Returns a fresh port per test. The port records every call so tests
    can assert the route/use case forwarded the input correctly.
    """
    return FakeJobSearchPort(jobs=sample_indeed_jobs)


@pytest.fixture
def app(
    fake_indeed_port: FakeJobSearchPort,
    fake_infojobs_port: FakeJobSearchPort,
) -> FastAPI:
    """A FastAPI app whose ALL THREE use cases are wired to fake ports.

    The LinkedIn use case is wrapped around a fresh
    `FakeJobSearchPort` with NO jobs so the LinkedIn route works but
    returns an empty list. The Indeed use case is wrapped around
    `fake_indeed_port` (3 sample Indeed jobs). The InfoJobs use case
    is wrapped around `fake_infojobs_port` (3 sample InfoJobs jobs
    with the canonical `/ofertas-trabajo/oferta-{id}` URL format).
    The existing LinkedIn integration tests
    (`tests/integration/test_api.py`, etc.) define their own local
    `app` fixture and so are NOT affected by this conftest fixture.

    The fixture exists to give the per-source integration tests
    (`test_indeed_api.py`, `test_infojobs_api.py`) a single `app` to
    drive, with all routes available for the `/health`-independence
    and per-source cross-check tests.
    """
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = SearchLinkedInJobsUseCase(port=linkedin_port)
    indeed_use_case = IndeedSearchJobsUseCase(port=fake_indeed_port)
    infojobs_use_case = InfoJobsSearchJobsUseCase(port=fake_infojobs_port)
    return build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
    )


# ---------------------------------------------------------------------------
# InfoJobs fixtures (added in T-001 of `infojobs_platform`).
#
# The fixtures mirror the Indeed pattern: a helper that builds 3
# deterministic `Job` instances, a `sample_infojobs_jobs` fixture that
# returns the helper's output, and a `fake_infojobs_port` fixture that
# wraps a `FakeJobSearchPort` primed with the sample jobs. The
# `FakeJobSearchPort` class itself is reused from above — InfoJobs
# doesn't need its own class because the port is source-agnostic
# (REQ-I-003 / REQ-I-005 analog).
# ---------------------------------------------------------------------------


def _make_infojobs_sample_jobs() -> list[Job]:
    """Build 3 deterministic, InfoJobs-style `Job` instances.

    The ids are 7-character alphanumeric slugs (matching the parser's
    `/oferta-<id>` href format — see
    `jobs_finder.infrastructure.infojobs.parsers.parse_infojobs_job_id`).
    Each URL is the canonical
    `https://www.infojobs.net/ofertas-trabajo/oferta-<id>` form
    (REQ-J-001). `posted_at` is tz-aware UTC to satisfy the
    `Job.__post_init__` invariant.
    """
    return [
        Job(
            id="abc123def",
            title="InfoJobs Title 1",
            company="InfoJobs Co 1",
            location="Madrid, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-abc123def",
            posted_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
        Job(
            id="def456ghi",
            title="InfoJobs Title 2",
            company="InfoJobs Co 2",
            location="Barcelona, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-def456ghi",
            posted_at=datetime(2026, 5, 2, tzinfo=UTC),
        ),
        Job(
            id="ghi789jkl",
            title="InfoJobs Title 3",
            company="InfoJobs Co 3",
            location="Valencia, Spain",
            url="https://www.infojobs.net/ofertas-trabajo/oferta-ghi789jkl",
            posted_at=datetime(2026, 5, 3, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def sample_infojobs_jobs() -> list[Job]:
    """3 deterministic, source-agnostic `Job` instances shaped for InfoJobs tests.

    Each job has the canonical
    `https://www.infojobs.net/ofertas-trabajo/oferta-<id>` URL
    (REQ-J-001). The 3 jobs have unique ids, titles, companies, and
    locations so tests that assert field-by-field can identify which
    one they're looking at.
    """
    return _make_infojobs_sample_jobs()


@pytest.fixture
def fake_infojobs_port(sample_infojobs_jobs: list[Job]) -> FakeJobSearchPort:
    """An in-memory `FakeJobSearchPort` primed with `sample_infojobs_jobs`.

    Returns a fresh port per test. The port records every call so tests
    can assert the route/use case forwarded the input correctly.

    Note: the `FakeJobSearchPort` class is the same one used by the
    `fake_indeed_port` fixture (added in T-001 of `indeed_platform`).
    InfoJobs reuses it because the port is source-agnostic.
    """
    return FakeJobSearchPort(jobs=sample_infojobs_jobs)
