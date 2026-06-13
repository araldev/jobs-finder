"""`POST /jobs/chat` chat-filter route (T-014 of `ai-chat-filter`)
+ `POST /jobs/chat/stream` streaming route (T-008 of `chat-streaming`).

The v1 route (`build_chat_router`) is UNCHANGED — REQ-BACKWARDS-COMPAT-001.
The new streaming route (`build_chat_stream_router`) is a sibling
that emits SSE events: `meta` (2-stage) → `text` × N → `done`, OR
`event: error` on a 6-way machine-code mapping (REQ-ERROR-MAPPING-001).

Spec: REQ-CHAT-001 (chat request/response), REQ-LLM-003 (strict-
subset ID validation — the use case, T-013, owns the validation),
REQ-CHAT-002 (per-user rate limit — the `ChatRateLimitMiddleware`
in T-015 enforces it). Streaming: REQ-SSE-001/002/003,
REQ-META-001, REQ-CACHE-001, REQ-ERROR-MAPPING-001.
"""

from __future__ import annotations

import asyncio
import unicodedata
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
    StreamEventDone,
    StreamEventMeta,
    StreamEventText,
)
from jobs_finder.domain.exceptions import JobSearchError
from jobs_finder.infrastructure.llm.exceptions import (
    LLMRequestTimeoutError,
    LLMResponseParseError,
    LLMStreamError,
    LLMUnavailableError,
)
from jobs_finder.presentation.schemas import (
    ChatRequest,
    ChatResponse,
    ChatStreamDoneEvent,
    ChatStreamMetaEvent,
    ChatStreamTextEvent,
    to_response,
)


def build_chat_router(
    *,
    use_case: FilterJobsByIntentUseCase,
    max_message_chars: int,
) -> APIRouter:
    """Build the `APIRouter` for `POST /jobs/chat`.

    Args:
        use_case: The `FilterJobsByIntentUseCase` to invoke. The
            route does NOT import the use case from a module —
            the composition root (`app_factory.build_app`, T-016)
            constructs it and injects it here so a test can pass
            a fake use case.
        max_message_chars: The hard cap on `req.message` length.
            Sourced from `settings.llm_max_message_chars` at
            composition-root time. The rejection body
            `{"detail": "message exceeds N chars (got M)"}`
            interpolates the configured value so a deployment
            can change the cap without code changes (Q2 spec
            resolution).

    Returns:
        A `FastAPI.APIRouter` with `POST /jobs/chat` registered.
        The router is independent of any global state — the
        composition root decides whether to mount it on the app.
    """
    router = APIRouter()

    @router.post("/jobs/chat", response_model=ChatResponse)
    async def chat(
        body: ChatRequest,
        request: Request,
    ) -> ChatResponse:
        # 1. Explicit char cap (Q2). Runs BEFORE the use case so
        #    the aggregator + LLM are NEVER invoked on an
        #    over-cap message. The 400 body shape is the route's
        #    `HTTPException` shape (NOT Pydantic's
        #    `RequestValidationError` shape) so the client sees a
        #    single consistent error contract across all chat
        #    rejections.
        if len(body.message) > max_message_chars:
            raise HTTPException(
                status_code=400,
                detail=(f"message exceeds {max_message_chars} chars (got {len(body.message)})"),
            )

        # 2. Cache-key normalization (REQ-CHAT-001 + preflight
        #    CONFIRMED). NFC handles decomposed accents
        #    (`"A\u0301"` -> `"Á"`); casefold handles Spanish
        #    uppercase + accented characters; strip trims the
        #    accidental spaces from the user's input. The
        #    aggregator is called with empty `q` / `location`
        #    (the v1 convention where the message IS the
        #    intent) so its per-source cache key is
        #    `(source, "", "", 20)` — every chat call within
        #    60s reuses the per-source cache.
        normalized = unicodedata.normalize("NFC", body.message).casefold().strip()

        # 3. Use case invocation with mapped exceptions.
        try:
            result = await use_case.execute(
                message=normalized,
                q="",
                location="",
                limit=20,
                sources=None,
            )
        except LLMUnavailableError as exc:
            # 502 mapping (route-local explicit; the global
            # `JobSearchError` handler would also map to 502,
            # but the route-local catch is testable + carries
            # the LLM-specific detail in the response body).
            raise HTTPException(
                status_code=502,
                detail=f"LLM provider unavailable: {exc}",
            ) from exc
        except LLMResponseParseError as exc:
            # 422 mapping (route-local; the global handler would
            # map to 502, so the route-local catch is required
            # to surface a 422 to the client).
            raise HTTPException(
                status_code=422,
                detail=f"LLM response could not be parsed: {exc}",
            ) from exc
        # Other `JobSearchError` subclasses (per-source errors
        # from the aggregator, etc.) propagate to the global
        # handler, which maps to 502 with the masked
        # `"upstream source unavailable"` detail.

        # 4. Build the response. `to_response(...)` is the
        #    shared `Job` -> `JobResponse` mapper (now forwards
        #    `description` per PR1 SUGGESTION #2). The chat
        #    response is a NEW `ChatResponse` schema — the
        #    client gets the LLM's `explanation` + the
        #    `total_considered` / `total_matched` counts.
        # The `used_fallback` flag (NEW in `chat-filter-2stage`,
        # REQ-CHAT-INT-004) tells the client whether the
        # 2-stage path ran (`False`) or the v1 single-stage
        # fallback ran (`True`). The use case's
        # `FilteredJobsResult.used_fallback` is `True` by
        # default (safe v1 behavior); the route forwards
        # whatever the use case set.
        return ChatResponse(
            jobs=[to_response(j) for j in result.jobs],
            explanation=result.explanation,
            total_considered=result.total_considered,
            total_matched=result.total_matched,
            used_fallback=result.used_fallback,
        )

    return router


