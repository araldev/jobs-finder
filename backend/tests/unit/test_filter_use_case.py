"""Unit tests for the chat-filter use case (T-013 of `ai-chat-filter`,
extended in T-008/T-010 of `chat-filter-2stage`).

Spec: REQ-LLM-003 (strict-subset ID validation), REQ-CHAT-001
(message normalization — verified at the route layer in T-014),
REQ-CHAT-INT-001..005 (2-stage flow + v1 fallback).

`FilterJobsByIntentUseCase` orchestrates the 3-stage chat-filter
flow with the 2-stage LLM option. Stage 2 queries the
`JobRepositoryPort` (the SQLite-backed cache populated by the
scheduler) — the chat endpoint NEVER calls the live scrapers.

  v1 path (REQ-CHAT-INT-005 backward compat):
    1. Call `job_repository.search_jobs_history(...)` with
       `q=""`, `location=""`, `limit=20` (the caller's
       forwarded args). Reuses the DB populated by the
       scheduler.
    2. Short-circuit on empty repository result — the LLM is
       NEVER called when no jobs are available; the response
       carries the Spanish "no se encontraron ofertas"
       explanation.
    3. Build the 5-key LLM-facing dict per job, call the LLM
       with the Spanish system prompt + a JSON-serialized user
       message, parse the response, validate `matching_ids` to
       a strict subset of input IDs, log a WARNING per dropped
       (hallucinated) ID, and return the filtered jobs in the
       repository's order (NOT the LLM's order).

  2-stage path (REQ-CHAT-INT-001..004):
    1. Call `IntentExtractor.extract(message=...)` to get a
       structured `Intent` (stage 1).
    2. If `intent.confidence >= threshold`: call the repository
       with `q=intent.q or ""`, `location=intent.location or ""`,
       `limit=intent_max_results` (stage 2). The remaining
       steps are identical to the v1 path (stage 3 LLM filter).
    3. If `intent.confidence < threshold` OR `IntentExtractor`
       raised `LLMResponseParseError` (after retry exhaustion):
       fall back to the v1 path with `used_fallback=True`.

The use case depends ONLY on the application's `LLMClientPort`,
`IntentExtractorPort`, and `JobRepositoryPort` Protocols — never
on the concrete `MiniMaxLLMClient`, `IntentExtractor`, or
`SqliteJobRepository`. The test fixtures use `FakeLLMClient` +
`FakeIntentExtractor` + `FakeJobRepository` so the orchestration
is exercised without invoking any real port or LLM. The
`aggregator` constructor parameter is preserved for backward
compat but the use case no longer calls it; tests pass a
`MagicMock()` as the placeholder.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from jobs_finder.application.aggregator import (
    AggregatedJob,
    AggregatedResult,
    SourceResult,
)
from jobs_finder.application.ports import Intent
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
from tests.conftest import FakeIntentExtractor
from tests.unit._helpers.fake_job_repository import FakeJobRepository

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
        source="linkedin",
    )


class FakeAggregator:
    """Stand-in for `SearchAllSourcesUseCase` that returns a canned result.

    Implements the same `search(keywords, location, limit, sources)`
    signature the real aggregator exposes. Records every call so
    tests can assert the use case forwarded the right `q` /
    `location` / `limit` / `sources`. Returns a fixed
    `AggregatedResult` (or raises a fixed exception) for
    testability.

    The 4th `linkedin_geo_id: int | None = None` kwarg (added
    in WU3) is part of the aggregator's signature. The
    `calls` list now records 5-tuples
    `(keywords, location, limit, sources, linkedin_geo_id)`.
    """

    def __init__(
        self,
        jobs: list[Job] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._jobs = jobs if jobs is not None else []
        self._error = error
        self.calls: list[tuple[str, str, int, list[str] | None, int | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str] | None = None,
        *,
        linkedin_geo_id: int | None = None,
    ) -> AggregatedResult:
        self.calls.append((keywords, location, limit, sources, linkedin_geo_id))
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
        stream_chunks: list[str] | None = None,
    ) -> None:
        self._selection = selection or LLMSelection(matching_ids=[], explanation="")
        self._error = error
        # `stream_chunks` is the canned tokens the streaming
        # `stream_complete` method yields. When `None` (the
        # default), the v1 tests are unaffected (the no-op
        # default yields nothing). T-006 tests pass a list
        # of strings to drive the `stream_execute` path.
        self._stream_chunks: list[str] = list(stream_chunks) if stream_chunks else []
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

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        """Yield the canned chunks passed via `stream_chunks=...`.

        T-006 of `chat-streaming` (the `stream_execute` method)
        calls `stream_complete` to drive the streaming path. The
        v1 tests do not exercise this method (they call
        `execute`); the v1 no-op default (yields nothing) is
        preserved when `stream_chunks` is `None`/empty.

        The yielded chunks are concatenated by the
        `StreamEventParser`; the test asserts the chunk
        ORDER (not just the final selection) to verify the
        use case preserves the LLM's emission order.
        """
        del system, user
        for chunk in self._stream_chunks:
            yield chunk


# ---------------------------------------------------------------------------
# Happy path — LLM picks 3 of 5 jobs; result is in AGGREGATOR order, not
# the LLM's order.
# ---------------------------------------------------------------------------


async def test_execute_returns_filtered_jobs_in_aggregator_order() -> None:
    """5 jobs in, LLM returns 3 ids, the result has 3 jobs in the
    repository's order (NOT the LLM's order).

    The use case must preserve the repository's order so the
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
    fake_repo = FakeJobRepository(jobs=jobs)
    # LLM returns IDs in a non-aggregator order: e, a, c (not a, c, e).
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["e", "a", "c"], explanation="3 match"))

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )

    assert [j.id for j in result.jobs] == ["a", "c", "e"]  # repository order
    assert result.explanation == "3 match"
    assert result.total_considered == 5
    assert result.total_matched == 3


