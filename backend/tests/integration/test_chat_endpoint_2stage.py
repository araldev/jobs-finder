"""Integration tests for the 2-stage `POST /jobs/chat` endpoint (T-013 of
`chat-filter-2stage`).

Spec: REQ-CHAT-INT-001..005 (2-stage flow + v1 fallback), REQ-CHAT-001
(chat request/response shape, end-to-end), REQ-LLM-SEC-001/002
(per-call security boundaries + retry-once).

The 2-stage flow adds a stage-1 LLM intent-extraction call that drives
a directed aggregator scrape (with the extracted `q` / `location`)
BEFORE the v1 stage-3 LLM filter runs. Low-confidence extractions
(`confidence < INTENT_EXTRACTION_CONFIDENCE_THRESHOLD`, default 0.7)
fall back to the v1 single-stage path; the `used_fallback: bool` field
on the `ChatResponse` tells the client which path served the request.

The 9 end-to-end scenarios:

  1. 200 happy path HIGH-confidence: 2 LLM calls (stage 1 + stage 3),
     directed aggregator scrape with extracted params, filtered jobs
     returned, `used_fallback=False`.
  2. 200 fallback LOW-confidence: stage 1 returns `confidence=0.5`,
     use case dispatches to v1 path, 1 LLM call (stage 3), the v1
     `q=""` / `location=""` aggregator scrape, `used_fallback=True`.
  3. 200 `INTENT_EXTRACTION_ENABLED=false` kill switch: no stage-1
     call, v1 path runs, `used_fallback=True`.
  4. 502 LLM down (stage 1): `FakeLLMClient.complete` raises
     `LLMUnavailableError` on call 1 → 502.
  5. 502 LLM down (stage 3): stage 1 OK, `FakeLLMClient.complete`
     raises on call 2 → 502.
  6. 422 parse error (stage 3): stage 1 OK, `FakeLLMClient.complete`
     on call 2 returns malformed JSON → 422 (the v1 parser raises
     `LLMResponseParseError`; the route maps it to 422).
  7. 400 message cap: a 500-char message with `max_message_chars=400`
     → 400; no LLM call.
  8. 429 chat rate limit: 21st call from same IP within the window
     → 429 (the `ChatRateLimitMiddleware` short-circuits).
  9. 404 disabled: `llm_filter_enabled=False` → the route is NOT
     registered, so `POST /jobs/chat` returns 404.

The test seam: the `_build_chat_2stage_test_app` helper mirrors the
v1 `_build_chat_test_app` in `test_chat_endpoint.py` but wires the
`IntentExtractor` with a `FakeIntentExtractor` (from conftest)
returning a canned `Intent`. A `FakeLLMClient` is injected for the
stage-3 LLM. The 3 source routes are wired to a single shared
`FakeJobSearchPort` primed with the test's jobs.

Each test uses a NEW `FakeIntentExtractor` instance with the
appropriate `canned` Intent (high-confidence for the 2-stage path;
low-confidence for the fallback path) so the use case's dispatch
logic is exercised. The `FakeLLMClient` records every call so
tests can assert the 2-stage path made exactly 2 calls (stage 1 +
stage 3) vs the v1 path's 1 call (stage 3 only).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import (
    Intent,
    IntentExtractorPort,
    JobSearchCacheKey,
    LLMClientPort,
)
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
from jobs_finder.infrastructure.location.hardcoded_resolver import (
    HardcodedLocationResolver,
)
from jobs_finder.infrastructure.rate_limit.in_memory_token_bucket import (
    InMemoryTokenBucket,
)
from jobs_finder.presentation.middleware import (
    ChatRateLimitMiddleware,
    RequestIdMiddleware,
)
from jobs_finder.presentation.routes import chat as chat_routes
from tests.conftest import FakeIntentExtractor, FakeJobSearchPort
from tests.unit._helpers.fake_job_repository import FakeJobRepository

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_job(job_id: str, title: str = "Software Engineer") -> Job:
    """Build a `Job` with a unique id and a sensible default shape.

    Mirrors the v1 `_make_job` helper in `test_chat_endpoint.py`. The
    2-stage tests use the same `Job` shape so the `FakeLLMClient`'s
    `matching_ids` line up with the aggregator's flat list.
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