# The factory returns the router. The composition root
# (T-016) mounts it on the app when the chat filter is
# enabled. `__all__` keeps the public surface stable for the
# test that imports `build_chat_router` (the factory function).
__all__ = ["build_chat_router", "build_chat_stream_router"]


# ---------------------------------------------------------------------------
# `POST /jobs/chat/stream` — SSE streaming sibling (T-008 of `chat-streaming`)
#
# Spec: REQ-SSE-001/002/003 + REQ-META-001 + REQ-CACHE-001 +
# REQ-ERROR-MAPPING-001.
#
# The route:
#   1. Reads the `ChatRequest{message}` body (same as v1).
#   2. Enforces the explicit char cap (400 with the same
#      `{"detail": "..."}` body shape as v1).
#   3. NFC + casefold + strip normalizes the message.
#   4. Spawns a `producer` task that drains the use case's
#      `stream_execute(...)` and pushes serialized SSE events
#      to an `asyncio.Queue[str | None]`.
#   5. The consumer reads events with
#      `asyncio.wait_for(queue.get(), sse_keepalive_seconds)`:
#      a `TimeoutError` yields a `: keepalive\n\n` comment and
#      continues; a `None` sentinel ends the stream.
#   6. Returns a `StreamingResponse` with
#      `media_type="text/event-stream"` + the 4 cache headers.
#
# The 6 error mappings (REQ-ERROR-MAPPING-001):
#   - `LLMUnavailableError`    → `llm_unavailable`
#   - `LLMStreamError`         → `llm_stream`
#   - `LLMResponseParseError`  → `llm_parse`
#   - `LLMRequestTimeoutError` → `llm_timeout`
#   - other `JobSearchError`   → `internal`
#   - stage-1 intent parse     → `stage1_parse`
# (The stage-1 error is raised by the use case, NOT caught
# here — the producer's generic `except Exception` catches it
# and maps via the `LLMResponseParseError` branch when the
# intent extractor raised one. The other 5 are explicit.)
# ---------------------------------------------------------------------------


_SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # nginx + proxies: do not buffer
}


def _serialize_event(event: object, request_id: str) -> str:
    """Serialize a `StreamEvent` to its SSE `event: ...\\ndata: ...\\n\\n` shape.

    The 3 event types are discriminated via `isinstance`:
      - `StreamEventText` → `event: text\\ndata: <json>\\n\\n`
      - `StreamEventMeta` → `event: meta\\ndata: <json>\\n\\n`
      - `StreamEventDone` → `event: done\\ndata: <json>\\n\\n`

    The `request_id` is injected into the `done` event's
    `data.request_id` field (per REQ-SSE-001 3rd scenario).
    """
    if isinstance(event, StreamEventText):
        payload = ChatStreamTextEvent(delta=event.delta).model_dump_json()
        return f"event: text\ndata: {payload}\n\n"
    if isinstance(event, StreamEventMeta):
        payload = ChatStreamMetaEvent(intent=event.intent).model_dump_json()
        return f"event: meta\ndata: {payload}\n\n"
    if isinstance(event, StreamEventDone):
        payload = ChatStreamDoneEvent(
            jobs=[to_response(j) for j in event.jobs],
            explanation=event.explanation,
            total_considered=event.total_considered,
            total_matched=event.total_matched,
            used_fallback=event.used_fallback,
            request_id=request_id,
        ).model_dump_json()
        return f"event: done\ndata: {payload}\n\n"
    # Unknown event type — fall through to an error event so
    # the client always sees a terminal event (avoids
    # hangs on protocol drift).
    return _serialize_error(RuntimeError(f"unknown stream event type: {type(event).__name__}"))


