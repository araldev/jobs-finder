"""Integration tests for the `POST /jobs/chat` endpoint (T-017 of `ai-chat-filter`).

Spec: REQ-CHAT-001 (chat request/response), REQ-CHAT-002 (per-user
rate limit), REQ-LLM-003 (strict-subset ID validation, end-to-end).

The integration test is the FULL ROUNDTRIP exercise of the chat
feature: a `FakeLLMClient` (Protocol-conforming) is injected
into the app via `app.state.filter_use_case` override; a real
FastAPI app is built; an `httpx.AsyncClient` makes a real
`POST /jobs/chat` request; the response is asserted end-to-end
(body shape, status code, error mapping).

The 6 test scenarios cover the spec's chat-endpoint contract
plus the LLM error paths:

  1. Happy path: 5 jobs, LLM picks 3 → 200 with `ChatResponse`.
  2. Empty result: aggregator returns 0 jobs → 200 with
     `explanation="no se encontraron..."` and 0 jobs.
  3. LLM unavailable: `FakeLLMClient` raises `LLMUnavailableError`
     → 502.
  4. LLM parse error: `FakeLLMClient` returns malformed JSON
     → 422 (the route's local catch).
  5. Message too long: 1234 chars with `max_message_chars=1000`
     → 400 with the documented detail.
  6. Hallucinated IDs: `FakeLLMClient` returns IDs not in the
     aggregator result → only valid IDs in the response
     (REQ-LLM-003 end-to-end: the use case drops the bad IDs,
     the route forwards only the valid ones).

The test seam: a custom `build_chat_test_app` helper that
builds an app with the chat feature enabled + a
`FakeLLMClient` injected via `app.state.filter_use_case`. The
`app_factory.build_app` production wiring is bypassed for the
LLM client (we want a fake, not a real `MiniMaxLLMClient`).
The 3 source routes are wired to `FakeJobSearchPort` instances
so the aggregator returns canned jobs.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import JobSearchCacheKey, LLMClientPort
from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
)
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
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.llm.exceptions import LLMUnavailableError
from jobs_finder.presentation.middleware import RequestIdMiddleware
from jobs_finder.presentation.routes import chat as chat_routes
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_job(job_id: str, title: str = "Software Engineer") -> Job:
    """Build a `Job` with a unique id and a sensible default shape."""
    return Job(
        id=job_id,
        title=title,
        company=f"Co-{job_id}",
        location="Madrid",
        url=f"https://example.com/jobs/{job_id}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="linkedin",
    )


class FakeLLMClient:
    """A `LLMClientPort` that returns canned responses (or raises).

    The fake short-circuits the parser by returning a clean
    JSON string (the use case's parser runs on the returned
    string, just like in production). Tests that exercise
    error paths raise a fixed exception. Tests that exercise
    parse-error paths return a malformed string (the parser
    raises `LLMResponseParseError`).
    """

    def __init__(
        self,
        matching_ids: list[str] | None = None,
        explanation: str = "ok",
        error: Exception | None = None,
        raw_response: str | None = None,
    ) -> None:
        self._matching_ids = matching_ids or []
        self._explanation = explanation
        self._error = error
        self._raw_response = raw_response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._error is not None:
            raise self._error
        if self._raw_response is not None:
            return self._raw_response
        return json.dumps(
            {
                "matching_ids": list(self._matching_ids),
                "explanation": self._explanation,
            }
        )

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        """No-op `stream_complete` for `LLMClientPort` Protocol conformance (T-003).

        The v1 chat tests do not exercise the streaming
        endpoint; this default yields nothing so a v1 caller
        that iterates the stream gets an empty generator.
        """
        del system, user
        if False:  # pragma: no cover — yields nothing
            yield ""


def _build_chat_test_app(
    *,
    jobs: list[Job],
    llm: LLMClientPort,
    max_message_chars: int = 1000,
) -> FastAPI:
    """Build a FastAPI app with the chat feature wired + the fake LLM injected.

    The 3 source use cases are wired to a single shared
    `FakeJobSearchPort` primed with the `jobs` list so the
    aggregator returns those jobs for any query. The
    `FilterJobsByIntentUseCase` is built with the existing
    `SearchAllSourcesUseCase` + the injected `FakeLLMClient`.
    The chat route is registered (no conditional — the test
    always wants the chat endpoint). The `ChatRateLimitMiddleware`
    is NOT mounted (T-015 covers it; this file is about the
    route + use case roundtrip).
    """
    port = FakeJobSearchPort(jobs=jobs)
    cache: InMemoryTTLCache[JobSearchCacheKey, list[Job]] = InMemoryTTLCache(ttl_seconds=60.0)
    linkedin_uc = SearchLinkedInJobsUseCase(port=port, cache=cache, source="linkedin")
    indeed_uc = IndeedSearchJobsUseCase(port=port, cache=cache, source="indeed")
    infojobs_uc = InfoJobsSearchJobsUseCase(port=port, cache=cache, source="infojobs")
    aggregator = SearchAllSourcesUseCase(
        linkedin_use_case=linkedin_uc,
        indeed_use_case=indeed_uc,
        infojobs_use_case=infojobs_uc,
    )
    # The chat endpoint now queries the DB (job_repository) instead
    # of the aggregator. Wire a FakeJobRepository with the same
    # canned jobs so tests don't need a live SQLite.
    from tests.unit._helpers.fake_job_repository import (  # noqa: PLC0415
        FakeJobRepository,
    )

    repo = FakeJobRepository(jobs=jobs or [])
    chat_use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm, job_repository=repo)

    app = FastAPI()
    # Mount the chat router directly (bypassing the conditional
    # `build_app` wiring) so the test always has the chat route
    # available. The `RequestIdMiddleware` provides the 4xx/5xx
    # body's `request_id`.
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        chat_routes.build_chat_router(
            use_case=chat_use_case,
            max_message_chars=max_message_chars,
        )
    )
    # Expose the use case for diagnostic assertions.
    app.state.filter_use_case = chat_use_case
    return app


@pytest.fixture
def jobs() -> list[Job]:
    """5 sample jobs — the default for the chat endpoint tests."""
    return [
        _make_job("a", "Python Developer"),
        _make_job("b", "Java Backend"),
        _make_job("c", "Frontend React"),
        _make_job("d", "DevOps"),
        _make_job("e", "Data Engineer"),
    ]


# ---------------------------------------------------------------------------
# REQ-CHAT-001 — Happy path: 5 jobs in, LLM picks 3, response is 200 + ChatResponse
# ---------------------------------------------------------------------------


async def test_chat_endpoint_happy_path(
    jobs: list[Job],
) -> None:
    """5 jobs, LLM picks 3 → 200 with `jobs` = 3 + `explanation` + `totals`.

    The end-to-end roundtrip: the route normalizes the
    message, calls the use case, the use case delegates to
    the aggregator + LLM, the strict-subset filter drops any
    hallucinated IDs, and the route returns a `ChatResponse`
    with the filtered jobs in aggregator order.
    """
    # Replace the fixture's no-op LLM with one that picks
    # 3 valid IDs.
    llm = FakeLLMClient(
        matching_ids=["a", "c", "e"],
        explanation="3 of 5 match the user's intent",
    )
    # Re-build the app with the new LLM.
    app = _build_chat_test_app(jobs=jobs, llm=llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python or react"})

    assert response.status_code == 200
    body = response.json()
    assert [job["id"] for job in body["jobs"]] == ["a", "c", "e"]
    assert body["explanation"] == "3 of 5 match the user's intent"
    assert body["total_considered"] == 5
    assert body["total_matched"] == 3


# ---------------------------------------------------------------------------
# REQ-CHAT-001 — Empty result: 0 jobs from aggregator, no LLM call
# ---------------------------------------------------------------------------


async def test_chat_endpoint_empty_aggregator_short_circuits() -> None:
    """0 jobs from aggregator → 200 with empty `jobs` + Spanish explanation.

    The use case short-circuits: the LLM is NEVER called.
    The response carries the Spanish "no se encontraron"
    explanation so the user sees a sensible answer.
    """
    # Build a fresh app with an empty job list.
    llm = FakeLLMClient(matching_ids=[])
    app = _build_chat_test_app(jobs=[], llm=llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "anything"})

    assert response.status_code == 200
    body = response.json()
    assert body["jobs"] == []
    assert body["total_considered"] == 0
    assert body["total_matched"] == 0
    assert "no se encontraron" in body["explanation"].lower()
    # LLM was NEVER called.
    assert llm.calls == []


# ---------------------------------------------------------------------------
# REQ-LLM-001 — LLM unavailable: 502
# ---------------------------------------------------------------------------


async def test_chat_endpoint_returns_502_when_llm_unavailable(
    jobs: list[Job],
) -> None:
    """`FakeLLMClient.complete` raises `LLMUnavailableError` → 502.

    The route catches the error locally and maps to 502 with
    a descriptive `detail`. The exception's message is
    surfaced in the body so the operator can see which LLM
    failure mode fired.
    """
    llm = FakeLLMClient(error=LLMUnavailableError("upstream down"))
    app = _build_chat_test_app(jobs=jobs, llm=llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 502
    body = response.json()
    assert "LLM provider unavailable" in body["detail"]
    assert "upstream down" in body["detail"]


# ---------------------------------------------------------------------------
# REQ-LLM-002 — LLM parse error: 422 (the route-local catch)
# ---------------------------------------------------------------------------


async def test_chat_endpoint_returns_422_when_llm_response_unparseable(
    jobs: list[Job],
) -> None:
    """`FakeLLMClient.complete` returns malformed text → 422.

    The defensive parser raises `LLMResponseParseError`
    (tier 1 + tier 2 both fail on a non-JSON string). The
    route catches it locally and maps to 422 (NOT the global
    502 handler).
    """
    llm = FakeLLMClient(raw_response="this is not json at all")
    app = _build_chat_test_app(jobs=jobs, llm=llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 422
    body = response.json()
    assert "LLM response could not be parsed" in body["detail"]


# ---------------------------------------------------------------------------
# REQ-CHAT-001 (Q2) — Message cap: 400
# ---------------------------------------------------------------------------


async def test_chat_endpoint_returns_400_when_message_exceeds_cap(
    jobs: list[Job],
) -> None:
    """A 1234-char message with `max_message_chars=1000` → 400.

    The cap check runs BEFORE the use case: the aggregator +
    LLM are NEVER called. The 400 body shape is the route's
    `HTTPException` shape: `{"detail": "message exceeds 1000
    chars (got 1234)"}`.
    """
    llm = FakeLLMClient(matching_ids=["a"])
    app = _build_chat_test_app(jobs=jobs, llm=llm, max_message_chars=1000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "x" * 1234})

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "message exceeds 1000 chars (got 1234)"
    # The LLM was NEVER called (cap check runs first).
    assert llm.calls == []


# ---------------------------------------------------------------------------
# REQ-LLM-003 — Strict-subset ID validation: hallucinated IDs are dropped
# ---------------------------------------------------------------------------


async def test_chat_endpoint_drops_hallucinated_ids_end_to_end(
    jobs: list[Job],
) -> None:
    """LLM returns 1 hallucinated + 2 valid IDs → response has 2 valid jobs.

    The use case's strict-subset filter drops the
    hallucinated id and logs a WARNING. The route forwards
    only the 2 valid jobs in the response. The
    `total_considered` reflects the input count (5), the
    `total_matched` reflects the output count (2).
    """
    llm = FakeLLMClient(
        matching_ids=["a", "hallucinated_id", "c"],
        explanation="2 valid matches",
    )
    app = _build_chat_test_app(jobs=jobs, llm=llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python or react"})

    assert response.status_code == 200
    body = response.json()
    # Only `a` and `c` make it through (the hallucinated id is dropped).
    assert [job["id"] for job in body["jobs"]] == ["a", "c"]
    assert body["total_considered"] == 5
    assert body["total_matched"] == 2
    assert body["explanation"] == "2 valid matches"
