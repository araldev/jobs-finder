"""Unit tests for the `POST /jobs/chat` route (T-014 of `ai-chat-filter`).

Spec: REQ-CHAT-001 (chat request/response), REQ-CHAT-002 (per-user
rate limit — the `ChatRateLimitMiddleware` is T-015), REQ-LLM-003
(strict-subset ID validation — the use case is T-013; the route
relies on the use case to do the validation).

The route is a thin composition layer over the
`FilterJobsByIntentUseCase` (T-013). It:

  1. Reads the `ChatRequest` body (Pydantic `message: str`).
  2. Enforces the explicit char cap (`len(req.message) >
     max_message_chars` → 400 with `{"detail": "message exceeds
     N chars (got M)"}` per Q2). The cap is NOT a Pydantic
     constraint — the route raises `HTTPException(400)` so the
     rejection body shape is the route's `HTTPException` shape,
     not Pydantic's `RequestValidationError` shape.
  3. Normalizes the message: `unicodedata.normalize("NFC",
     req.message).casefold().strip()` (REQ-CHAT-001 + preflight
     cache-key normalization decision).
  4. Calls the use case's `execute(message=normalized, q="",
     location="", limit=20, sources=None)` (v1 — the message IS
     the intent; the aggregator receives empty `q` / `location`).
  5. Maps exceptions: `LLMUnavailableError` → 502 via route-local
     `HTTPException` (the global handler would map it to 502 too,
     but the route-local catch is explicit + testable);
     `LLMResponseParseError` → 422 via route-local
     `HTTPException`. Other `JobSearchError`s propagate to the
     global handler.
  6. Returns the `ChatResponse` mapped from the
     `FilteredJobsResult` (jobs via `to_response(...)`,
     explanation, total_considered, total_matched).

The test seam: a minimal `FastAPI` app that mounts the chat
router, with the use case overridden via `dependency_overrides`.
The tests use `httpx.AsyncClient` + `ASGITransport` (the
project's standard pattern — `TestClient` is deprecated by
Starlette; see `test_app_lifespan.py` for the precedent).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, FastAPI

from jobs_finder.application.aggregator import (
    AggregatedJob,
    AggregatedResult,
    SourceResult,
)
from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.llm._parser import LLMSelection
from jobs_finder.infrastructure.llm.exceptions import (
    LLMResponseParseError,
    LLMUnavailableError,
)
from jobs_finder.presentation.middleware import RequestIdMiddleware
from jobs_finder.presentation.routes.chat import build_chat_router

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_job(job_id: str) -> Job:
    """Build a `Job` with a unique id and a sensible default shape."""
    return Job(
        id=job_id,
        title="Software Engineer",
        company=f"Co-{job_id}",
        location="Madrid",
        url=f"https://example.com/jobs/{job_id}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeLLMClient:
    """An in-memory `LLMClientPort` for tests.

    Returns a fixed JSON string (so the use case's parser runs
    end-to-end on a canned response). Tests that exercise
    error paths raise a fixed exception.
    """

    def __init__(
        self,
        matching_ids: Iterable[str] = (),
        explanation: str = "ok",
        error: Exception | None = None,
    ) -> None:
        self._selection = LLMSelection(matching_ids=list(matching_ids), explanation=explanation)
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

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        """No-op `stream_complete` for `LLMClientPort` Protocol conformance (T-003)."""
        del system, user
        if False:  # pragma: no cover — yields nothing
            yield ""


class FakeAggregator:
    """Stand-in for `SearchAllSourcesUseCase` that returns canned jobs."""

    def __init__(self, jobs: list[Job]) -> None:
        self._jobs = jobs
        self.calls: list[tuple[str, str, int, list[str] | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str] | None = None,
    ) -> AggregatedResult:
        self.calls.append((keywords, location, limit, sources))
        return AggregatedResult(
            jobs=[AggregatedJob(job=j, sources=["linkedin"]) for j in self._jobs],
            per_source={
                "linkedin": SourceResult(source="linkedin", jobs=self._jobs, cache_status="MISS")
            },
            cache_statuses={"linkedin": "MISS"},
        )


def _build_test_app(
    *,
    use_case: FilterJobsByIntentUseCase,
    max_message_chars: int = 1000,
) -> FastAPI:
    """Build a minimal `FastAPI` app that mounts the chat router.

    The app installs `RequestIdMiddleware` so the 502/422/400
    bodies can read `request.state.request_id` if needed. The
    `ChatRateLimitMiddleware` is NOT installed — the route unit
    tests are isolated to the route handler. T-015 covers the
    middleware in isolation.
    """
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    router = build_chat_router(use_case=use_case, max_message_chars=max_message_chars)
    app.include_router(router)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    """Build an `httpx.AsyncClient` bound to the in-process ASGI app."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_chat_route_returns_200_with_filtered_jobs() -> None:
    """`POST /jobs/chat` with a valid message returns 200 + `ChatResponse`.

    The 5 jobs are passed in via the fake aggregator; the LLM
    picks 3; the route returns those 3 in the `jobs` field +
    the LLM's explanation + the totals.
    """
    jobs = [
        _make_job("a"),
        _make_job("b"),
        _make_job("c"),
        _make_job("d"),
        _make_job("e"),
    ]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(matching_ids=["a", "c", "e"], explanation="3 match")
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    app = _build_test_app(use_case=use_case, max_message_chars=1000)
    async with _client(app) as client:
        response = await client.post("/jobs/chat", json={"message": "python junior"})

    assert response.status_code == 200
    body = response.json()
    assert [job["id"] for job in body["jobs"]] == ["a", "c", "e"]
    assert body["explanation"] == "3 match"
    assert body["total_considered"] == 5
    assert body["total_matched"] == 3