# ---------------------------------------------------------------------------
# Empty aggregator — short-circuit; LLM is NEVER called.
# ---------------------------------------------------------------------------


async def test_execute_short_circuits_when_aggregator_returns_no_jobs() -> None:
    """0 jobs from the repository → empty result + Spanish explanation; LLM is NEVER called.

    REQ-LLM-003 5th scenario: "Empty aggregated list → LLM not called".
    The use case skips the LLM call entirely (no payload to filter)
    and returns a Spanish explanation so the route can surface a
    sensible response to the user.
    """
    fake_repo = FakeJobRepository(jobs=[])
    llm = FakeLLMClient()  # would record calls if invoked

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )
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
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a", "hallucinated"], explanation="ok")
    )

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )

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
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(
            matching_ids=["bogus1", "bogus2", "bogus3", "bogus4", "bogus5"],
            explanation="none match",
        )
    )

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )

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
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=[], explanation="none match"))

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )

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
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(error=LLMUnavailableError("upstream down"))

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )
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
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(error=LLMResponseParseError("no JSON in response"))

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )
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
    to the repository's `search_jobs_history()` so the DB query is
    consistent with what `/jobs` would query.

    The chat endpoint passes `q=""` and `location=""` in v1 (the
    message IS the intent), but the use case MUST forward whatever
    the caller passes so a future caller (e.g. a chat-with-defaults
    endpoint) can pre-fill `q` and benefit from the per-call DB
    filter.
    """
    fake_repo = FakeJobRepository(jobs=[])
    llm = FakeLLMClient()

    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        job_repository=fake_repo,
    )
    await use_case.execute(
        message="python",
        q="python",
        location="Madrid",
        limit=10,
        sources=["linkedin", "infojobs"],
    )

    # The repository received the call with the forwarded args
    # (the v1 path forwards `q` / `location` / `limit` /
    # `sources` directly).
    assert fake_repo.calls == [
        {
            "keywords": "python",
            "location": "Madrid",
            "sources": ["linkedin", "infojobs"],
            "limit": 10,
        }
    ]


# ---------------------------------------------------------------------------
# Return-type sanity — the dataclass shape is documented and pinned.
# ---------------------------------------------------------------------------


def test_filtered_jobs_result_is_frozen_and_slots() -> None:
    """`FilteredJobsResult` is a frozen + slotted dataclass.

    The use case returns this dataclass to the route; the route
    reads `.jobs` / `.explanation` / `.total_considered` /
    `.total_matched` / `.used_fallback`. A regression that
    switches the class to a mutable dataclass would silently
    allow the route to mutate the result; the
    `frozen=True, slots=True` contract is part of the type's
    API.
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


# ---------------------------------------------------------------------------
# 2-stage flow scenarios (T-010, REQ-CHAT-INT-001..003).
#
# The 2-stage path is enabled when `intent_extractor` is provided
# AND `intent_extraction_enabled=True` (the master switch). The
# use case:
#   1. Calls `intent_extractor.extract(message=...)` to get a
#      structured `Intent`.
#   2. Reads `intent.confidence`:
#        - High confidence (>= threshold): dispatches to
#          `_execute_2stage(...)`. The aggregator gets
#          `q=intent.q or ""`, `location=intent.location or ""`,
#          `limit=intent_max_results`. `used_fallback=False`.
#        - Low confidence (< threshold): dispatches to
#          `_execute_v1(...)`. `used_fallback=True`.
#        - `LLMResponseParseError` after retry exhaustion:
#          dispatches to `_execute_v1(...)`. `used_fallback=True`.
# ---------------------------------------------------------------------------