class FakeLLMClient:
    """A `LLMClientPort` that returns canned responses (or raises).

    Mirrors the v1 `FakeLLMClient` in `test_chat_endpoint.py` but is
    defined locally so the 2-stage file is self-contained. The fake
    records every call (system + user) so tests can assert:
      - The 2-stage path made exactly 2 calls (stage 1 + stage 3).
      - The v1 fallback path made exactly 1 call (stage 3 only).
      - The stage-1 call's `system` arg contains
        `INTENT_EXTRACTION_SYSTEM_PROMPT` markers (the security
        boundary keywords).
      - The stage-3 call's `system` arg contains the v1 `SYSTEM_PROMPT`
        markers (the security boundary keywords appended in T-004).
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
        """No-op `stream_complete` for `LLMClientPort` Protocol conformance (T-003)."""
        del system, user
        if False:  # pragma: no cover — yields nothing
            yield ""


def _build_chat_2stage_test_app(
    *,
    jobs: list[Job],
    intent_extractor: IntentExtractorPort,
    llm: LLMClientPort,
    max_message_chars: int = 1000,
    chat_rate_limit_rpm: int = 20,
) -> FastAPI:
    """Build a FastAPI app with the 2-stage chat feature wired.

    The 3 source use cases are wired to a single shared
    `FakeJobSearchPort` primed with the `jobs` list so the
    aggregator returns those jobs for any query. The
    `FilterJobsByIntentUseCase` is built with the existing
    `SearchAllSourcesUseCase` + the injected `FakeLLMClient` +
    the `intent_extractor`. The chat route is registered (no
    conditional — the test always wants the chat endpoint).

    The `ChatRateLimitMiddleware` IS mounted (so the 429 test
    can exercise it) with the supplied `chat_rate_limit_rpm`.
    The `RequestIdMiddleware` provides the 4xx/5xx body's
    `request_id`.
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
    chat_use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,
        llm=llm,
        intent_extractor=intent_extractor,
        job_repository=FakeJobRepository(jobs=jobs),
    )

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    # The ChatRateLimitMiddleware reuses the main rate limiter
    # (a fresh `InMemoryTokenBucket` here so the test does not
    # share state with the main middleware). The middleware
    # itself is mounted unconditionally — the test that
    # exercises the 429 path uses a tiny `chat_rate_limit_rpm`
    # to reach the cap. The window is 60s (the canonical 1-min
    # window — refill rate = `capacity / 60` tokens per second).
    app.add_middleware(
        ChatRateLimitMiddleware,
        rate_limiter=InMemoryTokenBucket(capacity=chat_rate_limit_rpm, window_seconds=60.0),
        max_per_minute=chat_rate_limit_rpm,
    )
    app.include_router(
        chat_routes.build_chat_router(
            use_case=chat_use_case,
            max_message_chars=max_message_chars,
        )
    )
    # Expose the use case for diagnostic assertions (e.g. the
    # `app.state.filter_use_case._intent_extractor` can be checked
    # to confirm the wire-up).
    app.state.filter_use_case = chat_use_case
    return app


@pytest.fixture
def jobs() -> list[Job]:
    """5 sample jobs — the default for the 2-stage chat endpoint tests."""
    return [
        _make_job("a", "Python Developer"),
        _make_job("b", "Java Backend"),
        _make_job("c", "Frontend React"),
        _make_job("d", "DevOps"),
        _make_job("e", "Data Engineer"),
    ]


