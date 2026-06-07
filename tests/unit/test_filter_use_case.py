"""Unit tests for the chat-filter use case (T-013 of `ai-chat-filter`).

Spec: REQ-LLM-003 (strict-subset ID validation), REQ-CHAT-001
(message normalization — verified at the route layer in T-014).

`FilterJobsByIntentUseCase` orchestrates the 3-stage chat-filter
flow:
  1. Call the existing `SearchAllSourcesUseCase` aggregator
     (reuses the per-source cache + per-source error isolation).
  2. Short-circuit on empty aggregator result — the LLM is NEVER
     called when no jobs are available; the response carries the
     Spanish "no se encontraron ofertas" explanation.
  3. Build the 5-key LLM-facing dict per job, call the LLM with
     the Spanish system prompt + a JSON-serialized user message,
     parse the response, validate `matching_ids` to a strict
     subset of input IDs, log a WARNING per dropped (hallucinated)
     ID, and return the filtered jobs in the aggregator's order
     (NOT the LLM's order).

The use case depends ONLY on the application's `LLMClientPort`
Protocol — never on the concrete `MiniMaxLLMClient`. The test
fixtures use a `FakeLLMClient` + `FakeAggregator` so the
orchestration is exercised without invoking any real port or LLM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from jobs_finder.application.aggregator import (
    AggregatedJob,
    AggregatedResult,
    SourceResult,
)
from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilteredJobsResult,
    FilterJobsByIntentUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.llm._parser import LLMSelection
from jobs_finder.infrastructure.llm.exceptions import (
    LLMResponseParseError,
    LLMUnavailableError,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_job(job_id: str, title: str = "Software Engineer") -> Job:
    """Build a `Job` with a unique id and a sensible default shape.

    The chat use case is source-agnostic — the test fixtures use
    `title` / `company` as visual discriminators and `id` as the
    only field the LLM-driven filter actually inspects.
    """
    return Job(
        id=job_id,
        title=title,
        company=f"Co-{job_id}",
        location="Madrid",
        url=f"https://example.com/jobs/{job_id}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeAggregator:
    """Stand-in for `SearchAllSourcesUseCase` that returns a canned result.

    Implements the same `search(keywords, location, limit, sources)`
    signature the real aggregator exposes. Records every call so
    tests can assert the use case forwarded the right `q` /
    `location` / `limit` / `sources`. Returns a fixed
    `AggregatedResult` (or raises a fixed exception) for
    testability.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs = jobs if jobs is not None else []
        self._error = error
        self.calls: list[tuple[str, str, int, list[str] | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str] | None = None,
    ) -> AggregatedResult:
        self.calls.append((keywords, location, limit, sources))
        if self._error is not None:
            raise self._error
        # Wrap each Job in an AggregatedJob with a single source
        # name. The test doesn't depend on the source list; the
        # use case flattens the per-source wrapper to a `Job`.
        aggregated = [AggregatedJob(job=job, sources=["linkedin"]) for job in self._jobs]
        per_source: dict[str, SourceResult] = {
            "linkedin": SourceResult(
                source="linkedin",
                jobs=self._jobs,
                cache_status="MISS",
            )
        }
        return AggregatedResult(
            jobs=aggregated,
            per_source=per_source,
            cache_statuses={"linkedin": "MISS"},
        )


class FakeLLMClient:
    """An in-memory `LLMClientPort` for tests.

    Records every call so tests can assert the use case forwarded
    the right `system` / `user` arguments. Returns a fixed
    `LLMSelection` (or raises a fixed exception) for testability.

    Returns a JSON string that the production `parse_llm_response`
    parses into the same `LLMSelection`. This keeps the fake
    structurally honest: the production parser runs on the
    returned string, just like in production.
    """

    def __init__(
        self,
        selection: LLMSelection | None = None,
        error: Exception | None = None,
    ) -> None:
        self._selection = selection or LLMSelection(matching_ids=[], explanation="")
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._error is not None:
            raise self._error
        return json.dumps(
            {
                "matching_ids": list(self._selection.matching_ids),
                "explanation": self._selection.explanation,
            }
        )


# ---------------------------------------------------------------------------
# Happy path — LLM picks 3 of 5 jobs; result is in AGGREGATOR order, not
# the LLM's order.
# ---------------------------------------------------------------------------