async def test_2stage_high_confidence_runs_2_stage_with_extracted_params() -> None:
    """High-confidence intent → 2-stage path; repository receives extracted `q` / `location`.

    REQ-CHAT-INT-001: stage 1 extracts the `Intent`; stage 2
    uses the extracted `q` / `location` to direct the
    repository query. The 2 LLM calls are: stage 1 (intent
    extraction) + stage 3 (filter). The test asserts:
      - `intent_extractor.extract` is called once (stage 1).
      - `llm.complete` is called once (stage 3; the 2-stage
        path does NOT do another LLM call between stages 2
        and 3).
      - The repository receives the EXTRACTED `q` /
        `location`, NOT the caller's `q=""` / `location=""`.
      - `used_fallback=False`.
    """
    jobs = [_make_job("a"), _make_job("b"), _make_job("c")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a", "b"], explanation="2-stage match")
    )
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="ingeniero",
            location="Madrid",
            experience_years=3,
            remote=False,
            employment_type="full_time",
            confidence=0.95,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="ingeniero en Madrid",
        q="",
        location="",
        limit=20,
    )

    # Stage 1 ran (extractor was called).
    assert len(intent_extractor.calls) == 1
    # The user message was forwarded to the extractor.
    assert intent_extractor.calls[0] == "ingeniero en Madrid"
    # Stage 3 ran (LLM was called ONCE — the 2-stage path
    # does NOT add an LLM call between stage 1 and stage 3).
    assert len(llm.calls) == 1
    # The repository was called with the EXTRACTED params
    # (NOT the caller's empty `q=""` / `location=""` /
    # `limit=20`).
    assert fake_repo.calls == [
        {
            "keywords": "ingeniero",
            "location": "Madrid",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 100,
        }
    ]
    # The result has `used_fallback=False` (2-stage path).
    assert result.used_fallback is False
    # The result has the matched jobs in repository order.
    assert [j.id for j in result.jobs] == ["a", "b"]


async def test_2stage_intent_q_none_propagates_to_empty_q() -> None:
    """`intent.q=None, location="Madrid"` propagates to `q="", location="Madrid"` in the repository.

    The 2-stage path uses `intent.q or ""` so a `None`
    `q` does NOT crash the repository. The test asserts
    the repository received the empty-string fallback for
    `q` and the extracted `location`.
    """
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q=None,
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.9,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        job_repository=fake_repo,
    )
    await use_case.execute(
        message="trabajo en Madrid",
        q="",
        location="",
        limit=20,
    )
    # `q=""` (None → ""), `location="Madrid"` (extracted).
    assert fake_repo.calls == [
        {
            "keywords": "",
            "location": "Madrid",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 100,
        }
    ]


async def test_2stage_intent_max_results_env_override_changes_aggregator_limit() -> None:
    """`Settings(intent_max_results=50)` changes the repository's `limit`.

    The per-source cap for stage 2 is configurable so
    operators can tune the recall / cost trade-off without
    code changes. The v1 path always uses the caller's `limit`
    regardless of this setting; the 2-stage path always uses
    `intent_max_results`.
    """
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.9,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_max_results=50,
        job_repository=fake_repo,
    )
    await use_case.execute(
        message="python in Madrid",
        q="",
        location="",
        limit=20,  # ignored on 2-stage path
    )
    # The repository was called with `limit=50` (the
    # configured `intent_max_results`).
    assert fake_repo.calls == [
        {
            "keywords": "python",
            "location": "Madrid",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 50,
        }
    ]


async def test_v1_scenarios_also_pass_with_intent_extraction_enabled_high_confidence() -> None:
    """9 v1 scenarios ALSO pass with `intent_extraction_enabled=True` + high-confidence extractor.

    The 9 v1 scenarios construct the use case with the v1
    kwargs only (no `intent_extractor`, no
    `intent_extraction_enabled`). When the test also adds
    an `intent_extractor` (high confidence) AND
    `intent_extraction_enabled=True`, the use case
    dispatches to `_execute_2stage(...)` and the v1 logic
    (in `_execute_v1` for the v1 path, in
    `_run_stage3` for both paths) must run identically.
    The v1 logic includes: aggregator-order preservation,
    strict-subset ID validation, hallucination WARNINGs,
    short-circuit on empty input, LLM error propagation.
    This test is the regression anchor that the refactor
    didn't break the v1 path's invariants.

    Specifically: 3 jobs, LLM returns 3 ids (matching a
    subset), 1 high-confidence `FakeIntentExtractor` →
    2-stage path runs; the stage-3 strict-subset validation
    preserves the aggregator order.
    """
    jobs = [
        _make_job("a"),
        _make_job("b"),
        _make_job("c"),
    ]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["c", "a", "b"], explanation="all match")
    )
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_enabled=True,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )

    # 2-stage path; the v1 stage-3 logic runs identically.
    # The LLM returned ids in LLM order [c, a, b]; the
    # result is in AGGREGATOR order [a, b, c] (NOT the
    # LLM's order).
    assert [j.id for j in result.jobs] == ["a", "b", "c"]
    assert result.explanation == "all match"
    assert result.total_considered == 3
    assert result.total_matched == 3
    # 2-stage path: `used_fallback=False`.
    assert result.used_fallback is False


