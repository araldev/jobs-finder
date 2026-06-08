"""Unit tests for the chat-filter wiring in `app_factory.build_app` (T-016 of `ai-chat-filter`).

Spec: REQ-CHAT-001 (chat route registration), REQ-CHAT-002
(`ChatRateLimitMiddleware` mounting), design §2 (2-stage
rollout: code merged disabled, ops enables in prod via
`LLM_FILTER_ENABLED=true` + `LLM_API_KEY=<key>`).

The wiring is the composition-root concern. The factory:

  1. Builds an `httpx.AsyncClient` (when chat is enabled) so
     the `MiniMaxLLMClient` reuses the shared connection pool
     across requests (design §11 #1 — mirror the Redis client
     pattern).
  2. Builds a `MiniMaxLLMClient` via
     `build_minimax_llm_client(settings, http_client=httpx_client)`
     ONLY when `settings.llm_filter_enabled is True` AND
     `settings.llm_api_key is not None` (Q3 spec resolution:
     either condition missing → 404 for `/jobs/chat`).
  3. Builds a `FilterJobsByIntentUseCase(aggregator=..., llm=...)`.
  4. Stores the use case on `app.state.filter_use_case` (so a
     test can override it).
  5. Registers the chat router via
     `app.include_router(build_chat_router(...))`.
  6. Mounts `ChatRateLimitMiddleware` with
     `max_per_minute=settings.llm_filter_rate_limit_rpm`.
  7. Closes the httpx client in the lifespan's `finally` block.

The 3 test scenarios pin the conditional registration. Tests
inject fake use cases for the 3 source routes so the
composition root does not build real Playwright scrapers.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import SecretStr

from jobs_finder.application.ports import JobSearchCacheKey, JobSearchPort
from jobs_finder.application.usecases._cached_search import CachedJobSearchUseCase
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
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app

# ---------------------------------------------------------------------------
# Test fixtures — fake use cases for the 3 source routes
# ---------------------------------------------------------------------------


class _FakePort:
    """Minimal stand-in for a `JobSearchPort` (in-memory, empty)."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, keywords: str, location: str, limit: int = 20) -> list[Job]:
        self.calls += 1
        return []


def _build_fake_cached_use_case(source: str) -> CachedJobSearchUseCase:
    """Build a cached `*SearchJobsUseCase` wrapping a fresh fake port."""
    fake_port: JobSearchPort = _FakePort()
    cache: InMemoryTTLCache[JobSearchCacheKey, list[Job]] = InMemoryTTLCache(ttl_seconds=60.0)
    if source == "linkedin":
        return SearchLinkedInJobsUseCase(port=fake_port, cache=cache, source=source)
    if source == "indeed":
        return IndeedSearchJobsUseCase(port=fake_port, cache=cache, source=source)
    if source == "infojobs":
        return InfoJobsSearchJobsUseCase(port=fake_port, cache=cache, source=source)
    raise ValueError(f"unknown source: {source}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chat_path_registered(app: FastAPI) -> bool:
    """`True` if `/jobs/chat` is in the app's routes."""
    return any(getattr(r, "path", None) == "/jobs/chat" for r in app.routes)


def _chat_middleware_mounted(app: FastAPI) -> bool:
    """`True` if `ChatRateLimitMiddleware` is in the app's user_middleware."""
    for mw in app.user_middleware:
        if getattr(mw.cls, "__name__", None) == "ChatRateLimitMiddleware":
            return True
    return False


def _settings_with_chat(
    *,
    enabled: bool = True,
    api_key: SecretStr | None = None,
) -> Settings:
    """Build a `Settings` instance with the chat filter knobs set.

    Defaults: enabled + a test API key (the "happy path"
    configuration for the chat filter). The `api_key` default
    is `None` so the function's signature is callable without
    re-evaluating the `SecretStr` ctor at import time; the
    body sets the key to the test value when not provided.
    """
    if api_key is None:
        api_key = SecretStr("test-key")
    kwargs: dict[str, Any] = {
        "llm_filter_enabled": enabled,
        "llm_base_url": "https://api.example.invalid",  # not actually called
        "llm_request_timeout_seconds": 1.0,
    }
    kwargs["llm_api_key"] = api_key
    return Settings(**kwargs)


# ---------------------------------------------------------------------------
# Scenario 1: LLM filter enabled + API key set → chat route registered
# ---------------------------------------------------------------------------


def test_app_factory_registers_chat_route_when_filter_enabled_with_key() -> None:
    """Filter enabled + key set: route registered + middleware mounted.

    The production-wired path: the operator has set the env
    vars, the chat filter is ON, the LLM client is built, the
    use case is built, the route is registered, and the
    `ChatRateLimitMiddleware` is mounted. The test asserts
    the registration and mounting without actually calling
    the route (no LLM traffic).
    """
    settings = _settings_with_chat(enabled=True, api_key=SecretStr("test-key"))
    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )

    assert _chat_path_registered(app), (
        "chat route NOT registered when llm_filter_enabled=True + llm_api_key set"
    )
    assert _chat_middleware_mounted(app), "ChatRateLimitMiddleware NOT mounted when chat is enabled"


# ---------------------------------------------------------------------------
# Scenario 2: LLM filter disabled → chat route NOT registered
# ---------------------------------------------------------------------------


def test_app_factory_does_not_register_chat_route_when_filter_disabled() -> None:
    """`llm_filter_enabled=False` (even with API key set) → `/jobs/chat` NOT registered.

    The 2-stage rollout: code merged disabled, ops enables in
    prod. A test that sets `llm_filter_enabled=False` must
    produce an app without the chat route + without the
    chat rate-limit middleware.
    """
    settings = _settings_with_chat(enabled=False, api_key=SecretStr("test-key"))
    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )

    assert not _chat_path_registered(app), (
        "chat route registered when llm_filter_enabled=False; default is OFF"
    )
    assert not _chat_middleware_mounted(app), (
        "ChatRateLimitMiddleware mounted when llm_filter_enabled=False; "
        "no chat route means no chat bucket"
    )