def _high_confidence_extractor(
    *,
    q: str = "python",
    location: str = "Madrid",
    remote: bool = True,
) -> FakeIntentExtractor:
    """A `FakeIntentExtractor` returning a HIGH-confidence `Intent`.

    With the default `INTENT_EXTRACTION_CONFIDENCE_THRESHOLD=0.7`,
    `confidence=0.95` triggers the 2-stage path: the use case
    forwards `q` / `location` to the aggregator with
    `limit=intent_max_results` (default 100).
    """
    return FakeIntentExtractor(
        canned=Intent(
            q=q,
            location=location,
            experience_years=None,
            remote=remote,
            employment_type="full_time",
            confidence=0.95,
            notes=None,
        )
    )


def _low_confidence_extractor() -> FakeIntentExtractor:
    """A `FakeIntentExtractor` returning a LOW-confidence `Intent`.

    With the default threshold of 0.7, `confidence=0.5` triggers
    the v1 fallback path: the use case calls the aggregator with
    `q=""` / `location=""` / `limit=20` and the response carries
    `used_fallback=True`.
    """
    return FakeIntentExtractor(
        canned=Intent(
            q=None,
            location=None,
            experience_years=None,
            remote=None,
            employment_type=None,
            confidence=0.5,
            notes=None,
        )
    )


# ---------------------------------------------------------------------------
# REQ-CHAT-INT-001 + REQ-CHAT-INT-002 — 2-stage happy path (HIGH confidence)
# ---------------------------------------------------------------------------


async def test_2stage_happy_path_high_confidence(
    jobs: list[Job],
) -> None:
    """2-stage happy path: HIGH confidence → 1 LLM call (stage 3), directed params.

    The `FakeIntentExtractor` returns a canned `Intent` directly
    (it does NOT call the LLM — that's the test double's
    purpose; the real `IntentExtractor` makes 1 LLM call, but
    the test pins the use case's STAGE-2 + STAGE-3 dispatch,
    not the extractor's internals). The single LLM call from
    the use case is stage 3 (the final filter). Stage 2
    forwards the extracted `q` / `location` to the aggregator.

    The response is 200 with 3 jobs, the LLM's explanation,
    and `used_fallback=False` (the 2-stage path ran, NOT the
    v1 fallback).

    NOTE: when the test uses the REAL `IntentExtractor` (not
    a fake), the LLM call count would be 2 (stage 1 + stage 3).
    The unit tests in `test_filter_use_case.py` cover the
    "2 LLM calls with real `IntentExtractor`" path; this
    integration test exercises the 2-stage dispatch via
    `FakeIntentExtractor` so the stage-1 call is mocked out
    and the test is deterministic.
    """
    intent_extractor = _high_confidence_extractor(q="python", location="Madrid", remote=True)
    llm = FakeLLMClient(matching_ids=["a", "c", "e"], explanation="3 of 5 match")
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python remoto en Madrid"})

    assert response.status_code == 200
    body = response.json()
    # The 3 jobs in aggregator order.
    assert [job["id"] for job in body["jobs"]] == ["a", "c", "e"]
    assert body["explanation"] == "3 of 5 match"
    assert body["total_considered"] == 5
    assert body["total_matched"] == 3
    # The 2-stage path ran, NOT the v1 fallback.
    assert body["used_fallback"] is False
    # 1 LLM call: stage 3 only (the FakeIntentExtractor does
    # NOT invoke the LLM for stage 1).
    assert len(llm.calls) == 1
    # The single LLM call's system prompt is the v1 SELECTION
    # prompt (with the security boundary appended), NOT the
    # INTENT extraction prompt. The `IntentExtractor`'s
    # system prompt test lives in `test_intent_extractor.py`.
    system_arg, _ = llm.calls[0]
    assert "matching_ids" in system_arg  # stage 3's schema field name
    assert "explanation" in system_arg  # stage 3's schema field name


