"""`POST /jobs/chat` chat-filter route (T-014 of `ai-chat-filter`).

Spec: REQ-CHAT-001 (chat request/response), REQ-LLM-003 (strict-
subset ID validation — the use case, T-013, owns the validation),
REQ-CHAT-002 (per-user rate limit — the `ChatRateLimitMiddleware`
in T-015 enforces it).

The route is a thin composition layer over the
`FilterJobsByIntentUseCase` (T-013). It:

  1. Reads the `ChatRequest` body (Pydantic `message: str`).
  2. Enforces the explicit char cap (`len(req.message) >
     max_message_chars` → 400 with `{"detail": "message exceeds
     N chars (got M)"}` per Q2). The cap is NOT a Pydantic
     constraint — the route raises `HTTPException(400)` so the
     rejection body shape is the route's `HTTPException` shape,
     not Pydantic's `RequestValidationError` shape. This mirrors
     the `sources` validation pattern in `aggregator.py:78-106`.
  3. Normalizes the message: `unicodedata.normalize("NFC",
     req.message).casefold().strip()` (REQ-CHAT-001 + preflight
     cache-key normalization decision). The normalized form is
     the `message` the use case forwards to the LLM; the
     aggregator receives empty `q` / `location` (the v1
     convention where the message IS the intent).
  4. Calls the use case's `execute(message=normalized, q="",
     location="", limit=20, sources=None)`.
  5. Maps exceptions:
     - `LLMUnavailableError` → 502 via route-local
       `HTTPException` with body `{"detail": "LLM provider
       unavailable: <msg>"}`. The global `JobSearchError`
       handler would also map the parent class to 502, but the
       route-local catch is explicit + testable.
     - `LLMResponseParseError` → 422 via route-local
       `HTTPException` with body `{"detail": "LLM response
       could not be parsed: <msg>"}`. The global handler maps
       `JobSearchError` to 502, so a route-local catch is
       required for the 422 mapping.
     - Other `JobSearchError`s propagate to the global handler
       (per-source errors from the aggregator land at 502).
  6. Returns the `ChatResponse` mapped from the
     `FilteredJobsResult` (jobs via `to_response(...)`,
     explanation, total_considered, total_matched).

The route is registered conditionally in `app_factory.build_app`
(T-016) — the chat endpoint is OFF when
`settings.llm_filter_enabled` is `False` OR when
`settings.llm_api_key` is `None`. When OFF, the route is NOT
registered and `POST /jobs/chat` returns 404 (the safest default
per design §2).
"""

from __future__ import annotations

import unicodedata

from fastapi import APIRouter, HTTPException, Request

from jobs_finder.application.usecases.filter_jobs_by_intent import (
    FilterJobsByIntentUseCase,
)
from jobs_finder.infrastructure.llm.exceptions import (
    LLMResponseParseError,
    LLMUnavailableError,
)
from jobs_finder.presentation.schemas import (
    ChatRequest,
    ChatResponse,
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
        return ChatResponse(
            jobs=[to_response(j) for j in result.jobs],
            explanation=result.explanation,
            total_considered=result.total_considered,
            total_matched=result.total_matched,
        )

    return router


# The factory returns the router. The composition root
# (T-016) mounts it on the app when the chat filter is
# enabled. `__all__` keeps the public surface stable for the
# test that imports `build_chat_router` (the factory function).
__all__ = ["build_chat_router"]