# ---------------------------------------------------------------------------
# Scenario 3: LLM filter enabled + NO API key → chat route NOT registered
# ---------------------------------------------------------------------------


def test_app_factory_does_not_register_chat_route_when_api_key_missing() -> None:
    """`llm_filter_enabled=True` but `llm_api_key=None` → `/jobs/chat` NOT registered.

    Defense-in-depth (Q3 spec resolution): the operator enabled
    the filter flag but forgot to set the key. The wiring
    MUST NOT register the route (it would 502 on every call
    because the LLM client cannot be built without a key).
    A future caller that bypasses the conditional registration
    would fail loud in `build_minimax_llm_client` (the
    factory's `ValueError` is the safety net).
    """
    # The Pydantic Settings class rejects `llm_api_key=None`
    # by default (it accepts the env var), so we instantiate
    # with the key explicitly omitted. The factory pattern
    # uses `is not None` for the conditional check.
    settings = Settings(llm_filter_enabled=True)  # no llm_api_key
    assert settings.llm_api_key is None, "test setup: llm_api_key must be None"

    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )

    assert not _chat_path_registered(app), (
        "chat route registered when llm_api_key is None; "
        "the factory's ValueError would 502 every call"
    )
    assert not _chat_middleware_mounted(app), "ChatRateLimitMiddleware mounted without a chat route"


# ---------------------------------------------------------------------------
# 2-stage wire-up (T-009 of `chat-filter-2stage`).
#
# `app_factory.build_app()` now wires an `IntentExtractor` into
# the `FilterJobsByIntentUseCase` when `intent_extraction_enabled=True`
# (the new 6-`Settings`-field master switch from T-007). When
# `intent_extraction_enabled=False`, the use case is built with
# `intent_extractor=None` (the v1 backward-compat path —
# REQ-CHAT-INT-005).
# ---------------------------------------------------------------------------


def test_app_factory_wires_intent_extractor_when_2stage_enabled() -> None:
    """`Settings(intent_extraction_enabled=True)` builds a 2-stage use case.

    The 2-stage wire-up is the new PR2 path. The factory
    builds an `IntentExtractor` (with the `MiniMaxLLMClient`
    + `parse_intent_response` parser + the
    `effective_settings.intent_extraction_retry` count) and
    passes it to `FilterJobsByIntentUseCase`. The test
    inspects the use case to confirm the `IntentExtractor`
    was injected (NOT `None`).
    """
    settings = _settings_with_chat(enabled=True, api_key=SecretStr("test-key"))
    # Default `intent_extraction_enabled=True`.
    assert settings.intent_extraction_enabled is True
    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )
    use_case = app.state.filter_use_case
    assert use_case is not None
    # The 2-stage wire-up injects an `IntentExtractor`. The
    # `app_factory` exposes it via the use case's private
    # attribute (`_intent_extractor`).
    assert use_case._intent_extractor is not None  # noqa: SLF001
    # The dispatcher flag is on by default.
    assert use_case._intent_extraction_enabled is True  # noqa: SLF001
    # The default threshold / max_results match the spec.
    assert use_case._intent_extraction_confidence_threshold == 0.7  # noqa: SLF001
    assert use_case._intent_max_results == 100  # noqa: SLF001


def test_app_factory_does_not_wire_intent_extractor_when_2stage_disabled() -> None:
    """`Settings(intent_extraction_enabled=False)` → v1 use case with `intent_extractor=None`.

    Backward compat (REQ-CHAT-INT-005): setting the
    2-stage master switch to `False` reverts to the v1
    single-stage behavior. The factory MUST NOT build the
    `IntentExtractor` (it costs a real LLM call on every
    request) and MUST pass `intent_extractor=None` to the
    use case.
    """
    settings = _settings_with_chat(enabled=True, api_key=SecretStr("test-key"))
    settings_dict = settings.model_dump()
    settings_dict["intent_extraction_enabled"] = False
    settings = Settings(**settings_dict)
    assert settings.intent_extraction_enabled is False
    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )
    use_case = app.state.filter_use_case
    assert use_case is not None
    # The dispatcher flag is OFF; the use case will route to
    # `_execute_v1(...)` even though `intent_extractor` is
    # also None.
    assert use_case._intent_extraction_enabled is False  # noqa: SLF001
    assert use_case._intent_extractor is None  # noqa: SLF001


def test_app_factory_forwards_intent_extraction_retry_to_intent_extractor() -> None:
    """`Settings(intent_extraction_retry=2)` → `IntentExtractor(max_retries=2)`.

    The retry count flows from `Settings` to the
    `IntentExtractor` ctor so operators can bump the retry
    count without code changes.
    """
    settings = _settings_with_chat(enabled=True, api_key=SecretStr("test-key"))
    settings_dict = settings.model_dump()
    settings_dict["intent_extraction_retry"] = 2
    settings = Settings(**settings_dict)
    assert settings.intent_extraction_retry == 2
    app = build_app(
        use_case=_build_fake_cached_use_case("linkedin"),
        indeed_use_case=_build_fake_cached_use_case("indeed"),
        infojobs_use_case=_build_fake_cached_use_case("infojobs"),
        settings=settings,
    )
    use_case = app.state.filter_use_case
    assert use_case is not None
    extractor = use_case._intent_extractor  # noqa: SLF001
    assert extractor is not None
    assert extractor._max_retries == 2  # noqa: SLF001