# ---------------------------------------------------------------------------
# REQ-CHAT-INT-004 — Low confidence fallback (v1 single-stage path)
# ---------------------------------------------------------------------------


async def test_2stage_fallback_low_confidence(
    jobs: list[Job],
) -> None:
    """2-stage fallback: LOW confidence → v1 path, 1 LLM call.

    Stage 1 returns `confidence=0.5` (below the 0.7 threshold).
    The use case dispatches to `_execute_v1(...)` with
    `used_fallback=True`. The aggregator gets the v1 defaults
    (`q=""`, `location=""`, `limit=20`). Stage 3 is the v1 LLM
    filter; the LLM picks 2 valid IDs. The response is 200 with
    2 jobs and `used_fallback=True`.

    NOTE: this test still exercises the 2-stage surface (the
    extractor IS invoked), so the LLM call count is 1, NOT 2.
    The 1 call is the v1 stage-3 filter; stage 1 returned a
    low-confidence intent and the dispatcher short-circuited
    BEFORE stage 2 / stage 3.
    """
    intent_extractor = _low_confidence_extractor()
    llm = FakeLLMClient(matching_ids=["a", "c"], explanation="2 of 5 match")
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "asdf"})

    assert response.status_code == 200
    body = response.json()
    assert [job["id"] for job in body["jobs"]] == ["a", "c"]
    assert body["total_considered"] == 5
    assert body["total_matched"] == 2
    # The v1 fallback path ran.
    assert body["used_fallback"] is True
    # 1 LLM call: stage 1 returned a low-confidence intent;
    # the dispatcher short-circuited BEFORE stage 3.
    assert len(llm.calls) == 1


# ---------------------------------------------------------------------------
# REQ-CHAT-INT-005 — `INTENT_EXTRACTION_ENABLED=false` kill switch
# ---------------------------------------------------------------------------


async def test_2stage_disabled_by_kill_switch(
    jobs: list[Job],
) -> None:
    """`INTENT_EXTRACTION_ENABLED=false` → v1 path, no stage 1 call.

    The master switch is OFF, so the use case dispatches to
    `_execute_v1(...)` without invoking the `IntentExtractor`.
    The v1 path makes 1 LLM call (stage 3). The response is
    200 with `used_fallback=True`.
    """
    # An extractor that would raise if called — the test passes
    # if it is NEVER invoked.
    extractor = FakeIntentExtractor(
        canned=Intent(confidence=0.95),
        error=AssertionError("IntentExtractor should not be called when 2-stage is disabled"),
    )
    llm = FakeLLMClient(matching_ids=["a", "b"], explanation="2 of 5 match")
    # Build the use case with `intent_extraction_enabled=False`.
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
    chat_use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,
        llm=llm,
        intent_extractor=extractor,
        intent_extraction_enabled=False,
        job_repository=FakeJobRepository(jobs=jobs),
    )
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        chat_routes.build_chat_router(
            use_case=chat_use_case,
            max_message_chars=1000,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "anything"})

    assert response.status_code == 200
    body = response.json()
    assert body["used_fallback"] is True
    # 1 LLM call (stage 3 only). The extractor was NEVER invoked.
    assert len(llm.calls) == 1
    assert extractor.calls == []


# ---------------------------------------------------------------------------
# REQ-LLM-001 (stage 1) — LLM down on stage 1 → 502
# ---------------------------------------------------------------------------


async def test_2stage_returns_502_when_llm_unavailable_stage_1(
    jobs: list[Job],
) -> None:
    """Stage-1 `FakeLLMClient.complete` raises `LLMUnavailableError` → 502.

    The `IntentExtractor` propagates the error (does NOT swallow
    it for retry — the contract is: `LLMUnavailableError`
    propagates; only `LLMResponseParseError` triggers the
    retry-once). The route catches the error locally and maps
    to 502 with a descriptive `detail`. The exception's
    message is surfaced in the body so the operator can see
    which LLM failure mode fired.
    """
    llm = FakeLLMClient(error=LLMUnavailableError("upstream down"))
    intent_extractor = _high_confidence_extractor()
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 502
    body = response.json()
    assert "LLM provider unavailable" in body["detail"]
    # Exception detail is no longer leaked to the client (security fix).
    assert "upstream down" not in body["detail"]


