"""End-to-end smoke test for ALL THREE source routes.

Spec: REQ-J-014 (composition), REQ-J-016 (live verify), REQ-J-018
(smoke test).

Exercises `GET /jobs/linkedin`, `GET /jobs/indeed`, AND
`GET /jobs/infojobs` with a `FakeJobSearchPort` injected into
each of the three dependency overrides. The test asserts that
ALL THREE routes return 200 with a populated `jobs` array, proving
the composition works for every source.

The test is a `final-verify` (T-012) sanity check; it does not
cover the parser / scraper internals (those have their own unit
tests). The test exists to catch regressions in the composition
root when any of the three sources' routes / schemas /
dependencies change.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

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
from tests.conftest import FakeJobSearchPort


async def test_smoke_all_three_routes_return_200_with_populated_jobs() -> None:
    """All three `/jobs/<source>` routes return 200 with a populated `jobs` array.

    The test injects a `FakeJobSearchPort` (primed with 3 sample
    jobs each) into the three use-case dependency overrides. The
    scraper is never invoked (the fake port short-circuits the
    network).
    """
    # Prime each fake port with 3 jobs (the default conftest
    # fixture sample). Without priming, `FakeJobSearchPort()`
    # returns an empty list.
    sample_jobs = _three_sample_jobs()
    linkedin_port = FakeJobSearchPort(jobs=sample_jobs)
    indeed_port = FakeJobSearchPort(jobs=sample_jobs)
    infojobs_port = FakeJobSearchPort(jobs=sample_jobs)

    app = build_app(
        use_case=SearchLinkedInJobsUseCase(port=linkedin_port),
        indeed_use_case=IndeedSearchJobsUseCase(port=indeed_port),
        infojobs_use_case=InfoJobsSearchJobsUseCase(port=infojobs_port),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # LinkedIn
        li_response = await client.get("/jobs/linkedin?keywords=python&location=madrid&limit=2")
        assert li_response.status_code == 200
        li_jobs = li_response.json()["jobs"]
        # The fake port returns all primed jobs regardless of
        # `limit` (FakeJobSearchPort doesn't slice — the real
        # scraper would). We assert ≥ 1 to prove the route
        # successfully translates the use case's output to a
        # 200 response.
        assert len(li_jobs) >= 1

        # Indeed
        in_response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=2")
        assert in_response.status_code == 200
        in_jobs = in_response.json()["jobs"]
        assert len(in_jobs) >= 1

        # InfoJobs
        ij_response = await client.get("/jobs/infojobs?keywords=python&location=madrid&limit=2")
        assert ij_response.status_code == 200
        ij_jobs = ij_response.json()["jobs"]
        assert len(ij_jobs) >= 1

    # Each port was called exactly once (once per source's
    # dependency override chain).
    assert len(linkedin_port.calls) == 1
    assert len(indeed_port.calls) == 1
    assert len(infojobs_port.calls) == 1


def _three_sample_jobs() -> list[Job]:
    """Build 3 deterministic, source-agnostic `Job` instances for the smoke test.

    The shape is a real `Job` (domain value object) so the route's
    `to_response()` helper can map it to `JobResponse` without
    raising.
    """
    base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    return [
        Job(
            id=f"smoke-{i}",
            title=f"Smoke Test Job {i}",
            company="Smoke Co",
            location="Madrid, Spain",
            url=f"https://example.com/job/{i}",
            posted_at=base,
        )
        for i in range(1, 4)
    ]
