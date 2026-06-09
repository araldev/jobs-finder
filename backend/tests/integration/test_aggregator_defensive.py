"""Integration tests for the aggregator's defensive partial-results behavior.

Spec: REQ-DEFENSIVE-001 (scenarios 1-4).

The aggregator's design promises that per-source failures
are isolated: one source raising `JobSearchError` does NOT
take down the aggregator. The HTTP status code is:
- `200`: at least 1 source succeeded (partial results are
  valid).
- `502`: ALL 3 sources failed (the registered `JobSearchError`
  handler maps to 502).

The 3 tests below pin the 3 main scenarios + a 4th
"log-once" regression test. Each test drives a
`SearchAllSourcesUseCase` directly (no HTTP layer) to keep
the test focused on the use case's behavior, not the route's
status code mapping (the handler mapping is covered by the
existing `test_exception_handlers.py` suite).

This file is the RED → GREEN → REFACTOR anchor for T-005.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
from jobs_finder.domain.exceptions import AllSourcesFailedError, JobSearchError
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.indeed.exceptions import (
    IndeedBlockedError,
    IndeedTimeoutError,
)
from jobs_finder.infrastructure.infojobs.exceptions import InfoJobsBlockedError
from jobs_finder.infrastructure.linkedin.exceptions import LinkedInBlockedError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _job(idx: int, title: str = "Title") -> Job:
    return Job(
        id=f"j{idx}",
        title=title,
        company="Co",
        location="Madrid",
        url=f"https://example.com/j{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


class _FakeJobSearchPort:
    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        del keywords, location, limit, geo_id
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def _build(
    linkedin_port: _FakeJobSearchPort,
    indeed_port: _FakeJobSearchPort,
    infojobs_port: _FakeJobSearchPort,
) -> SearchAllSourcesUseCase:
    return SearchAllSourcesUseCase(
        linkedin_use_case=CachedJobSearchUseCase(
            port=linkedin_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
        indeed_use_case=CachedJobSearchUseCase(
            port=indeed_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="indeed",
        ),
        infojobs_use_case=CachedJobSearchUseCase(
            port=infojobs_port,
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="infojobs",
        ),
    )


# ---------------------------------------------------------------------------
# Partial results (REQ-DEFENSIVE-001 scenarios 1 + 3)
# ---------------------------------------------------------------------------


async def test_aggregator_returns_partial_results_on_indeed_failure() -> None:
    """Indeed raises `IndeedBlockedError`; LinkedIn + InfoJobs return jobs.

    Aggregator returns the 2 successful sources' jobs (15
    LinkedIn + 8 InfoJobs = 23). The Indeed failure is
    recorded in `per_source` with the exception; the
    aggregator does NOT raise.
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(i) for i in range(1, 16)])
    indeed_port = _FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = _FakeJobSearchPort(jobs=[_job(i, title=f"IJ{i}") for i in range(1, 9)])
    use_case = _build(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "python", "madrid", 20, ["linkedin", "indeed", "infojobs"]
    )

    # 15 LinkedIn + 8 InfoJobs = 23 (Indeed is excluded).
    assert len(result.jobs) == 23
    # Indeed's error is recorded.
    assert result.per_source["indeed"].error is not None
    assert isinstance(result.per_source["indeed"].error, IndeedBlockedError)
    # The successful sources are tracked.
    assert result.per_source["linkedin"].succeeded is True
    assert result.per_source["infojobs"].succeeded is True


async def test_aggregator_returns_200_on_partial_2_fail_1_succeed() -> None:
    """LinkedIn succeeds with 10 jobs; Indeed + InfoJobs both fail.

    Aggregator returns the 10 LinkedIn jobs. The aggregator
    does NOT raise (the route returns 200).
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(i) for i in range(1, 11)])
    indeed_port = _FakeJobSearchPort(error=IndeedTimeoutError())
    infojobs_port = _FakeJobSearchPort(error=InfoJobsBlockedError("distil"))
    use_case = _build(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "python", "madrid", 20, ["linkedin", "indeed", "infojobs"]
    )

    assert len(result.jobs) == 10
    assert result.per_source["linkedin"].succeeded is True
    assert result.per_source["indeed"].succeeded is False
    assert result.per_source["infojobs"].succeeded is False


# ---------------------------------------------------------------------------
# All sources fail → 502 (REQ-DEFENSIVE-001 scenario 2)
# ---------------------------------------------------------------------------


async def test_aggregator_returns_502_when_all_sources_fail() -> None:
    """All 3 sources fail with `JobSearchError`; aggregator raises `AllSourcesFailedError`.

    The aggregator waits for `asyncio.gather` to complete (does
    NOT abort on the first failure), then raises
    `AllSourcesFailedError` because `success_count == 0`. The
    registered `JobSearchError` handler maps this to HTTP
    502.
    """
    linkedin_port = _FakeJobSearchPort(error=LinkedInBlockedError("auth wall"))
    indeed_port = _FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = _FakeJobSearchPort(error=InfoJobsBlockedError("distil"))
    use_case = _build(linkedin_port, indeed_port, infojobs_port)

    with pytest.raises(AllSourcesFailedError):
        await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])


# ---------------------------------------------------------------------------
# Per-source WARNING log (REQ-DEFENSIVE-001 scenario 4)
# ---------------------------------------------------------------------------


async def test_failed_source_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failed source is logged at WARNING level exactly ONCE (not once per job).

    LinkedIn returns 25 jobs (a full page). Indeed raises
    `IndeedBlockedError`. The aggregator's WARNING log for
    `source="indeed"` appears exactly 1 time, not 25. (A
    regression that logged per-job would surface here.)
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(i) for i in range(1, 26)])
    indeed_port = _FakeJobSearchPort(error=IndeedBlockedError("cloudflare"))
    infojobs_port = _FakeJobSearchPort(jobs=[])
    use_case = _build(linkedin_port, indeed_port, infojobs_port)

    with caplog.at_level(logging.WARNING, logger="jobs_finder.application.aggregator"):
        result = await use_case.search(
            "python", "madrid", 20, ["linkedin", "indeed", "infojobs"]
        )

    # The aggregator returned 25 LinkedIn jobs.
    assert len(result.jobs) == 25
    # The WARNING log for the failed source appears exactly 1 time.
    indeed_warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and getattr(rec, "source", None) == "indeed"
    ]
    assert len(indeed_warnings) == 1
