"""Unit tests for `SearchAllSourcesUseCase` + `AggregatedResult` + dedup logic.

Spec: REQ-A-001..REQ-A-006.

The aggregator is a thin composition layer over the 3 source use
cases. It invokes them in parallel via `asyncio.gather`, isolates
`JobSearchError` per source, and deduplicates results by
`(title, company, location)` (case-insensitive, whitespace-stripped).
The dedup keeps the FIRST occurrence in source-priority order
(LinkedIn > Indeed > InfoJobs) and accumulates the source name
list for each deduped job.

This test file is the RED → GREEN → REFACTOR anchor for T-001.
It must be authored BEFORE the production module, run to confirm
it fails (RED), then the production module is added, then the
tests pass (GREEN), then any cleanup (REFACTOR) happens.

The tests use `CachedJobSearchUseCase` instances (the production
shape) wrapping fake `JobSearchPort` instances that record calls
and can be primed with jobs or a fixed exception. The wrapper
returns `SearchResult(jobs, cache_status)` and the aggregator must
unify the `list[Job]` shape with the raw `JobSearchPort` shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobs_finder.application.aggregator import (
    SOURCE_PRIORITY,
    SearchAllSourcesUseCase,
)
from jobs_finder.application.usecases._cached_search import (
    CachedJobSearchUseCase,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _job(
    idx: int,
    title: str = "Title",
    company: str = "Co",
    location: str = "Madrid",
) -> Job:
    """Build a deterministic `Job` for tests.

    `posted_at` is tz-aware UTC to satisfy the `Job.__post_init__`
    invariant. The default `id=f"j{idx}"` keeps URLs unique so the
    dedup key is `(title, company, location)` only.
    """
    return Job(
        id=f"j{idx}",
        title=title,
        company=company,
        location=location,
        url=f"https://example.com/j{idx}",
        posted_at=datetime(2026, 6, idx, tzinfo=UTC),
    )


class _FakeJobSearchPort:
    """In-memory fake of `JobSearchPort`.

    Records every call. Can be primed with jobs and/or a fixed
    exception to raise. Mirrors the `_FakeJobSearchPort` used by the
    other test files but is defined inline here so this test file
    remains self-contained.
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


def _build_cached_use_case(port: _FakeJobSearchPort, source: str) -> CachedJobSearchUseCase:
    """Wrap a `_FakeJobSearchPort` in a fresh `CachedJobSearchUseCase`.

    The production aggregator receives the 3 cached wrappers, not the
    raw ports; this helper builds a real wrapper with a fresh
    `InMemoryTTLCache` (no shared state across tests) so the tests
    exercise the same code path as production.
    """
    return CachedJobSearchUseCase(
        port=port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source=source,
    )


def _build_aggregator(
    linkedin_port: _FakeJobSearchPort,
    indeed_port: _FakeJobSearchPort,
    infojobs_port: _FakeJobSearchPort,
) -> SearchAllSourcesUseCase:
    """Build a `SearchAllSourcesUseCase` whose 3 use cases wrap the given ports."""
    return SearchAllSourcesUseCase(
        linkedin_use_case=_build_cached_use_case(linkedin_port, "linkedin"),
        indeed_use_case=_build_cached_use_case(indeed_port, "indeed"),
        infojobs_use_case=_build_cached_use_case(infojobs_port, "infojobs"),
    )


# ---------------------------------------------------------------------------
# Source priority order (REQ-A-001: LinkedIn > Indeed > InfoJobs)
# ---------------------------------------------------------------------------


def test_source_priority_is_linkedin_indeed_infojobs() -> None:
    """`SOURCE_PRIORITY` lists LinkedIn first, then Indeed, then InfoJobs."""
    assert SOURCE_PRIORITY == ("linkedin", "indeed", "infojobs")


# ---------------------------------------------------------------------------
# Happy paths (3 sources, 1 source)
# ---------------------------------------------------------------------------


async def test_3_sources_all_succeed_returns_3_jobs_with_source_lists() -> None:
    """3 sources return 3 distinct jobs; each `AggregatedJob.sources` is `[source]`.

    The default ranking is `posted_at` DESC (REQ-AR-002): j3 has
    `posted_at=2026-06-03` (latest), j2 has `2026-06-02`, j1 has
    `2026-06-01` (earliest). All 3 jobs are from distinct sources
    so the tie-breaker chain (source-priority ASC, then `id` ASC)
    never engages. The result is ordered `[j3, j2, j1]`.
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1, title="LinkedIn Job")])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2, title="Indeed Job")])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3, title="InfoJobs Job")])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert len(result.jobs) == 3
    # The default ranking is `posted_at` DESC: j3 (June 3) is first,
    # j2 (June 2) second, j1 (June 1) last. The source lists on
    # each `AggregatedJob` are preserved from the dedup step.
    assert result.jobs[0].job.id == "j3"
    assert result.jobs[0].sources == ["infojobs"]
    assert result.jobs[1].job.id == "j2"
    assert result.jobs[1].sources == ["indeed"]
    assert result.jobs[2].job.id == "j1"
    assert result.jobs[2].sources == ["linkedin"]


async def test_single_source_query_only_invokes_that_source() -> None:
    """`sources=["linkedin"]` invokes ONLY LinkedIn (Indeed + InfoJobs are skipped)."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin"])

    assert len(result.jobs) == 1
    assert result.jobs[0].sources == ["linkedin"]
    # Only LinkedIn was called.
    assert len(linkedin_port.calls) == 1
    assert len(indeed_port.calls) == 0
    assert len(infojobs_port.calls) == 0


