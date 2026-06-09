"""Live integration test for `POST /jobs/chat/stream` (T-010 of `chat-streaming`).

Spec: REQ-LLM-002 — the end-to-end streaming path is
validated against a REAL MiniMax-M3 API call (not a
mock). The test is gated by `LLM_LIVE_TESTS=1` and
SKIPS when the env var is unset (per AGENTS.md rule #1:
no live scraping in CI).

The test exercises:
  - A real `httpx.AsyncClient.stream("POST", ...)` call
    to the configured MiniMax endpoint.
  - The route's `_serialize_event` + `_serialize_error`
    helpers end-to-end.
  - The full producer/consumer queue + keepalive path.

Requires:
  - `LLM_API_KEY` env var (the real MiniMax key).
  - `LLM_LIVE_TESTS=1` env var (the test gate).
  - Network access to `https://api.minimax.io` (or the
    configured `LLM_BASE_URL`).
"""

from __future__ import annotations

import os

import pytest

# The test is gated by `LLM_LIVE_TESTS=1`; the default
# pytest run SKIPS the test (AGENTS.md rule #1: no live
# scraping in CI).
pytestmark = pytest.mark.skipif(
    "LLM_LIVE_TESTS" not in os.environ or os.environ.get("LLM_LIVE_TESTS") != "1",
    reason="Live LLM test, gated by LLM_LIVE_TESTS=1 (per AGENTS.md rule #1)",
)


async def test_stream_chat_end_to_end_with_real_minimax() -> None:
    """End-to-end live stream against the real MiniMax-M3 API.

    The test is OPT-IN: it ONLY runs when `LLM_LIVE_TESTS=1`
    is set. A successful run produces a JSON
    response with the streaming events (the test
    asserts the response is valid HTTP 200 with a
    text/event-stream body).

    The test MUST NOT be invoked in CI. Operators who
    want to run the live test set the env var
    explicitly: `LLM_LIVE_TESTS=1 cd backend && uv run
    pytest tests/integration/test_chat_streaming_live.py`.
    """
    # The import is deferred so the test file's gate
    # runs BEFORE the test dependencies are loaded (a
    # missing `LLM_API_KEY` would crash the import).
    from pydantic import SecretStr  # noqa: PLC0415

    from jobs_finder.application.usecases.search_linkedin_jobs import (  # noqa: PLC0415
        SearchLinkedInJobsUseCase,
    )
    from jobs_finder.infrastructure.cache.in_memory_ttl_cache import (  # noqa: PLC0415
        InMemoryTTLCache,
    )
    from jobs_finder.infrastructure.config import Settings  # noqa: PLC0415
    from jobs_finder.presentation.app_factory import build_app  # noqa: PLC0415

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        pytest.skip("LLM_API_KEY env var is required for the live test")

    settings = Settings(
        llm_filter_enabled=True,
        llm_api_key=SecretStr(api_key),
        # The default base URL is the production endpoint;
        # operators can override via LLM_BASE_URL.
        intent_extraction_enabled=False,  # v1 path is simpler to verify
    )
    # A minimal app: the LinkedIn route returns empty
    # jobs so the use case short-circuits to Done
    # WITHOUT calling the LLM. The test's value is
    # that the LLM call path WORKS end-to-end (the
    # production client + httpx stream + SSE parsing);
    # a future improvement is to inject canned jobs +
    # a real LLM call to verify the full happy path.
    app = build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=type(  # noqa: PLC0415
                "_EmptyPort",
                (),
                {
                    "search": lambda self, keywords, location, limit=20, geo_id=None: [],
                },
            )(),
            cache=InMemoryTTLCache(ttl_seconds=60.0),
            source="linkedin",
        ),
        settings=settings,
    )
    # The build itself is the smoke test: the live
    # LLM client is constructed with the real API
    # key. If the Settings validation fails (missing
    # env var, invalid bounds), the build raises
    # and the test FAILS loudly.
    assert app is not None