async def test_execute_returns_filtered_jobs_in_aggregator_order() -> None:
    """5 jobs in, LLM returns 3 ids, the result has 3 jobs in the
    aggregator's order (NOT the LLM's order).

    The use case must preserve the aggregator's order so the
    response is consistent with the rest of the API (per-source
    priority + ranking).
    """
    jobs = [
        _make_job("a"),
        _make_job("b"),
        _make_job("c"),
        _make_job("d"),
        _make_job("e"),
    ]
    aggregator = FakeAggregator(jobs=jobs)
    # LLM returns IDs in a non-aggregator order: e, a, c (not a, c, e).
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["e", "a", "c"], explanation="3 match"))

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )

    assert [j.id for j in result.jobs] == ["a", "c", "e"]  # aggregator order
    assert result.explanation == "3 match"
    assert result.total_considered == 5
    assert result.total_matched == 3


# ---------------------------------------------------------------------------
# Empty aggregator — short-circuit; LLM is NEVER called.
# ---------------------------------------------------------------------------


async def test_execute_short_circuits_when_aggregator_returns_no_jobs() -> None:
    """0 jobs from the aggregator → empty result + Spanish explanation; LLM is NEVER called.

    REQ-LLM-003 5th scenario: "Empty aggregated list → LLM not called".
    The use case skips the LLM call entirely (no payload to filter)
    and returns a Spanish explanation so the route can surface a
    sensible response to the user.
    """
    aggregator = FakeAggregator(jobs=[])
    llm = FakeLLMClient()  # would record calls if invoked

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )

    assert result.jobs == []
    assert result.total_considered == 0
    assert result.total_matched == 0
    # The Spanish "no se encontraron" explanation is surfaced verbatim.
    assert "no se encontraron" in result.explanation.lower()
    # The LLM was NEVER called.
    assert llm.calls == []


# ---------------------------------------------------------------------------
# Hallucinated IDs — strict subset validation drops them, logs a warning per
# dropped id.
# ---------------------------------------------------------------------------


async def test_execute_drops_hallucinated_ids_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LLM returns 1 hallucinated id + 2 valid → result has 2 jobs and 1 WARNING.

    REQ-LLM-003 2nd scenario: "One hallucinated ID". The use case
    filters the LLM's `matching_ids` to a strict subset of the
    input, logs a WARNING per dropped id, and returns only the
    valid matches. The caplog assertion pins the warning shape
    (the id appears in the message).
    """
    jobs = [_make_job("a"), _make_job("b")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a", "hallucinated"], explanation="ok")
    )

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    with caplog.at_level("WARNING"):
        result = await use_case.execute(
            message="python",
            q="",
            location="",
            limit=20,
        )

    # Only `a` is in the result.
    assert [j.id for j in result.jobs] == ["a"]
    assert result.total_considered == 2
    assert result.total_matched == 1
    # Exactly one WARNING logged for the hallucinated id.
    hallucination_warnings = [
        record for record in caplog.records if "hallucinated" in record.getMessage().lower()
    ]
    assert len(hallucination_warnings) == 1
    assert "hallucinated" in hallucination_warnings[0].getMessage()


async def test_execute_all_hallucinated_returns_empty_with_warnings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """5 jobs, LLM returns 5 unknown ids → result is empty, 5 WARNINGs logged.

    REQ-LLM-003 3rd scenario: "All hallucinated". Every LLM-returned
    id is dropped, the response is an empty `jobs` list, and a
    WARNING is logged per dropped id. The result is a defensible
    "no matches" answer rather than a 5xx.
    """
    jobs = [
        _make_job("a"),
        _make_job("b"),
        _make_job("c"),
        _make_job("d"),
        _make_job("e"),
    ]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(
            matching_ids=["bogus1", "bogus2", "bogus3", "bogus4", "bogus5"],
            explanation="none match",
        )
    )

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    with caplog.at_level("WARNING"):
        result = await use_case.execute(
            message="python",
            q="",
            location="",
            limit=20,
        )

    assert result.jobs == []
    assert result.total_considered == 5
    assert result.total_matched == 0
    # 5 warnings, one per dropped id.
    hallucination_warnings = [
        record for record in caplog.records if "hallucinated" in record.getMessage().lower()
    ]
    assert len(hallucination_warnings) == 5


# ---------------------------------------------------------------------------
# Empty LLM list — valid answer (the LLM said "no matches"); no warning.
# ---------------------------------------------------------------------------


async def test_execute_empty_llm_list_returns_empty_with_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """5 jobs, LLM returns empty `matching_ids` → result is empty, NO warning.

    REQ-LLM-003 4th scenario: "Empty LLM list". The LLM correctly
    identified that no jobs match; the use case does NOT log a
    hallucination warning (nothing was hallucinated).
    """
    jobs = [_make_job("a"), _make_job("b")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=[], explanation="none match"))

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    with caplog.at_level("WARNING"):
        result = await use_case.execute(
            message="python",
            q="",
            location="",
            limit=20,
        )

    assert result.jobs == []
    assert result.total_considered == 2
    assert result.total_matched == 0
    # No hallucination warnings (the LLM did not invent any ids).
    hallucination_warnings = [
        record for record in caplog.records if "hallucinated" in record.getMessage().lower()
    ]
    assert hallucination_warnings == []


# ---------------------------------------------------------------------------
# Error propagation — the use case does NOT swallow LLM-side errors; the
# route maps them to HTTP 502 / 422.
# ---------------------------------------------------------------------------


async def test_execute_propagates_llm_unavailable_error() -> None:
    """LLM raises `LLMUnavailableError` → use case propagates it (route maps to 502).

    The use case is a thin orchestrator: it does not catch
    LLM-specific errors. The existing presentation-layer handler
    maps the parent `JobSearchError` to 502 with the standard
    masked-detail body.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(error=LLMUnavailableError("upstream down"))

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]
    with pytest.raises(LLMUnavailableError, match="upstream down"):
        await use_case.execute(
            message="python",
            q="",
            location="",
            limit=20,
        )


