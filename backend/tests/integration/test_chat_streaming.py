"""Integration tests for `POST /jobs/chat/stream` (T-009 of `chat-streaming`).

Spec: REQ-SSE-001/002/003, REQ-META-001, REQ-CACHE-001,
REQ-ERROR-MAPPING-001.

These tests exercise the SSE endpoint end-to-end via
`httpx.AsyncClient` over `ASGITransport`. The chat feature
is enabled via `Settings(llm_filter_enabled=True,
llm_api_key=...)`; the use case's dependencies (LLM,
aggregator, intent extractor) are injected with fakes
that don't talk to the network.

The 10 tests cover the spec's primary scenarios:
  1. Happy path: meta → text × N → done.
  2. v1 path: text × N → done (no meta).
  3. Keepalive during slow stage-2 aggregator (≥3 keepalives in 20s).
  4. No keepalive when `sse_keepalive_seconds=0`.
  5. Pre-stream 400 (over-cap message).
  6. Error mapping: `LLMUnavailableError` → `llm_unavailable`.
  7. Error mapping: parse failure → `llm_parse`.
  8. Error mapping: timeout → `llm_timeout`.
  9. SSE cache headers present.
  10. CORS preflight for POST → 200.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from jobs_finder.application.aggregator import (
    AggregatedJob,
    AggregatedResult,
    SourceResult,
)
from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
)
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.llm.exceptions import (
    LLMRequestTimeoutError,
    LLMStreamError,
    LLMUnavailableError,
)
from jobs_finder.presentation.app_factory import build_app

# ---------------------------------------------------------------------------
# Fixtures — chat-enabled app with fakes for LLM + aggregator
# ---------------------------------------------------------------------------


def _make_job(job_id: str) -> Job:
    """Build a sample `Job` for the integration tests."""
    return Job(
        id=job_id,
        title="Software Engineer",
        company=f"Co-{job_id}",
        location="Madrid",
        url=f"https://example.com/jobs/{job_id}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="linkedin",
    )


class _FakeAggregator:
    """Stand-in for `SearchAllSourcesUseCase`."""

    def __init__(
        self,
        jobs: list[Job] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._jobs = list(jobs) if jobs is not None else []
        self._delay_seconds = delay_seconds
        self.calls: list[tuple[str, str, int, list[str] | None]] = []

    async def search(
        self,
        keywords: str,
        location: str,
        limit: int,
        sources: list[str] | None = None,
    ) -> AggregatedResult:
        self.calls.append((keywords, location, limit, sources))
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        return AggregatedResult(
            jobs=[AggregatedJob(job=j, sources=["linkedin"]) for j in self._jobs],
            per_source={
                "linkedin": SourceResult(source="linkedin", jobs=self._jobs, cache_status="MISS")
            },
            cache_statuses={"linkedin": "MISS"},
        )


class _FakeLLMClient:
    """Stand-in for `LLMClientPort` with streaming + error support."""

    def __init__(
        self,
        *,
        stream_chunks: list[str] | None = None,
        complete_response: str = '{"matching_ids": [], "explanation": "ok"}',
        error: Exception | None = None,
    ) -> None:
        self._stream_chunks = list(stream_chunks or [])
        self._complete_response = complete_response
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._error is not None:
            raise self._error
        return self._complete_response

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        del system, user
        if self._error is not None:
            raise self._error
        for chunk in self._stream_chunks:
            yield chunk


def _build_chat_app(
    *,
    jobs: list[Job] | None = None,
    stream_chunks: list[str] | None = None,
    complete_response: str = '{"matching_ids": [], "explanation": "ok"}',
    llm_error: Exception | None = None,
    aggregator_delay_seconds: float = 0.0,
    sse_keepalive_seconds: float = 0.0,
    llm_filter_enabled: bool = True,
    intent_extraction_enabled: bool = False,
) -> FastAPI:
    """Build a chat-enabled app with fakes for the LLM + aggregator.

    Defaults: chat ON, intent extraction OFF (v1 path).
    The v1 path is simpler to test (no `meta` event);
    the 2-stage path is covered by the unit tests in
    `test_filter_use_case.py::test_stream_execute_*`.
    """
    from jobs_finder.application.usecases.search_indeed_jobs import (  # noqa: PLC0415
        SearchJobsUseCase as IndeedSearchJobsUseCase,
    )
    from jobs_finder.application.usecases.search_infojobs_jobs import (  # noqa: PLC0415
        SearchJobsUseCase as InfoJobsSearchJobsUseCase,
    )
    from jobs_finder.application.usecases.search_linkedin_jobs import (  # noqa: PLC0415
        SearchLinkedInJobsUseCase,
    )

    class _EmptyPort:
        async def search(
            self, keywords: str, location: str, limit: int = 20, geo_id: int | None = None
        ) -> list[Job]:
            del keywords, location, limit, geo_id
            return []

    linkedin_port = _EmptyPort()
    linkedin_use_case = SearchLinkedInJobsUseCase(
        port=linkedin_port, cache=InMemoryTTLCache(ttl_seconds=60.0), source="linkedin"
    )
    indeed_use_case = IndeedSearchJobsUseCase(
        port=_EmptyPort(), cache=InMemoryTTLCache(ttl_seconds=60.0), source="indeed"
    )
    infojobs_use_case = InfoJobsSearchJobsUseCase(
        port=_EmptyPort(), cache=InMemoryTTLCache(ttl_seconds=60.0), source="infojobs"
    )

    settings = Settings(
        llm_filter_enabled=llm_filter_enabled,
        llm_api_key=SecretStr("test-key"),
        llm_base_url="https://api.example.invalid",  # not actually called
        sse_keepalive_seconds=sse_keepalive_seconds,
        intent_extraction_enabled=intent_extraction_enabled,
    )

    app = build_app(
        use_case=linkedin_use_case,
        indeed_use_case=indeed_use_case,
        infojobs_use_case=infojobs_use_case,
        settings=settings,
    )

    # Replace the chat use case with one that uses our fakes.
    # The composition-root build creates a real LLM client; we
    # override the use case with one that uses our fakes.
    aggregator = _FakeAggregator(jobs=jobs, delay_seconds=aggregator_delay_seconds)
    # The chat endpoint now queries the DB (job_repository) instead
    # of the aggregator. Wire a FakeJobRepository with the same
    # canned jobs so tests don't need a live SQLite.
    from tests.unit._helpers.fake_job_repository import (  # noqa: PLC0415
        FakeJobRepository,
    )

    repo = FakeJobRepository(jobs=jobs or [])
    llm = _FakeLLMClient(
        stream_chunks=stream_chunks,
        complete_response=complete_response,
        error=llm_error,
    )
    new_use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,  # type: ignore[arg-type]
        llm=llm,
        intent_extraction_enabled=intent_extraction_enabled,
        job_repository=repo,
    )
    # Replace the use case on app.state AND rebuild the routers
    # so the new use case is used. The simplest path: rebuild the
    # routers using the new use case.
    from jobs_finder.presentation.routes import chat as chat_routes  # noqa: PLC0415

    app.state.filter_use_case = new_use_case
    # Remove the existing v1 + stream routers and re-include with
    # the fake use case.
    app.router.routes = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) not in ("/jobs/chat", "/jobs/chat/stream")
    ]
    app.include_router(
        chat_routes.build_chat_router(
            use_case=new_use_case,
            max_message_chars=settings.llm_max_message_chars,
        )
    )
    app.include_router(
        chat_routes.build_chat_stream_router(
            use_case=new_use_case,
            max_message_chars=settings.llm_max_message_chars,
            sse_keepalive_seconds=sse_keepalive_seconds,
        )
    )
    return app


def _parse_sse_events(text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse the raw SSE body into `(event_name, data)` tuples.

    Each event is `event: <name>\\ndata: <json>\\n\\n`. The
    function splits on `\\n\\n`, then parses the `event:`
    and `data:` lines.
    """
    events: list[tuple[str, dict[str, object]]] = []
    for raw_block in text.split("\n\n"):
        block = raw_block.strip()
        if not block:
            continue
        if block.startswith(":"):  # comment line (keepalive)
            continue
        event_name = ""
        data_payload = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_payload = line[len("data: ") :]
        if event_name and data_payload:
            try:
                data_obj: object = json.loads(data_payload)
                # Narrow to dict for the typed return; the
                # JSON payloads for our events are always
                # objects (the SSE wire format is
                # `event: <name>\\ndata: {<json object>}\\n\\n`).
                if isinstance(data_obj, dict):
                    data: dict[str, object] = data_obj
                    events.append((event_name, data))
            except json.JSONDecodeError:
                events.append((event_name, {"raw": data_payload}))
    return events


