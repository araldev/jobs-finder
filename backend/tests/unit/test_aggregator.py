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

    The `geo_id` kwarg is part of the `JobSearchPort` Protocol
    signature since the `fix-linkedin-geoid` change (the
    aggregator forwards it to the LinkedIn port; Indeed +
    InfoJobs ignore it). The 4-tuple `calls` shape captures
    the per-source forwarding contract: a LinkedIn call
    records `(keywords, location, limit, geo_id)`; an Indeed
    or InfoJobs call records `(keywords, location, limit, None)`.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self._error: Exception | None = error
        self.calls: list[tuple[str, str, int, int | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        self.calls.append((keywords, location, limit, geo_id))
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
    """Build a `SearchAllSourcesUseCase` whose 3 use cases wrap the given ports.

    Wires the production pure-function helpers
    (`filter_infojobs_results` + `keyword_score`) at
    construction time so the v1 + T-004 behaviors are both
    exercised. The aggregator's no-op defaults preserve
    backward compat for direct callers; tests that exercise
    the new behavior need the real helpers.
    """
    from jobs_finder.infrastructure.aggregator_filters import (  # noqa: PLC0415
        filter_infojobs_results,
    )
    from jobs_finder.infrastructure.keyword_score import keyword_score  # noqa: PLC0415

    return SearchAllSourcesUseCase(
        linkedin_use_case=_build_cached_use_case(linkedin_port, "linkedin"),
        indeed_use_case=_build_cached_use_case(indeed_port, "indeed"),
        infojobs_use_case=_build_cached_use_case(infojobs_port, "infojobs"),
        filter_infojobs_results=filter_infojobs_results,
        keyword_score=keyword_score,
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

    assert linkedin_port.calls == [("rust", "barcelona", 7, None)]
    assert indeed_port.calls == [("rust", "barcelona", 7, None)]
    assert infojobs_port.calls == [("rust", "barcelona", 7, None)]


# ---------------------------------------------------------------------------
# `linkedin_geo_id` dispatch (REQ-LOC-GEO-001 + REQ-A-001)
#
# The 2-stage chat filter calls the aggregator with
# `linkedin_geo_id=103374081` (Madrid's captured geoId) when
# the resolver returned a value. The aggregator MUST forward
# the kwarg ONLY to the LinkedIn use case (the per-source
# port that consumes it) — Indeed + InfoJobs are unaffected
# (they accept `location=` strings; they don't need a
# `geoId=`). The forwarding is the seam between the use
# case's 2-stage path and the LinkedIn scraper's URL
# formula.
# ---------------------------------------------------------------------------


async def test_linkedin_geo_id_is_forwarded_to_linkedin_port_only() -> None:
    """`linkedin_geo_id=103374081` → LinkedIn port receives it; Indeed + InfoJobs do NOT.

    The aggregator's per-source dispatch is the seam
    between the 2-stage chat filter (which has the
    resolved `geo_id` from the resolver) and the LinkedIn
    scraper (which uses the `geo_id` in the URL formula).
    The kwarg flows ONLY to the LinkedIn use case;
    Indeed + InfoJobs are called with the existing 3-arg
    signature (`keywords`, `location`, `limit`).
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search(
        "python", "Madrid", 20, ["linkedin", "indeed", "infojobs"], linkedin_geo_id=103374081
    )

    # The LinkedIn port received the `geo_id=103374081` kwarg.
    assert len(linkedin_port.calls) == 1
    keywords, location, limit, geo_id = linkedin_port.calls[0]
    assert keywords == "python"
    assert location == "Madrid"
    assert limit == 20
    assert geo_id == 103374081
    # The Indeed port received the 3-arg call (NO `geo_id`).
    assert indeed_port.calls == [("python", "Madrid", 20, None)]
    # The InfoJobs port received the 3-arg call (NO `geo_id`).
    assert infojobs_port.calls == [("python", "Madrid", 20, None)]


async def test_linkedin_geo_id_none_is_forwarded_to_linkedin_port() -> None:
    """`linkedin_geo_id=None` (resolver miss) → LinkedIn port receives `geo_id=None`.

    When the resolver returns `None` (unknown / country-
    level / País Vasco / Canarias / empty), the aggregator
    forwards `geo_id=None` to the LinkedIn port. The
    LinkedIn port's `search()` accepts the kwarg and the
    scraper's URL builder falls back to `?location=`
    (the broken-but-doesn't-500 path). The test pins
    the forwarding contract end-to-end.
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search(
        "python", "Madrid", 20, ["linkedin", "indeed", "infojobs"], linkedin_geo_id=None
    )

    # The LinkedIn port received `geo_id=None`.
    keywords, location, limit, geo_id = linkedin_port.calls[0]
    assert keywords == "python"
    assert location == "Madrid"
    assert limit == 20
    assert geo_id is None
    # Indeed + InfoJobs are still 3-arg.
    assert indeed_port.calls == [("python", "Madrid", 20, None)]
    assert infojobs_port.calls == [("python", "Madrid", 20, None)]


async def test_linkedin_geo_id_default_is_none() -> None:
    """`aggregator.search(...)` WITHOUT `linkedin_geo_id` defaults to `None`.

    Backward compat: callers that pre-date WU3 invoke the
    aggregator with the 4-arg signature
    (`keywords`, `location`, `limit`, `sources`); the
    `linkedin_geo_id` kwarg is optional with a `None`
    default. The test pins the default so existing
    callers (the v1 chat-filter path, the `/jobs`
    aggregator route) keep working unchanged.
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search("python", "Madrid", 20, ["linkedin", "indeed", "infojobs"])

    # The LinkedIn port received `geo_id=None` (default).
    keywords, location, limit, geo_id = linkedin_port.calls[0]
    assert geo_id is None
    # Indeed + InfoJobs received 3-arg calls.
    assert indeed_port.calls == [("python", "Madrid", 20, None)]
    assert infojobs_port.calls == [("python", "Madrid", 20, None)]


async def test_linkedin_geo_id_is_forwarded_only_when_linkedin_is_queried() -> None:
    """`sources=["indeed", "infojobs"]` + `linkedin_geo_id=103374081` → no LinkedIn call at all.

    The per-source dispatch validates `sources` first; a
    call with `linkedin_geo_id` but no `linkedin` in
    `sources` does NOT invoke the LinkedIn port (the kwarg
    is silently dropped — the per-source dispatch only
    loops over the queried sources). The test pins the
    "no LinkedIn call when LinkedIn is not queried"
    contract.
    """
    linkedin_port = _FakeJobSearchPort(jobs=[])
    indeed_port = _FakeJobSearchPort(jobs=[_job(2)])
    infojobs_port = _FakeJobSearchPort(jobs=[_job(3)])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search("python", "Madrid", 20, ["indeed", "infojobs"], linkedin_geo_id=103374081)

    # The LinkedIn port was NOT called.
    assert linkedin_port.calls == []
    # The Indeed + InfoJobs ports received 3-arg calls.
    assert indeed_port.calls == [("python", "Madrid", 20, None)]
    assert infojobs_port.calls == [("python", "Madrid", 20, None)]


# ---------------------------------------------------------------------------
# Cache-key 5th field dispatch (REQ-C-005 + REQ-LOC-GEO-001)
#
# A query with `linkedin_geo_id=103374081` and the same
# query with `linkedin_geo_id=None` MUST be different
# cache entries (different results — the geoId-filtered
# scrape returns Madrid-specific jobs, the unresolved
# scrape returns LinkedIn's default landing page). The
# `JobSearchCacheKey` 5th field pins the isolation.
# ---------------------------------------------------------------------------


async def test_aggregator_distinguishes_geo_id_in_cache_key_for_linkedin() -> None:
    """`linkedin_geo_id=103374081` vs `linkedin_geo_id=None` → 2 cache MISSes, 0 HITs.

    The `JobSearchCacheKey` 5th field (`geo_id`) isolates
    the 2 cache entries. The first call with
    `geo_id=103374081` is a MISS; the second call with
    `geo_id=None` (same keywords/location/limit) is ALSO
    a MISS (different cache key). The 3rd call with
    `geo_id=103374081` again is a HIT (same as the first).
    """
    linkedin_port = _FakeJobSearchPort(jobs=[_job(1)])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    first = await use_case.search("python", "Madrid", 20, ["linkedin"], linkedin_geo_id=103374081)
    second = await use_case.search("python", "Madrid", 20, ["linkedin"], linkedin_geo_id=None)
    third = await use_case.search("python", "Madrid", 20, ["linkedin"], linkedin_geo_id=103374081)

    # First + third: same `geo_id=103374081` cache entry.
    # Second: different `geo_id=None` cache entry.
    assert first.cache_statuses["linkedin"] == "MISS"
    assert second.cache_statuses["linkedin"] == "MISS"
    assert third.cache_statuses["linkedin"] == "HIT"


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


# ---------------------------------------------------------------------------
# InfoJobs client-side filter (REQ-FILTER-001, T-004)
#
# The `SearchAllSourcesUseCase.search()` method accepts a
# `query_tokens: frozenset[str] = frozenset()` kwarg. When
# non-empty, the aggregator applies `filter_infojobs_results`
# to the InfoJobs slice of the deduped jobs (post-cache,
# post-scrape). LinkedIn and Indeed are NOT filtered. The
# default empty set preserves the v1 contract (no filter
# applied, full result set returned).
# ---------------------------------------------------------------------------


async def test_aggregator_applies_infojobs_filter() -> None:
    """InfoJobs job with 0-token-overlap title is dropped; LinkedIn job with same title is kept.

    `query_tokens={"react", "málaga"}`. InfoJobs returns
    `Recepcionista` (0 overlap → dropped). LinkedIn returns
    `Senior Python` (also 0 overlap → kept, because the
    filter applies ONLY to InfoJobs). The result has 1 job
    from LinkedIn.
    """
    infojobs_recep = _job(1, title="Recepcionista")
    linkedin_python = _job(2, title="Senior Python")
    linkedin_port = _FakeJobSearchPort(jobs=[linkedin_python])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[infojobs_recep])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "react",
        "malaga",
        20,
        ["linkedin", "indeed", "infojobs"],
        query_tokens=frozenset({"react", "málaga"}),
    )

    # The LinkedIn job is in the result (filter does NOT apply to LinkedIn).
    assert len(result.jobs) == 1
    assert result.jobs[0].job.id == "j2"
    assert result.jobs[0].sources == ["linkedin"]


async def test_aggregator_does_not_filter_linkedin_or_indeed() -> None:
    """A 0-overlap LinkedIn job + a 0-overlap Indeed job are BOTH kept.

    The filter applies ONLY to InfoJobs (REQ-FILTER-001
    scenario 3). A LinkedIn job with no token overlap is
    still surfaced; an Indeed job with no token overlap is
    also still surfaced. Only the InfoJobs slice is filtered.
    """
    linkedin_no_match = _job(1, title="Senior Java Developer")
    indeed_no_match = _job(2, title="Recepcionista Hotel")
    infojobs_no_match = _job(3, title="Pintor Industrial")
    linkedin_port = _FakeJobSearchPort(jobs=[linkedin_no_match])
    indeed_port = _FakeJobSearchPort(jobs=[indeed_no_match])
    infojobs_port = _FakeJobSearchPort(jobs=[infojobs_no_match])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "react",
        "malaga",
        20,
        ["linkedin", "indeed", "infojobs"],
        query_tokens=frozenset({"react", "málaga"}),
    )

    # LinkedIn + Indeed are kept; InfoJobs is dropped.
    assert len(result.jobs) == 2
    result_ids = sorted(job.job.id for job in result.jobs)
    assert result_ids == ["j1", "j2"]


async def test_aggregator_sorts_by_keyword_score_when_enabled() -> None:
    """`enable_keyword_scoring=True` → sorted by score DESC, then posted_at DESC.

    Two jobs:
    - `A` with `title="React Developer"` (matches `react` AND
      `developer` → score = 1.0 — full title match).
    - `B` with `title="Python Developer"` (matches `developer`
      only → score = 0.5 — partial title match).

    With `query_tokens={"react", "developer"}` and
    `enable_keyword_scoring=True`, A sorts BEFORE B. The
    `query_tokens` is chosen so BOTH jobs survive the
    InfoJobs filter (1+ token overlap on `developer`).
    """
    job_a = _job(1, title="React Developer")
    job_b = _job(2, title="Python Developer")
    linkedin_port = _FakeJobSearchPort(jobs=[job_a])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[job_b])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "react",
        "madrid",
        20,
        ["linkedin", "indeed", "infojobs"],
        query_tokens=frozenset({"react", "developer"}),
        enable_keyword_scoring=True,
    )

    # A is first (higher score).
    assert result.jobs[0].job.id == "j1"
    assert result.jobs[1].job.id == "j2"


async def test_aggregator_sorts_by_posted_at_when_disabled() -> None:
    """`enable_keyword_scoring=False` (default) → existing `posted_at` DESC sort is used.

    Backward compat: the v1 `rank_jobs` function sorts by
    `posted_at` DESC (with source-priority tie-breaker). When
    `enable_keyword_scoring=False` (the default), the
    aggregator MUST call the existing sort path, NOT the
    `keyword_score` path. The test pins the contract: a
    later-posted job sorts BEFORE an earlier-posted job
    regardless of keyword relevance. No `query_tokens` is
    passed so the InfoJobs filter is a no-op.
    """
    # j1: EARLY date, "React Developer" (would have a high
    #     score if `enable_keyword_scoring=True`).
    # j3: LATE date, "Python Developer" (would have a 0
    #     score if `enable_keyword_scoring=True`).
    job_early_react = _job(1, title="React Developer")
    job_late_python = _job(3, title="Python Developer")
    linkedin_port = _FakeJobSearchPort(jobs=[job_early_react])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[job_late_python])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search(
        "react",
        "madrid",
        20,
        ["linkedin", "indeed", "infojobs"],
        enable_keyword_scoring=False,  # default behavior
    )

    # j3 (later date) sorts first per the `posted_at` DESC
    # sort; the keyword_score is irrelevant.
    assert result.jobs[0].job.id == "j3"
    assert result.jobs[1].job.id == "j1"


async def test_aggregator_forwards_query_tokens_to_filter() -> None:
    """`query_tokens` is forwarded to the InfoJobs filter; the LinkedIn/Indeed paths are unaffected.

    A LinkedIn port spy records the call. The aggregator
    receives `query_tokens={"react"}`; the LinkedIn port
    receives the 4-arg call (`keywords, location, limit, None`)
    — the new kwarg is filter-only and does NOT propagate to
    the LinkedIn/Indeed ports. (The `query_tokens` is
    aggregator-internal; the per-source use cases are
    unchanged.)
    """
    linkedin_port = _FakeJobSearchPort(jobs=[])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    await use_case.search(
        "react",
        "malaga",
        20,
        ["linkedin", "indeed", "infojobs"],
        query_tokens=frozenset({"react"}),
    )

    # LinkedIn + Indeed + InfoJobs all received 4-arg calls
    # (no `query_tokens` kwarg in the per-source signature).
    assert linkedin_port.calls == [("react", "malaga", 20, None)]
    assert indeed_port.calls == [("react", "malaga", 20, None)]
    assert infojobs_port.calls == [("react", "malaga", 20, None)]


# ---------------------------------------------------------------------------
# `query_tokens` backward-compat: default empty set does NOT filter
# ---------------------------------------------------------------------------


async def test_aggregator_default_query_tokens_does_not_filter() -> None:
    """`query_tokens` default (empty) → no InfoJobs filter applied (backward compat).

    A pre-WU2 caller invokes `aggregator.search(...)` WITHOUT
    the new `query_tokens` kwarg. The default is
    `frozenset()` (empty). The filter is a no-op: the
    InfoJobs `Recepcionista` job is kept.
    """
    infojobs_recep = _job(1, title="Recepcionista")
    linkedin_port = _FakeJobSearchPort(jobs=[])
    indeed_port = _FakeJobSearchPort(jobs=[])
    infojobs_port = _FakeJobSearchPort(jobs=[infojobs_recep])
    use_case = _build_aggregator(linkedin_port, indeed_port, infojobs_port)

    result = await use_case.search("react", "malaga", 20, ["linkedin", "indeed", "infojobs"])

    # No filter applied: the InfoJobs job is in the result.
    assert len(result.jobs) == 1
    assert result.jobs[0].job.id == "j1"