# ---------------------------------------------------------------------------
# Deduplication (REQ-A-002)
# ---------------------------------------------------------------------------


async def test_2_sources_same_job_dedupes_with_both_sources_listed() -> None:
    """LinkedIn and Indeed return the same job; aggregated result has 1 item with both sources."""
    job_a = _job(1, title="Senior Python", company="Acme", location="Madrid")
    linkedin_port = _FakeJobSearchPort(jobs=[job_a])
    indeed_port = _FakeJobSearchPort(jobs=[job_a])
    infojobs_port = _FakeJobSearchPort(jobs=[])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert len(result.jobs) == 1
    assert result.jobs[0].job.id == "j1"
    assert result.jobs[0].sources == ["linkedin", "indeed"]


async def test_3_sources_same_job_dedupes_with_all_3_sources_listed() -> None:
    """All 3 sources return the same job; aggregated result has 1 item with 3 sources."""
    job_a = _job(1, title="Senior Python", company="Acme", location="Madrid")
    linkedin_port = _FakeJobSearchPort(jobs=[job_a])
    indeed_port = _FakeJobSearchPort(jobs=[job_a])
    infojobs_port = _FakeJobSearchPort(jobs=[job_a])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert len(result.jobs) == 1
    assert result.jobs[0].sources == ["linkedin", "indeed", "infojobs"]


async def test_dedup_is_case_insensitive_and_strips_whitespace() -> None:
    """Dedup key is `(title, company, location)` lowercased+stripped; trailing spaces match."""
    linkedin_job = _job(1, title="Senior Python", company="Acme", location="Madrid")
    # Indeed's job differs in case and has leading/trailing whitespace.
    indeed_job = _job(2, title="  senior python  ", company="ACME", location="madrid")
    linkedin_port = _FakeJobSearchPort(jobs=[linkedin_job])
    indeed_port = _FakeJobSearchPort(jobs=[indeed_job])
    infojobs_port = _FakeJobSearchPort(jobs=[])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert len(result.jobs) == 1
    # First occurrence (LinkedIn) wins the canonical `Job`; both sources listed.
    assert result.jobs[0].job.id == "j1"
    assert result.jobs[0].sources == ["linkedin", "indeed"]


async def test_dedup_preserves_source_priority_order_not_insertion_order() -> None:
    """`sources` list is in source-priority order (Indeed, InfoJobs), not the order
    the dedup map was populated in.
    """
    job_a = _job(1, title="Same Title", company="Same Co", location="Same City")
    linkedin_port = _FakeJobSearchPort(jobs=[])
    indeed_port = _FakeJobSearchPort(jobs=[job_a])
    infojobs_port = _FakeJobSearchPort(jobs=[job_a])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert len(result.jobs) == 1
    # Source-priority order, not the (impossible-to-control) asyncio.gather arrival order.
    assert result.jobs[0].sources == ["indeed", "infojobs"]


# ---------------------------------------------------------------------------
# Per-source error isolation (REQ-A-003)
# ---------------------------------------------------------------------------