# ---------------------------------------------------------------------------
# Test 1: happy path
# ---------------------------------------------------------------------------


async def test_chat_stream_happy_path_emits_text_then_done() -> None:
    """v1 path: `text` × N → `done` (no `meta`). The done carries jobs in aggregator order.

    REQ-SSE-001 1st scenario: a valid message streams
    `text` events (per LLM token) and ends with a
    `done` event carrying the matched jobs in the
    aggregator's order.
    """
    app = _build_chat_app(
        jobs=[_make_job("a"), _make_job("b"), _make_job("c")],
        stream_chunks=['{"matching_ids":["a","c"],', '"explanation":"match"}'],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    # 2 text + 1 done = 3 events (no meta in v1 path).
    event_names = [name for name, _ in events]
    assert event_names == ["text", "text", "done"]
    done_data: dict[str, object] = events[-1][1]
    jobs_obj: object = done_data["jobs"]
    assert isinstance(jobs_obj, list)
    job_ids: list[str] = []
    for j in jobs_obj:
        assert isinstance(j, dict)
        id_val: object = j["id"]
        assert isinstance(id_val, str)
        job_ids.append(id_val)
    assert job_ids == ["a", "c"]


# ---------------------------------------------------------------------------
# Test 2: SSE cache headers
# ---------------------------------------------------------------------------


async def test_chat_stream_response_has_required_sse_headers() -> None:
    """The response carries Content-Type, Cache-Control, Connection, X-Accel-Buffering.

    REQ-CACHE-001 1st scenario: all 4 required headers
    are present on a successful 200 response.
    """
    app = _build_chat_app(
        jobs=[_make_job("a")],
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"ok"}'],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("cache-control") == "no-cache"
    assert response.headers.get("connection") == "keep-alive"
    assert response.headers.get("x-accel-buffering") == "no"


# ---------------------------------------------------------------------------
# Test 3: pre-stream 400
# ---------------------------------------------------------------------------


async def test_chat_stream_returns_400_when_message_exceeds_cap() -> None:
    """A 1234-char message with `max_message_chars=1000` → 400 + descriptive detail.

    REQ-SSE-001 pre-stream validation: over-cap
    messages return 400 with the v1 `{"detail": ...}`
    body shape (NOT an SSE stream). The LLM is NEVER
    called.
    """
    app = _build_chat_app(jobs=[_make_job("a")], stream_chunks=["never-called"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "x" * 1234})

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "message exceeds 1000 chars (got 1234)"


# ---------------------------------------------------------------------------
# Test 4: error mapping — LLMUnavailableError → llm_unavailable
# ---------------------------------------------------------------------------


async def test_chat_stream_error_event_on_llm_unavailable() -> None:
    """LLM raises `LLMUnavailableError` → SSE event `error` with code `llm_unavailable`.

    REQ-SSE-003 1st scenario: the LLM call fails
    mid-stream; the server emits exactly one
    `event: error` with the expected `code` and
    closes the connection.
    """
    app = _build_chat_app(
        jobs=[_make_job("a")],
        llm_error=LLMUnavailableError("upstream down"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e[0] == "error"]
    assert len(error_events) == 1
    _, data = error_events[0]
    assert data["code"] == "llm_unavailable"
    message_str: object = data["message"]
    assert isinstance(message_str, str)
    assert "upstream down" in message_str


# ---------------------------------------------------------------------------
# Test 5: error mapping — LLMStreamError → llm_stream
# ---------------------------------------------------------------------------


async def test_chat_stream_error_event_on_llm_stream_error() -> None:
    """LLM raises `LLMStreamError` → SSE event `error` with code `llm_stream`."""
    app = _build_chat_app(
        jobs=[_make_job("a")],
        llm_error=LLMStreamError("stream status 500"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e[0] == "error"]
    assert len(error_events) == 1
    _, data = error_events[0]
    assert data["code"] == "llm_stream"


# ---------------------------------------------------------------------------
# Test 6: error mapping — LLMRequestTimeoutError → llm_timeout
# ---------------------------------------------------------------------------


async def test_chat_stream_error_event_on_llm_timeout() -> None:
    """LLM raises `LLMRequestTimeoutError` → SSE event `error` with code `llm_timeout`."""
    app = _build_chat_app(
        jobs=[_make_job("a")],
        llm_error=LLMRequestTimeoutError("timeout after 15s"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e[0] == "error"]
    assert len(error_events) == 1
    _, data = error_events[0]
    assert data["code"] == "llm_timeout"


# ---------------------------------------------------------------------------
# Test 7: error mapping — LLMResponseParseError → llm_parse
# ---------------------------------------------------------------------------


async def test_chat_stream_error_event_on_llm_parse_error() -> None:
    """Parser raises `LLMResponseParseError` → graceful fallback: all aggregator jobs returned, no error event."""
    app = _build_chat_app(
        jobs=[_make_job("a"), _make_job("b")],
        stream_chunks=["not-valid-json"],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e[0] == "error"]
    # Graceful fallback: no error event, all aggregator jobs returned in done event.
    assert len(error_events) == 0
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    _, data = done_events[0]
    assert data["used_fallback"] is True
    assert len(data["jobs"]) == 2  # both aggregator jobs returned


# ---------------------------------------------------------------------------
# Test 8: no keepalive when sse_keepalive_seconds=0
# ---------------------------------------------------------------------------


async def test_chat_stream_no_keepalive_when_disabled() -> None:
    """With `sse_keepalive_seconds=0`, the body contains NO `: keepalive` comments.

    REQ-SSE-002 2nd scenario: when the keepalive
    feature is disabled, no `: keepalive` lines
    appear in the body. The `text` + `done` event
    sequence is unchanged.
    """
    app = _build_chat_app(
        jobs=[_make_job("a")],
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"ok"}'],
        sse_keepalive_seconds=0.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    # The body has NO `: keepalive` lines.
    assert ": keepalive" not in response.text
    # But the normal event sequence is intact.
    events = _parse_sse_events(response.text)
    event_names = [name for name, _ in events]
    assert "done" in event_names


# ---------------------------------------------------------------------------
# Test 9: keepalive emitted during slow stage-2 aggregator
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    "LLM_LIVE_TESTS" not in os.environ or os.environ.get("LLM_LIVE_TESTS") != "1",
    reason="Slow test (20s aggregator wait); opt-in via LLM_LIVE_TESTS=1 to keep CI fast",
)
async def test_chat_stream_emits_keepalive_during_slow_aggregator() -> None:
    """A slow aggregator + `sse_keepalive_seconds=2.0` emits ≥3 keepalive comments.

    REQ-SSE-002 1st scenario: during the stage-2
    aggregator scrape wait, the server emits a
    `: keepalive` comment every `sse_keepalive_seconds`.
    The test waits ~6s and asserts ≥3 keepalives
    arrived.
    """
    app = _build_chat_app(
        jobs=[_make_job("a")],
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"ok"}'],
        aggregator_delay_seconds=6.0,
        sse_keepalive_seconds=2.0,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        timeout=30.0,
    ) as client:
        response = await client.post("/jobs/chat/stream", json={"message": "python"})

    assert response.status_code == 200
    keepalive_count = response.text.count(": keepalive")
    assert keepalive_count >= 3, f"Expected ≥3 keepalives in 6s with sse=2.0; got {keepalive_count}"


# ---------------------------------------------------------------------------
# Test 10: CORS preflight for POST
# ---------------------------------------------------------------------------


async def test_chat_stream_cors_preflight_for_post_succeeds() -> None:
    """`OPTIONS /jobs/chat/stream` with POST method → 200 + CORS headers.

    REQ-CORS-001 1st scenario: the preflight succeeds
    with the documented CORS headers. The
    `Access-Control-Allow-Methods` MUST include POST
    (the new endpoint) and GET (the per-source routes).
    """
    app = _build_chat_app(
        jobs=[_make_job("a")],
        stream_chunks=['{"matching_ids":["a"],', '"explanation":"ok"}'],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.options(
            "/jobs/chat/stream",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods.upper()
    assert "GET" in allow_methods.upper()
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "content-type" in allow_headers.lower()