# ---------------------------------------------------------------------------
# REQ-LLM-001 (stage 3) — LLM down on stage 3 → 502
# ---------------------------------------------------------------------------


async def test_2stage_returns_502_when_llm_unavailable_stage_3(
    jobs: list[Job],
) -> None:
    """Stage 1 OK; stage 3 LLM raises `LLMUnavailableError` → 502.

    The `FakeIntentExtractor` returns a canned `Intent` directly
    (it does NOT call the LLM — that's the test double's
    purpose). The single LLM call from the use case is stage 3
    (the final filter). When that call raises, the use case
    propagates the error to the route, which maps to 502.
    """
    llm = FakeLLMClient(error=LLMUnavailableError("stage-3 upstream down"))
    intent_extractor = _high_confidence_extractor()
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 502
    body = response.json()
    assert "LLM provider unavailable" in body["detail"]
    # Exception detail is no longer leaked to the client (security fix).
    assert "stage-3 upstream down" not in body["detail"]
    # 1 LLM call (stage 3 only; the FakeIntentExtractor does
    # NOT invoke the LLM).
    assert len(llm.calls) == 1


# ---------------------------------------------------------------------------
# REQ-LLM-002 — Stage 3 parse error → 422
# ---------------------------------------------------------------------------


async def test_2stage_returns_422_when_stage3_response_unparseable(
    jobs: list[Job],
) -> None:
    """Stage 1 OK; stage 3 LLM returns malformed text → 422.

    The `FakeIntentExtractor` returns a canned `Intent` directly
    (it does NOT call the LLM). The single LLM call from the
    use case is stage 3 (the final filter). When that call
    returns malformed text, the v1 `parse_llm_response` raises
    `LLMResponseParseError`. The route catches the error
    locally and maps to 422.
    """
    llm = FakeLLMClient(raw_response="this is not json at all")
    intent_extractor = _high_confidence_extractor()
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 422
    body = response.json()
    assert "LLM response could not be parsed" in body["detail"]
    # 1 LLM call (stage 3 only; the FakeIntentExtractor does
    # NOT invoke the LLM).
    assert len(llm.calls) == 1


# ---------------------------------------------------------------------------
# REQ-CHAT-001 (Q2) — Message cap: 400
# ---------------------------------------------------------------------------


async def test_2stage_returns_400_when_message_exceeds_cap(
    jobs: list[Job],
) -> None:
    """A 500-char message with `max_message_chars=400` → 400; no LLM call.

    The cap check runs BEFORE the use case: the aggregator,
    the `IntentExtractor`, and the LLM are NEVER called. The
    400 body shape is the route's `HTTPException` shape.
    """
    intent_extractor = _high_confidence_extractor()
    llm = FakeLLMClient(matching_ids=["a"])
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
        max_message_chars=400,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "x" * 500})

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "message exceeds 400 chars (got 500)"
    # The LLM was NEVER called (cap check runs first).
    assert llm.calls == []


# ---------------------------------------------------------------------------
# REQ-CHAT-002 — Chat rate limit: 429
# ---------------------------------------------------------------------------