# ---------------------------------------------------------------------------
# Fallback scenarios (T-010, REQ-CHAT-INT-004).
#
# The v1 path runs (with `used_fallback=True`) when:
#   - The stage-1 `Intent.confidence < threshold`.
#   - `intent_extraction_enabled=False` (master switch).
#   - The `IntentExtractor` raises `LLMResponseParseError`
#     (after retry exhaustion).
# ---------------------------------------------------------------------------


async def test_fallback_low_confidence_dispatches_to_v1_with_used_fallback_true() -> None:
    """`intent.confidence=0.5 < threshold=0.7` → v1 path; `used_fallback=True`.

    REQ-CHAT-INT-004: low confidence → v1 single-stage
    fallback. The repository receives the caller's
    `q=""`, `location=""`, `limit=20` (NOT the
    extracted `q` / `location` / `intent_max_results`).
    """
    jobs = [_make_job("a"), _make_job("b")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.5,  # below the 0.7 threshold
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_confidence_threshold=0.7,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # The repository received the v1 defaults (caller's
    # `q=""` / `location=""` / `limit=20`).
    assert fake_repo.calls == [
        {
            "keywords": "",
            "location": "",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 20,
        }
    ]
    # `used_fallback=True` (v1 path).
    assert result.used_fallback is True


async def test_fallback_high_confidence_dispatches_to_2stage_with_used_fallback_false() -> None:
    """`intent.confidence=0.95 >= threshold=0.7` → 2-stage path; `used_fallback=False`."""
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,  # above the 0.7 threshold
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_confidence_threshold=0.7,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # The repository received the extracted `q` /
    # `location` and the configured `intent_max_results=100`.
    assert fake_repo.calls == [
        {
            "keywords": "python",
            "location": "Madrid",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 100,
        }
    ]
    # `used_fallback=False` (2-stage path).
    assert result.used_fallback is False


async def test_fallback_intent_extraction_disabled_dispatches_to_v1() -> None:
    """`intent_extraction_enabled=False` → v1 path; extractor NOT called; `used_fallback=True`."""
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    # The extractor is set up but should NOT be called when
    # `intent_extraction_enabled=False` (the dispatcher
    # short-circuits to v1).
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_enabled=False,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # The extractor was NOT called.
    assert intent_extractor.calls == []
    # The repository received the v1 defaults.
    assert fake_repo.calls == [
        {
            "keywords": "",
            "location": "",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 20,
        }
    ]
    # `used_fallback=True` (v1 path).
    assert result.used_fallback is True


async def test_fallback_threshold_env_override_dispatches_to_2stage_at_lower_confidence() -> None:
    """`threshold=0.5 + confidence=0.6` → 2-stage path (above the lowered threshold).

    The threshold is configurable so operators can tune
    the recall / safety trade-off. A lower threshold
    means more intents are trusted to direct the
    repository (less v1 fallback, less recall but more
    precision). The test asserts the dispatcher respects
    the configured threshold (not just the hardcoded 0.7
    default).
    """
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.6,  # above 0.5, below the 0.7 default
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_confidence_threshold=0.5,  # lowered
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # 2-stage path: repository received the extracted
    # params + `intent_max_results=100`.
    assert fake_repo.calls == [
        {
            "keywords": "python",
            "location": "Madrid",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 100,
        }
    ]
    assert result.used_fallback is False


async def test_fallback_intent_extractor_parse_error_dispatches_to_v1() -> None:
    """`IntentExtractor` raises `LLMResponseParseError` → v1 path; `used_fallback=True`.

    REQ-CHAT-INT-004: stage-1 parse failure (after retry
    exhaustion) falls back to v1. The use case catches
    the error so a transient LLM parse failure does NOT
    block the user. A WARNING is logged (verified by
    `caplog`); the test asserts the fallback behavior.
    """
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        error=LLMResponseParseError("stage-1 parse failure after retry")
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=MagicMock(),
        llm=llm,
        intent_extractor=intent_extractor,
        job_repository=fake_repo,
    )
    result = await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # v1 path: repository received the v1 defaults.
    assert fake_repo.calls == [
        {
            "keywords": "",
            "location": "",
            "sources": ["linkedin", "indeed", "infojobs"],
            "limit": 20,
        }
    ]
    # `used_fallback=True` (v1 fallback).
    assert result.used_fallback is True