def _serialize_error(exc: BaseException) -> str:
    """Map a domain exception to its SSE `event: error\\ndata: ...\\n\\n` shape.

    The 6-way mapping is the `isinstance` chain documented
    in REQ-ERROR-MAPPING-001. The order matters: the more
    SPECIFIC subclasses MUST be checked before the parent
    (`LLMStreamError`/`LLMRequestTimeoutError` before
    `LLMUnavailableError` before `JobSearchError`).
    """
    if isinstance(exc, LLMStreamError):
        code = "llm_stream"
    elif isinstance(exc, LLMRequestTimeoutError):
        code = "llm_timeout"
    elif isinstance(exc, LLMUnavailableError):
        code = "llm_unavailable"
    elif isinstance(exc, LLMResponseParseError):
        code = "llm_parse"
    elif isinstance(exc, JobSearchError):
        code = "internal"
    else:
        # Stage-1 intent parse failures raise LLMResponseParseError
        # too (the use case catches them and falls back, but if
        # they propagate, the producer's generic catch routes them
        # here). The catch-all `internal` covers anything else.
        code = "internal"
    payload = f'{{"code": "{code}", "message": "{str(exc).replace(chr(34), chr(92) + chr(34))}"}}'
    return f"event: error\ndata: {payload}\n\n"


def build_chat_stream_router(
    *,
    use_case: FilterJobsByIntentUseCase,
    max_message_chars: int,
    sse_keepalive_seconds: float,
) -> APIRouter:
    """Build the `APIRouter` for `POST /jobs/chat/stream`.

    Args:
        use_case: The `FilterJobsByIntentUseCase` to invoke.
            The route does NOT import the use case from a
            module — the composition root constructs it
            and injects it here so a test can pass a
            fake use case.
        max_message_chars: The hard cap on `req.message`
            length. Sourced from
            `settings.llm_max_message_chars` at
            composition-root time. The 400 body shape
            matches v1 (regular HTTPException, NOT SSE).
        sse_keepalive_seconds: The interval between
            `: keepalive\n\n` comments during quiet
            periods. Sourced from
            `settings.sse_keepalive_seconds` (default
            15.0). `0.0` disables keepalive entirely
            (the `wait_for` call is replaced with a
            plain `await queue.get()`).

    Returns:
        A `FastAPI.APIRouter` with
        `POST /jobs/chat/stream` registered. The router
        is independent of any global state — the
        composition root decides whether to mount it
        on the app.
    """
    router = APIRouter()

    @router.post("/jobs/chat/stream")
    async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
        # 1. Pre-stream 400 (mirrors v1's behavior).
        if len(body.message) > max_message_chars:
            raise HTTPException(
                status_code=400,
                detail=(f"message exceeds {max_message_chars} chars (got {len(body.message)})"),
            )

        # 2. Normalize (NFC + casefold + strip, same as v1).
        normalized = unicodedata.normalize("NFC", body.message).casefold().strip()

        # 3. The request_id is read from the middleware
        #    (if present) or generated as a uuid4 hex
        #    (the test seam: a test that bypasses the
        #    middleware gets a fresh uuid4).
        request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

        # 4. The producer/consumer pattern with
        #    `asyncio.Queue[str | None]`. The `None`
        #    sentinel is the producer's "I'm done"
        #    signal; the consumer returns on it.
        q: asyncio.Queue[str | None] = asyncio.Queue()

        async def producer() -> None:
            try:
                async for event in use_case.stream_execute(
                    message=normalized,
                    q="",
                    location="",
                    limit=20,
                    exclude_ids=body.exclude_ids,
                ):
                    await q.put(_serialize_event(event, request_id))
            except BaseException as exc:  # noqa: BLE001
                # Map any domain exception to its SSE error
                # event. The `BaseException` catch covers
                # `Exception` AND `asyncio.CancelledError`
                # (so a client disconnect that cancels the
                # producer task does NOT leak a `None`).
                await q.put(_serialize_error(exc))
            finally:
                await q.put(None)

        task = asyncio.create_task(producer())

        async def stream() -> AsyncIterator[bytes]:
            try:
                while True:
                    if sse_keepalive_seconds > 0:
                        try:
                            item = await asyncio.wait_for(q.get(), timeout=sse_keepalive_seconds)
                        except TimeoutError:
                            # No event in `sse_keepalive_seconds`
                            # → emit a keepalive comment line and
                            # continue waiting. This is the
                            # "browser / proxy don't time out"
                            # safeguard (REQ-SSE-002).
                            yield b": keepalive\n\n"
                            continue
                    else:
                        # Keepalive disabled — block until an
                        # event arrives (or the producer is done).
                        item = await q.get()
                    if item is None:
                        return
                    yield item.encode("utf-8")
            finally:
                # If the consumer is cancelled (client
                # disconnect), cancel the producer task
                # so the upstream LLM call (if still in
                # flight) is also cancelled. The producer's
                # `except BaseException` block logs the
                # cancellation, but the `wait_for` + the
                # `asyncio.CancelledError` propagation
                # prevents a leaked task.
                if not task.done():
                    task.cancel()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    return router