async def test_one_source_fails_with_job_search_error_returns_others() -> None:
    """LinkedIn + InfoJobs succeed; Indeed raises `JobSearchError`; aggregator returns 2 jobs
    and tracks the failed source in `per_source`.

    The default ranking is `posted_at` DESC: j3 (InfoJobs,
    `posted_at=2026-06-03`) sorts before j1 (LinkedIn,
    `posted_at=2026-06-01`).
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1, title="LinkedIn Job")])
    indeed_port = _FakeJobSearchPort(error=JobSearchError("indeed is down"))
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3, title="InfoJobs Job")])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    # The 2 successful sources' jobs are in the deduped result.
    assert len(result.jobs) == 2
    # Default ranking is `posted_at` DESC: j3 (June 3) is first,
    # j1 (June 1) is second.
    assert result.jobs[0].sources == ["infojobs"]
    assert result.jobs[0].job.id == "j3"
    assert result.jobs[1].sources == ["linkedin"]
    assert result.jobs[1].job.id == "j1"
    # The failed source is tracked with its error.
    assert result.per_source["indeed"].error is not None
    assert isinstance(result.per_source["indeed"].error, JobSearchError)
    assert "indeed is down" in str(result.per_source["indeed"].error)
    # The successful sources have no error.
    assert result.per_source["linkedin"].error is None
    assert result.per_source["infojobs"].error is None
    # `succeeded` is the inverse of `error is not None`.
    assert result.per_source["linkedin"].succeeded is True
    assert result.per_source["indeed"].succeeded is False
    assert result.per_source["infojobs"].succeeded is True


async def test_all_3_sources_fail_returns_empty_jobs_with_all_errors() -> None:
    """All 3 sources raise `JobSearchError`; aggregator returns empty jobs and tracks 3 errors."""
    linkedin_port = _FakeJobSearchPort(error=JobSearchError("linkedin down"))
    indeed_port = _FakeJobSearchPort(error=JobSearchError("indeed down"))
    infojobs_port = _FakeJobSearchPort(error=JobSearchError("infojobs down"))
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])

    assert result.jobs == []
    assert result.per_source["linkedin"].error is not None
    assert result.per_source["indeed"].error is not None
    assert result.per_source["infojobs"].error is not None
    assert result.per_source["linkedin"].succeeded is False
    assert result.per_source["indeed"].succeeded is False
    assert result.per_source["infojobs"].succeeded is False


async def test_non_job_search_error_reraises() -> None:
    """A non-`JobSearchError` (e.g. `KeyError`) from one source propagates to the caller."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(error=KeyError("missing-key"))
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    with pytest.raises(KeyError, match="missing-key"):
        await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])


# ---------------------------------------------------------------------------
# Source validation (REQ-A-001)
# ---------------------------------------------------------------------------


async def test_unknown_source_raises_value_error() -> None:
    """An unknown source name (e.g. `glassdoor`) raises `ValueError` before any call."""
    linkedin_port = _FakeJobSearchPort()
    indeed_port = _FakeJobSearchPort()
    infojobs_port = _FakeJobSearchPort()
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    with pytest.raises(ValueError, match="glassdoor"):
        await use_case.search("python", "madrid", 20, ["linkedin", "glassdoor"])

    # No port was called — validation happens before the gather.
    assert len(linkedin_port.calls) == 0
    assert len(indeed_port.calls) == 0
    assert len(infojobs_port.calls) == 0


# ---------------------------------------------------------------------------
# Cache status (REQ-A-004)
# ---------------------------------------------------------------------------


async def test_cache_statuses_are_miss_on_first_call_and_hit_on_second() -> None:
    """The per-source `cache_statuses` reflect HIT/MISS from the wrapped use case."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    first = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])
    # First call: every source is a cache miss.
    assert first.cache_statuses == {
        "linkedin": "MISS",
        "indeed": "MISS",
        "infojobs": "MISS",
    }

    second = await use_case.search("python", "madrid", 20, ["linkedin", "indeed", "infojobs"])
    # Second call: every source is a cache hit (the wrapped use cases
    # cached the first call's results).
    assert second.cache_statuses == {
        "linkedin": "HIT",
        "indeed": "HIT",
        "infojobs": "HIT",
    }


# ---------------------------------------------------------------------------
# per_source + cache_statuses cover exactly the queried sources
# ---------------------------------------------------------------------------


async def test_per_source_and_cache_statuses_cover_only_queried_sources() -> None:
    """`per_source` and `cache_statuses` contain ONLY the sources that were queried."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("python", "madrid", 20, ["linkedin", "infojobs"])

    assert set(result.per_source.keys()) == {"linkedin", "infojobs"}
    assert set(result.cache_statuses.keys()) == {"linkedin", "infojobs"}
    assert "indeed" not in result.per_source
    assert "indeed" not in result.cache_statuses


# ---------------------------------------------------------------------------
# Argument forwarding (REQ-A-001)
# ---------------------------------------------------------------------------


async def test_search_forwards_keywords_location_and_limit_to_each_port() -> None:
    """The aggregator forwards `(keywords, location, limit)` to every queried port."""
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search("rust", "barcelona", 7, ["linkedin", "indeed", "infojobs"])

    assert linkedin_port.calls == [("rust", "barcelona", 7)]
    assert indeed_port.calls == [("rust", "barcelona", 7)]
    assert infojobs_port.calls == [("rust", "barcelona", 7)]


# ---------------------------------------------------------------------------
# Dependency rule: application does not import infrastructure or presentation
# ---------------------------------------------------------------------------


def test_aggregator_does_not_import_infrastructure_or_presentation() -> None:
    """`aggregator.py` (application layer) has no infrastructure or presentation imports."""
    import ast  # noqa: PLC0415

    source_path = "src/jobs_finder/application/aggregator.py"
    with open(source_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "infrastructure" not in joined, f"{source_path} imports infrastructure"
    assert "presentation" not in joined, f"{source_path} imports presentation"
    assert "playwright" not in joined, f"{source_path} imports playwright"
    assert "fastapi" not in joined, f"{source_path} imports fastapi"
