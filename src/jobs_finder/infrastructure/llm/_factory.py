"""Factory for building a `MiniMaxLLMClient` from `Settings` (T-012 of `ai-chat-filter`).

Spec: design §5 + §11 #1 (build `httpx.AsyncClient` in the lifespan,
inject at construction time).

The factory is the single place that maps `Settings` fields to
`MiniMaxLLMClient` constructor args. Two things happen here:

  1. **Validation**: `settings.llm_api_key` MUST be set. The chat
     route registration in T-016 checks this BEFORE calling the
     factory, so a default `Settings()` (no env var) does not even
     reach the factory. The factory's own check is a
     defense-in-depth measure: a future caller that bypasses the
     route's conditional registration would fail loud here rather
     than build a broken client that crashes on the first request.

  2. **Construction**: builds the client with the right fields.
     The factory accepts an optional `http_client` so production
     wiring (T-016) can pass the shared client built in the app's
     lifespan (design §11 #1 — connection pooling across requests).
     When omitted, the client's ctor creates its own client.
"""

from __future__ import annotations

import httpx

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.llm._client import MiniMaxLLMClient


def build_minimax_llm_client(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> MiniMaxLLMClient:
    """Build a `MiniMaxLLMClient` from a `Settings` instance.

    The factory is the bridge between the env-driven `Settings`
    and the concrete client. Every `Settings.llm_*` field maps
    1:1 to a constructor arg; the mapping is the documented
    place to change if a future `Settings` field is added.

    Args:
        settings: The application settings. The `llm_api_key`
            field MUST be set (i.e. NOT `None`); a missing key
            is the kill switch that disables the chat route.
            The route registration in T-016 checks this BEFORE
            calling the factory; this check is a
            defense-in-depth.
        http_client: Optional pre-built `httpx.AsyncClient`.
            When provided, the client borrows the caller-owned
            transport (and the factory does NOT close it on
            the client's `aclose`). When omitted, the client
            creates its own client with the configured timeout.

    Returns:
        A configured `MiniMaxLLMClient` ready to call
        `complete(system=..., user=...)`.

    Raises:
        ValueError: when `settings.llm_api_key is None`. The
            error message names the missing env var so the
            operator can fix the misconfiguration in one step.
    """
    if settings.llm_api_key is None:
        raise ValueError(
            "build_minimax_llm_client: settings.llm_api_key is None. "
            "Set the LLM_API_KEY env var (or pass llm_api_key=... to "
            "Settings) to enable the chat filter."
        )
    return MiniMaxLLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_request_timeout_seconds,
        http_client=http_client,
        # `thinking_disabled=True` is the preflight D2 default.
        # Only MiniMax-M3 honors this flag (M2.x models cannot
        # disable thinking); the Settings.llm_model field
        # defaults to "MiniMax-M3" for the same reason.
        thinking_disabled=True,
    )