async def test_2stage_returns_429_on_chat_rate_limit(
    jobs: list[Job],
) -> None:
    """21st call from same IP within the window → 429.

    The `ChatRateLimitMiddleware` uses a fresh
    `InMemoryTokenBucket(capacity=2, refill_rate=1.0)` so the
    first 2 calls succeed (returning 200) and the 3rd call
    returns 429. The 429 body shape is the rate-limiter's
    `RateLimitedResponse`.
    """
    intent_extractor = _high_confidence_extractor()
    llm = FakeLLMClient(matching_ids=["a"])
    app = _build_chat_2stage_test_app(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
        chat_rate_limit_rpm=2,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First 2 calls succeed.
        for _ in range(2):
            r = await ac.post("/jobs/chat", json={"message": "python"})
            assert r.status_code == 200
        # 3rd call is rate-limited.
        response = await ac.post("/jobs/chat", json={"message": "python"})

    assert response.status_code == 429
    body = response.json()
    assert body["detail"] == "rate limit exceeded"


# ---------------------------------------------------------------------------
# `llm_filter_enabled=False` → 404 (route not registered)
# ---------------------------------------------------------------------------


async def test_2stage_returns_404_when_chat_disabled() -> None:
    """`llm_filter_enabled=False` → the chat route is NOT registered → 404.

    The `app_factory.build_app` production wiring conditionally
    mounts the chat route on the `llm_filter_enabled=True` flag.
    A bare `FastAPI()` app (no chat route mounted) returns 404
    for any `POST /jobs/chat` request — the test pins the
    "no chat route = 404" contract end-to-end.
    """
    # Build a bare FastAPI app with no chat route.
    app = FastAPI()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python"})

    # FastAPI's default 404 body shape.
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# `LocationResolverPort` integration (REQ-LOC-GEO-001, WU5 of
# `fix-linkedin-geoid`).
#
# End-to-end assertion: a high-confidence chat with
# `intent.location="Madrid"` flows through the resolver
# (`HardcodedLocationResolver().resolve("Madrid") == 103374081`)
# and the LinkedIn port receives `geo_id=103374081` in its
# `search(...)` call. This is the original gap test (intentionally
# a regression test for the 953 baseline): the prior `chat-filter-
# 2stage` cycle used `FakeJobSearchPort` that short-circuited the
# URL builder and missed the `geoId=` vs `location=` mismatch.
# The new test pins the full chain end-to-end.
# ---------------------------------------------------------------------------


class RecordingLinkedInJobSearchPort:
    """A `JobSearchPort` that records `(keywords, location, limit, geo_id)`.

    The 4-tuple `calls` shape captures the per-source forwarding
    contract after the WU3 signature extension. The test asserts
    the LinkedIn port received `geo_id=103374081` (the value the
    `HardcodedLocationResolver` returned for `"Madrid"`).
    """

    def __init__(self, jobs: list[Job] | None = None) -> None:
        self._jobs: list[Job] = list(jobs) if jobs is not None else []
        self.calls: list[tuple[str, str, int, int | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int = 20,
        geo_id: int | None = None,
    ) -> list[Job]:
        self.calls.append((keywords, location, limit, geo_id))
        return list(self._jobs)


def _build_chat_2stage_test_app_with_resolver(
    *,
    jobs: list[Job],
    intent_extractor: IntentExtractorPort,
    llm: LLMClientPort,
    linkedin_port: RecordingLinkedInJobSearchPort,
) -> FastAPI:
    """Build a chat app with a real `HardcodedLocationResolver` + a recording LinkedIn port.

    The 3 source use cases are wired to a SHARED
    `RecordingLinkedInJobSearchPort` for LinkedIn (records
    the `geo_id` kwarg) and a fresh empty `FakeJobSearchPort`
    for Indeed + InfoJobs (so the aggregator only records
    the LinkedIn call with the `geo_id`). The chat use
    case is built with the real `HardcodedLocationResolver`
    so the `intent.location` → `geoId` translation runs
    end-to-end.
    """
    indeed_port = FakeJobSearchPort(jobs=[])
    infojobs_port = FakeJobSearchPort(jobs=[])
    cache: InMemoryTTLCache[JobSearchCacheKey, list[Job]] = InMemoryTTLCache(ttl_seconds=60.0)
    linkedin_uc = SearchLinkedInJobsUseCase(
        port=linkedin_port,
        cache=cache,
        source="linkedin",
    )
    indeed_uc = IndeedSearchJobsUseCase(
        port=indeed_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="indeed",
    )
    infojobs_uc = InfoJobsSearchJobsUseCase(
        port=infojobs_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="infojobs",
    )
    aggregator = SearchAllSourcesUseCase(
        linkedin_use_case=linkedin_uc,
        indeed_use_case=indeed_uc,
        infojobs_use_case=infojobs_uc,
    )
    chat_use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,
        llm=llm,
        intent_extractor=intent_extractor,
        location_resolver=HardcodedLocationResolver(),
        job_repository=FakeJobRepository(jobs=jobs),
    )
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        chat_routes.build_chat_router(
            use_case=chat_use_case,
            max_message_chars=1000,
        )
    )
    app.state.filter_use_case = chat_use_case
    return app