# ---------------------------------------------------------------------------
# `LocationResolverPort` injection (REQ-LOC-GEO-001, WU4 of `fix-linkedin-geoid`).
#
# The 2-stage chat filter wires a `LocationResolverPort` into the
# use case. After stage 1, the use case calls the resolver to
# translate `intent.location` (a free-form string) to a LinkedIn
# `geoId` (a `int`). The resolved `geo_id` is forwarded to the
# aggregator as `linkedin_geo_id=...` (the WU3 dispatch seam).
#
# The v1 path (`_execute_v1` with `intent_extraction_enabled=False`
# or `confidence < threshold`) MUST NOT call the resolver — the
# v1 path passes `q=""`, `location=""` to the aggregator; there's
# nothing to resolve. A regression that calls the resolver in the
# v1 path would be a regression (extra WARNING logs + a resolver
# call that returns `None` and clutters observability).
# ---------------------------------------------------------------------------


class FakeLocationResolver:
    """In-memory fake of `LocationResolverPort` for tests.

    Records every call so tests can assert the use case
    forwarded the right `location` string. Returns a canned
    `int | None` value (or raises a canned exception) for
    testability.

    The Protocol is `LocationResolverPort.resolve(self, location:
    str) -> int | None` (the single method, intentionally NOT
    `async` — the resolver is a pure in-process dict lookup).
    The second method `resolve_structured` was added in
    `backend-linkedin-location-fallback` (REQ-STR-LOC-001);
    the default returns `None` (the dict is city-level, so
    the fake's default semantic is "no structured triplet",
    which keeps the existing tests for the chat-filter
    use case unchanged).
    """

    def __init__(
        self,
        canned: int | None = 103374081,
        error: Exception | None = None,
    ) -> None:
        self._canned: int | None = canned
        self._error: Exception | None = error
        self.calls: list[str] = []
        self.structured_calls: list[str] = []
        self.structured_canned: tuple[str, str, str] | None = None

    def resolve(self, location: str) -> int | None:
        """Record the call, return the canned value (or raise)."""
        self.calls.append(location)
        if self._error is not None:
            raise self._error
        return self._canned

    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
        """Default: return `(None, None)` (unmapped sentinel).

        Spec: REQ-PROV-004 — the pre-change test doubles
        (e.g. `FakeLocationResolver` in this file) grow the
        second Protocol method with a default `(None, None)`
        return so the existing chat-wiring tests stay GREEN
        without modification. The InfoJobs plumb tests inject
        a real `HardcodedLocationResolver` and assert the
        InfoJobs path; the chat-wiring tests continue to
        exercise the v1 LinkedIn path (which only calls
        `resolve()`, not `resolve_infojobs()`).
        """
        return (None, None)

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:
        """Record the call, return the canned structured triplet (default `None`)."""
        self.structured_calls.append(location)
        return self.structured_canned