async def test_execute_propagates_llm_response_parse_error() -> None:
    """LLM raises `LLMResponseParseError` → use case propagates it (route maps to 422).

    The defensive parser is configured to raise (not silently
    return empty) when both tier-1 and tier-2 fail. The use case
    must NOT swallow this error; the route catches it locally
    and returns 422.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(error=LLMResponseParseError("no JSON in response"))

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]
    with pytest.raises(LLMResponseParseError, match="no JSON in response"):
        await use_case.execute(
            message="python",
            q="",
            location="",
            limit=20,
        )


# ---------------------------------------------------------------------------
# Aggregator argument forwarding — the use case must forward the call's
# `q` / `location` / `limit` / `sources` to the aggregator so the
# per-source cache key is the same as `/jobs`'s cache key.
# ---------------------------------------------------------------------------


async def test_execute_forwards_q_location_limit_to_aggregator() -> None:
    """The use case forwards the input `q` / `location` / `limit` / `sources`
    to the aggregator's `search()` so the per-source cache key is
    consistent with the `/jobs` aggregator route.

    The chat endpoint passes `q=""` and `location=""` in v1 (the
    message IS the intent), but the use case MUST forward whatever
    the caller passes so a future caller (e.g. a chat-with-defaults
    endpoint) can pre-fill `q` and benefit from the aggregator
    cache.
    """
    aggregator = FakeAggregator(jobs=[])
    llm = FakeLLMClient()

    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]
    await use_case.execute(
        message="python",
        q="python",
        location="Madrid",
        limit=10,
        sources=["linkedin", "infojobs"],
    )

    # The aggregator received the call with the forwarded args.
    assert aggregator.calls == [("python", "Madrid", 10, ["linkedin", "infojobs"])]


# ---------------------------------------------------------------------------
# Return-type sanity — the dataclass shape is documented and pinned.
# ---------------------------------------------------------------------------


def test_filtered_jobs_result_is_frozen_and_slots() -> None:
    """`FilteredJobsResult` is a frozen + slotted dataclass.

    The use case returns this dataclass to the route; the route
    reads `.jobs` / `.explanation` / `.total_considered` /
    `.total_matched`. A regression that switches the class to a
    mutable dataclass would silently allow the route to mutate
    the result; the `frozen=True, slots=True` contract is part
    of the type's API.
    """
    result = FilteredJobsResult(
        jobs=[],
        explanation="",
        total_considered=0,
        total_matched=0,
    )
    # `frozen=True` rejects attribute assignment.
    with pytest.raises((AttributeError, Exception)):
        result.jobs = []  # type: ignore[misc]