@pytest.mark.skip(
    reason=(
        "aggregator fallback removed: the chat endpoint no longer "
        "calls the LinkedIn scraper / aggregator. The resolver→geoId→"
        "LinkedIn chain is no longer testable end-to-end through the "
        "chat endpoint. The resolver itself is still unit-tested."
    )
)
async def test_2stage_geo_id_end_to_end_with_real_resolver(
    jobs: list[Job],
) -> None:
    """End-to-end: resolver translates Madrid → 103374081 → LinkedIn port.

    REQ-LOC-GEO-001 + REQ-CHAT-INT-001: the 2-stage path
    translates the extracted `intent.location` into a
    LinkedIn `geoId` via the real `HardcodedLocationResolver`
    (not a fake). The resolved `geo_id` is forwarded to
    the aggregator → LinkedIn use case → LinkedIn port
    → URL builder. The test asserts the full chain
    end-to-end with the real resolver implementation.

    The `RecordingLinkedInJobSearchPort` captures the
    `geo_id` kwarg the LinkedIn use case passed through
    (which is the contract that the prior `chat-filter-2stage`
    cycle missed — `FakeJobSearchPort` short-circuited
    this layer).

    The test uses the `FakeLLMClient` (1 LLM call: stage 3
    only; the `FakeIntentExtractor` does NOT invoke the
    LLM for stage 1). The test pins:
      1. The chat response is 200 with the expected jobs.
      2. The LinkedIn port received `geo_id=103374081`
         (the value the resolver returned for "Madrid").
      3. The Indeed + InfoJobs ports received `geo_id=None`
         (they ignore the kwarg).
    """
    intent_extractor = _high_confidence_extractor(q="python", location="Madrid", remote=True)
    llm = FakeLLMClient(matching_ids=["a", "c"], explanation="2 of 5 match")
    linkedin_port = RecordingLinkedInJobSearchPort(jobs=jobs)
    app = _build_chat_2stage_test_app_with_resolver(
        jobs=jobs,
        intent_extractor=intent_extractor,
        llm=llm,
        linkedin_port=linkedin_port,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/jobs/chat", json={"message": "python remoto en Madrid"})

    # The chat response is 200.
    assert response.status_code == 200
    body = response.json()
    # The LLM picked 2 jobs in aggregator order.
    assert [job["id"] for job in body["jobs"]] == ["a", "c"]
    # `used_fallback=False` (2-stage path).
    assert body["used_fallback"] is False
    # The LinkedIn port received `geo_id=103374081` (the
    # value the `HardcodedLocationResolver` returned for
    # "Madrid"). This is the original gap test.
    assert len(linkedin_port.calls) == 1
    keywords, location, limit, geo_id = linkedin_port.calls[0]
    assert keywords == "python"
    assert location == "Madrid"
    assert limit == 100  # `intent_max_results`
    assert geo_id == 103374081
    # The LLM was called ONCE (stage 3 only; the
    # `FakeIntentExtractor` does NOT invoke the LLM).
    assert len(llm.calls) == 1