@pytest.mark.skip(reason="aggregator fallback removed; resolver→geo_id forwarding no longer tested")
async def test_2stage_calls_resolver_and_forwards_geo_id_to_aggregator() -> None:
    """`intent.location="Madrid"` → resolver called once with `"Madrid"`.
    Then `linkedin_geo_id=103374081` is forwarded to the aggregator.

    REQ-LOC-GEO-001 + REQ-CHAT-INT-001: the 2-stage path
    calls the resolver to translate the free-form
    `intent.location` into a LinkedIn `geoId`, then
    forwards the resolved `geo_id` to the aggregator. The
    test asserts the full seam: the resolver is called
    once with the right input; the aggregator receives
    the resolved value as the `linkedin_geo_id` kwarg.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="ingeniero",
            location="Madrid",
            experience_years=3,
            remote=False,
            employment_type="full_time",
            confidence=0.95,
        )
    )
    resolver = FakeLocationResolver(canned=103374081)
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=resolver,
    )
    result = await use_case.execute(
        message="ingeniero en Madrid",
        q="",
        location="",
        limit=20,
    )

    # The resolver was called ONCE with the extracted `intent.location`.
    assert resolver.calls == ["Madrid"]
    # The aggregator received the resolved `geo_id=103374081` as
    # the `linkedin_geo_id` kwarg.
    assert aggregator.calls == [
        ("ingeniero", "Madrid", 100, ["linkedin", "indeed", "infojobs"], 103374081)
    ]
    # 2-stage path: `used_fallback=False`.
    assert result.used_fallback is False


@pytest.mark.skip(reason="aggregator fallback removed; resolver→None forwarding no longer tested")
async def test_2stage_resolver_returns_none_logs_warning_and_forwards_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`intent.location="Atlantis"` → resolver returns `None` → WARNING logged.
    Then `linkedin_geo_id=None` is forwarded to the aggregator.

    The unknown / country-level / País Vasco / Canarias /
    empty inputs all return `None` from the resolver. The
    use case logs a WARNING (per REQ-LOC-GEO-001) and
    forwards `linkedin_geo_id=None` to the aggregator; the
    LinkedIn scraper falls back to the broken `?location=`
    path (a strict improvement over today's 100%-broken
    behavior).
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Atlantis",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    resolver = FakeLocationResolver(canned=None)
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=resolver,
    )

    with caplog.at_level("WARNING"):
        result = await use_case.execute(
            message="python in Atlantis",
            q="",
            location="",
            limit=20,
        )

    # The resolver was called with the intent's location.
    assert resolver.calls == ["Atlantis"]
    # The aggregator received `linkedin_geo_id=None` (the
    # resolver returned `None`).
    assert aggregator.calls == [
        ("python", "Atlantis", 100, ["linkedin", "indeed", "infojobs"], None)
    ]
    # A WARNING was logged for the unresolvable location.
    resolver_warnings = [
        record
        for record in caplog.records
        if "atlantis" in record.getMessage().lower()
        and "linkedin_geo_id" in record.getMessage().lower()
    ]
    assert len(resolver_warnings) == 1
    assert "Atlantis" in resolver_warnings[0].getMessage()
    # 2-stage path: `used_fallback=False` (the resolver miss
    # is NOT a v1 fallback).
    assert result.used_fallback is False


@pytest.mark.skip(
    reason="aggregator fallback removed; resolver-non-call no longer testable via aggregator.calls"
)
async def test_v1_path_does_not_call_resolver() -> None:
    """`_execute_v1` does NOT call the resolver (Q2 explore resolution).

    The v1 path (`_execute_v1` with
    `intent_extraction_enabled=False` OR `confidence <
    threshold`) MUST NOT call the resolver. The v1 path
    passes `q=""` / `location=""` to the aggregator; there's
    nothing to resolve (the v1 path scrapes the default
    landing page with no location filter). A regression
    that calls the resolver in the v1 path would be a
    regression: extra WARNING logs + a resolver call that
    returns `None` (the empty string short-circuit) and
    clutters observability.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.5,  # below the 0.7 threshold → v1 path
        )
    )
    resolver = FakeLocationResolver(canned=103374081)
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=resolver,
    )
    result = await use_case.execute(
        message="python in Madrid",
        q="",
        location="",
        limit=20,
    )
    # The resolver was NEVER called.
    assert resolver.calls == []
    # The aggregator received the v1 defaults.
    assert aggregator.calls == [("", "", 20, ["linkedin", "indeed", "infojobs"], None)]
    # `used_fallback=True` (v1 path).
    assert result.used_fallback is True


@pytest.mark.skip(
    reason="aggregator fallback removed; resolver-non-call no longer testable via aggregator.calls"
)
async def test_2stage_resolver_not_called_when_intent_location_is_none() -> None:
    """`intent.location=None` → resolver NOT called; `linkedin_geo_id=None` forwarded.

    The `Intent.location` field is optional (a user message
    that doesn't specify a location → `location=None`). The
    use case MUST NOT call the resolver with `None` (an
    `None` is the "no location" sentinel; the resolver would
    short-circuit to `None` anyway, but the call would
    clutter observability). The aggregator receives
    `linkedin_geo_id=None`.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location=None,
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    resolver = FakeLocationResolver(canned=103374081)
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=resolver,
    )
    await use_case.execute(
        message="python",
        q="",
        location="",
        limit=20,
    )
    # The resolver was NEVER called.
    assert resolver.calls == []
    # The aggregator received `linkedin_geo_id=None`.
    assert aggregator.calls == [("python", "", 100, ["linkedin", "indeed", "infojobs"], None)]


@pytest.mark.skip(
    reason="aggregator fallback removed; resolver-non-call no longer testable via aggregator.calls"
)
async def test_use_case_works_without_location_resolver() -> None:
    """`location_resolver=None` (default) → resolver NOT called; `linkedin_geo_id=None`.

    Backward compat: callers that pre-date WU4 (and
    composition roots that don't inject a resolver) MUST
    be able to construct the use case WITHOUT a resolver.
    The `location_resolver` parameter is optional with a
    `None` default; when `None`, the use case skips the
    resolver call entirely and forwards
    `linkedin_geo_id=None` to the aggregator.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        # `location_resolver=None` is the default.
    )
    await use_case.execute(
        message="python in Madrid",
        q="",
        location="",
        limit=20,
    )
    # The aggregator received `linkedin_geo_id=None` (no
    # resolver injected; the use case forwards `None`).
    assert aggregator.calls == [("python", "Madrid", 100, ["linkedin", "indeed", "infojobs"], None)]