# ---------------------------------------------------------------------------
# Char cap — 400 with the documented body shape
# ---------------------------------------------------------------------------


async def test_chat_route_returns_400_when_message_exceeds_cap() -> None:
    """A 1234-char message with `max_message_chars=1000` → 400 + descriptive detail.

    Q2 spec resolution: the rejection body shape is the route's
    `HTTPException` shape: `{"detail": "message exceeds 1000 chars
    (got 1234)"}`. The aggregator and LLM are NEVER called (the
    cap check runs FIRST).
    """
    aggregator = FakeAggregator(jobs=[])
    llm = FakeLLMClient()
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    app = _build_test_app(use_case=use_case, max_message_chars=1000)
    async with _client(app) as client:
        response = await client.post("/jobs/chat", json={"message": "x" * 1234})

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "message exceeds 1000 chars (got 1234)"
    # The aggregator was NEVER called (cap check runs first).
    assert aggregator.calls == []
    # The LLM was NEVER called.
    assert llm.calls == []


# ---------------------------------------------------------------------------
# NFC + casefold + strip normalization — the LLM receives the normalized form
# ---------------------------------------------------------------------------


async def test_chat_route_normalizes_message_before_llm_call() -> None:
    """A message with mixed case + extra spaces + accents is NFC + casefold + strip normalized.

    REQ-CHAT-001 preflight: `unicodedata.normalize("NFC", s)
    .casefold().strip()`. The LLM receives the normalized form;
    the aggregator is called with empty `q` / `location` (the
    v1 convention where the message IS the intent).
    """
    # The aggregator must return at least 1 job so the use case
    # actually reaches the LLM (the empty-aggregator path
    # short-circuits and never invokes the LLM).
    aggregator = FakeAggregator(jobs=[_make_job("a")])
    llm = FakeLLMClient(matching_ids=["a"], explanation="ok")
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    app = _build_test_app(use_case=use_case, max_message_chars=1000)
    async with _client(app) as client:
        # Request: 2 extra spaces, uppercase, "A" + combining acute (NFC form = U+00C1 = "Á").
        response = await client.post("/jobs/chat", json={"message": "  PYTHON  \u00c1rea Junior  "})
    assert response.status_code == 200

    # The LLM was called exactly once with the normalized message.
    assert len(llm.calls) == 1
    _system, user_payload = llm.calls[0]
    parsed = json.loads(user_payload)
    # NFC + casefold + strip:
    #   "  PYTHON  Área Junior  " -> "python  área junior" (double space
    #   preserved; only leading/trailing is stripped). The NFC of
    #   "Á" (U+00C1) is a no-op because the input is already NFC.
    assert parsed["intent"] == "python  área junior"


# ---------------------------------------------------------------------------
# Error mapping — `LLMUnavailableError` → 502, `LLMResponseParseError` → 422
# ---------------------------------------------------------------------------


async def test_chat_route_returns_502_when_llm_unavailable() -> None:
    """The LLM raises `LLMUnavailableError` → route returns 502 with descriptive detail.

    The `LLMUnavailableError` propagates from the use case
    (which does not catch it). The route catches it locally and
    maps to 502 via `HTTPException`. The body shape mirrors the
    spec's design §5 row: `{"detail": "LLM provider unavailable: <msg>"}`.
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(error=LLMUnavailableError("upstream down"))
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    app = _build_test_app(use_case=use_case, max_message_chars=1000)
    async with _client(app) as client:
        response = await client.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 502
    body = response.json()
    assert "LLM provider unavailable" in body["detail"]
    assert "upstream down" in body["detail"]


async def test_chat_route_returns_422_when_llm_response_unparseable() -> None:
    """The LLM raises `LLMResponseParseError` → route returns 422 with descriptive detail.

    The defensive parser is configured to raise when both tier-1
    and tier-2 fail. The route catches it locally and maps to
    422 (NOT the global 502 handler — the error is recoverable
    from the user's perspective; a 422 tells the client the
    request is malformed in a way the LLM cannot satisfy).
    """
    jobs = [_make_job("a")]
    aggregator = FakeAggregator(jobs=jobs)
    llm = FakeLLMClient(error=LLMResponseParseError("could not extract JSON"))
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    app = _build_test_app(use_case=use_case, max_message_chars=1000)
    async with _client(app) as client:
        response = await client.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 422
    body = response.json()
    assert "LLM response could not be parsed" in body["detail"]
    assert "could not extract JSON" in body["detail"]


# ---------------------------------------------------------------------------
# Type-level sanity — the factory function returns an `APIRouter` with the
# chat route registered. Pins the API contract.
# ---------------------------------------------------------------------------


async def test_chat_router_factory_returns_an_apirouter_with_chat_route() -> None:
    """`build_chat_router()` returns a `FastAPI.APIRouter` with `/jobs/chat`.

    The factory function is the public seam; tests use it to
    build a minimal app for unit-testing the route in
    isolation. Pinning the return type + the route path pins
    the API contract.
    """
    aggregator = FakeAggregator(jobs=[])
    llm = FakeLLMClient()
    use_case = FilterJobsByIntentUseCase(aggregator=aggregator, llm=llm)  # type: ignore[arg-type]

    router = build_chat_router(use_case=use_case, max_message_chars=1000)
    assert isinstance(router, APIRouter)
    paths = [r.path for r in router.routes if hasattr(r, "path")]
    assert "/jobs/chat" in paths