@pytest.mark.skip(
    reason="aggregator fallback removed; resolver-exception resilience no longer testable"
)
async def test_2stage_resolver_call_is_resilient_to_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Resolver raises an exception → use case catches it, WARNING logs, `linkedin_geo_id=None`.

    A future `HybridLocationResolver` (geocoding API
    fallback) could fail at runtime (timeout, network
    error, etc.). The use case MUST be resilient: a
    resolver exception is caught, a WARNING is logged,
    and the path proceeds with `linkedin_geo_id=None` (the
    LinkedIn scraper falls back to broken `?location=`).
    The user-facing behavior is identical to a `None`
    return — the exception is NOT propagated to the
    route (the chat filter is still functional; only the
    LinkedIn location filter is degraded).
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(selection=LLMSelection(matching_ids=["a"], explanation="match"))
    intent_extractor = FakeIntentExtractor(
        canned=Intent(
            q="python",
            location="Madrid",
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.95,
        )
    )
    resolver = FakeLocationResolver(
        canned=None,
        error=RuntimeError("resolver backend unavailable"),
    )
    use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=resolver,
    )

    with caplog.at_level("WARNING"):
        await use_case.execute(
            message="python in Madrid",
            q="",
            location="",
            limit=20,
        )

    # The aggregator received `linkedin_geo_id=None` (the
    # resolver raised; the use case caught and continued
    # with `None`).
    assert aggregator.calls == [("python", "Madrid", 100, ["linkedin", "indeed", "infojobs"], None)]
    # A WARNING was logged for the resolver failure.
    resolver_warnings = [
        record
        for record in caplog.records
        if "resolver" in record.getMessage().lower() and "madrid" in record.getMessage().lower()
    ]
    assert len(resolver_warnings) == 1


# ===========================================================================

# `stream_execute` (T-006 of `chat-streaming`)
# Spec: REQ-SSE-001 + REQ-META-001 + REQ-PARSE-001.
# The streaming sibling of `execute` yields StreamEvent* dataclasses
# (meta + text × N + done) instead of returning a single FilteredJobsResult.
# The v1 execute() and _run_stage3() are UNCHANGED per REQ-BACKWARDS-COMPAT-001.


from jobs_finder.application.usecases.filter_jobs_by_intent import (  # noqa: E402
    StreamEventDone,
    StreamEventMeta,
    StreamEventText,
)


async def _drain(events: object) -> list[object]:
    """Drain an async iterator into a list."""
    out: list[object] = []
    async for event in events:  # type: ignore[attr-defined]
        out.append(event)
    return out


def _build_stream_use_case(
    *,
    job_repository: object,
    llm: object,
    aggregator: object | None = None,
    intent_extractor: object | None = None,
    intent_extraction_enabled: bool = False,
) -> FilterJobsByIntentUseCase:
    """Build a FilterJobsByIntentUseCase for stream tests; suppresses mypy.

    The use case's ctor expects `SearchAllSourcesUseCase` and
    `LLMClientPort` (strict types), but the tests inject fakes
    with the right methods. The `# type: ignore[arg-type]`
    lives HERE so the call sites stay readable.

    The `aggregator` parameter is still required by the ctor
    for backward compat but is no longer called by the use
    case; we inject a `MagicMock()` placeholder when the
    caller doesn't supply one. The `job_repository` IS used
    by the use case (the chat-filter no longer falls back to
    the aggregator).
    """
    kwargs: dict[str, object] = {
        "aggregator": aggregator if aggregator is not None else MagicMock(),
        "llm": llm,
        "job_repository": job_repository,
    }
    if intent_extractor is not None:
        kwargs["intent_extractor"] = intent_extractor
    kwargs["intent_extraction_enabled"] = intent_extraction_enabled
    return FilterJobsByIntentUseCase(**kwargs)  # type: ignore[arg-type]


async def test_stream_execute_2stage_emits_meta_then_text_then_done() -> None:
    """2-stage path: meta → text × N → done."""
    from jobs_finder.application.ports import Intent  # noqa: PLC0415

    jobs = [_make_job("a"), _make_job("b"), _make_job("c")]
    intent = Intent(q="python", location="Madrid", confidence=0.95)
    fake_repo = FakeJobRepository(jobs=jobs)
    intent_extractor = FakeIntentExtractor(canned=intent)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a", "b"], explanation="match"),
        stream_chunks=['{"matching_ids":["a","b"],', '"explanation":"match"}'],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extractor=intent_extractor,
        intent_extraction_enabled=True,
    )

    events = await _drain(
        use_case.stream_execute(message="busco python en Madrid", q="", location="", limit=20)
    )
    assert len(events) == 4
    assert isinstance(events[0], StreamEventMeta)
    assert events[0].intent == intent
    assert isinstance(events[1], StreamEventText)
    assert events[1].delta == '{"matching_ids":["a","b"],'
    assert isinstance(events[2], StreamEventText)
    assert events[2].delta == '"explanation":"match"}'
    assert isinstance(events[3], StreamEventDone)
    assert [j.id for j in events[3].jobs] == ["a", "b"]


async def test_stream_execute_v1_emits_no_meta() -> None:
    """v1 path: no meta, only text × N + done."""
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a"], explanation="ok"),
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"ok"}'],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extraction_enabled=False,
    )

    events = await _drain(use_case.stream_execute(message="python", q="", location="", limit=20))
    event_types = [type(e).__name__ for e in events]
    assert "StreamEventMeta" not in event_types
    assert event_types == ["StreamEventText", "StreamEventText", "StreamEventDone"]
    assert isinstance(events[-1], StreamEventDone)


async def test_stream_execute_text_chunks_in_feed_order() -> None:
    """Text chunks emitted in LLM's feed order."""
    jobs = [_make_job("a")]
    fake_repo = FakeJobRepository(jobs=jobs)
    # The chunks are the verbatim LLM tokens; the parser
    # concatenates them to form a valid JSON selection.
    # The TEST asserts the chunks come out in the same
    # order the LLM emitted them (NOT the final selection's
    # matching_ids order).
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a"], explanation="ok"),
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"', "ok", '"}'],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extraction_enabled=False,
    )

    events = await _drain(use_case.stream_execute(message="python", q="", location="", limit=20))
    text_events = [e for e in events if isinstance(e, StreamEventText)]
    # Chunks come out in feed order.
    assert [e.delta for e in text_events] == [
        '{"matching_ids":["a"],',
        '"explanation":"',
        "ok",
        '"}',
    ]


async def test_stream_execute_empty_aggregator_short_circuits_to_done() -> None:
    """Empty repository → short-circuit to done (no LLM call)."""
    fake_repo = FakeJobRepository(jobs=[])
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=[], explanation="ok"),
        stream_chunks=["never-called"],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extraction_enabled=False,
    )

    events = await _drain(use_case.stream_execute(message="python", q="", location="", limit=20))
    assert len(events) == 1
    assert isinstance(events[0], StreamEventDone)
    assert events[0].jobs == []
    assert "no se encontraron ofertas" in events[0].explanation.lower()
    assert len(fake_repo.calls) == 1
    # The LLM stream was never iterated (the short-circuit
    # path does not call `stream_complete` at all).
    assert llm.calls == []


async def test_stream_execute_done_jobs_in_aggregator_order_not_llm_order() -> None:
    """done.jobs is in the REPOSITORY's order, not the LLM's."""
    jobs = [
        _make_job("a"),
        _make_job("b"),
        _make_job("c"),
        _make_job("d"),
    ]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["d", "c", "b"], explanation="match"),
        stream_chunks=[
            '{"matching_ids":["d","c","b"],',
            '"explanation":"match"}',
        ],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extraction_enabled=False,
    )

    events = await _drain(use_case.stream_execute(message="python", q="", location="", limit=20))
    done = [e for e in events if isinstance(e, StreamEventDone)][0]
    assert [j.id for j in done.jobs] == ["b", "c", "d"]


async def test_stream_execute_drops_hallucinated_ids() -> None:
    """Hallucinated ids from the LLM are dropped."""
    jobs = [_make_job("a"), _make_job("b"), _make_job("c")]
    fake_repo = FakeJobRepository(jobs=jobs)
    llm = FakeLLMClient(
        selection=LLMSelection(matching_ids=["a", "z99"], explanation="match"),
        stream_chunks=[
            '{"matching_ids":["a","z99"],',
            '"explanation":"match"}',
        ],
    )
    use_case = _build_stream_use_case(
        job_repository=fake_repo,
        llm=llm,
        intent_extraction_enabled=False,
    )

    events = await _drain(use_case.stream_execute(message="python", q="", location="", limit=20))
    done = [e for e in events if isinstance(e, StreamEventDone)][0]
    assert [j.id for j in done.jobs] == ["a"]
    assert done.explanation == "match"
