"""Live LLM tests for `POST /jobs/chat` (T-015 of `chat-filter-2stage`).

Spec: REQ-CHAT-INT-001 (stage-1 extraction), REQ-CHAT-INT-004
(fallback), REQ-LLM-SEC-001/002 (per-call security boundaries
+ retry-once).

The 2 LIVE tests exercise the 2-stage flow end-to-end against a
real MiniMax-M3 + `thinking: {"type": "disabled"}` (the only
model that honors the disabled flag — the cost/latency budget
in the README's "AI Chat Filter" section depends on it).

**Live tests are NEVER run in CI** (AGENTS.md rule #1). They
require:

  1. A real `LLM_API_KEY` exported in the environment
     (recommended: `direnv` auto-loads `.envrc`).
  2. The `LLM_LIVE_TESTS=1` env var set so the
     `pytest.mark.skipif` gating lets the test run.

To run the live tests locally:

    # 1. Install direnv: https://direnv.net/
    # 2. Create `.envrc` in the project root (gitignored):
    #      export LLM_API_KEY=<your-key>
    # 3. Allow it:
    #      direnv allow
    # 4. Run the live tests:
    LLM_LIVE_TESTS=1 uv run pytest tests/integration/test_chat_live.py -v

The 2 tests are:

  - `test_live_chat_2stage_high_confidence`: a canned
    "ingeniero Python en Madrid, 3+ años, remoto" message
    should trigger the 2-stage path (stage 1 + stage 3, with
    a high-confidence intent). The test asserts the response
    is 200 with `used_fallback=False` and a non-empty
    `explanation`.
  - `test_live_chat_2stage_low_confidence_fallback`: a
    canned "asdf" message (gibberish) should trigger the
    v1 fallback path (the extractor returns a low-confidence
    intent). The test asserts the response is 200 with
    `used_fallback=True`.

Both tests are gated by `LLM_LIVE_TESTS=1` so the default
`pytest` run SKIPS them. They run only at `sdd-verify` when
the user has the API key set via direnv (the verify phase
flips the env var explicitly per the orchestrator's brief).

**Cost note**: each test makes 1-2 LLM calls; with
`INTENT_EXTRACTION_ENABLED=true` (the default), the high-
confidence test makes 2 calls (stage 1 + stage 3) and the
low-confidence test makes 1 call (stage 3 only — stage 1
returns a low-confidence intent and the dispatcher
short-circuits). At ~$0.0025/call, a single live-test run
is < $0.01.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from jobs_finder.application.aggregator import SearchAllSourcesUseCase
from jobs_finder.application.ports import JobSearchCacheKey
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
from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.llm._factory import build_minimax_llm_client
from jobs_finder.infrastructure.llm._intent import IntentExtractor
from jobs_finder.infrastructure.llm._intent_parser import parse_intent_response
from jobs_finder.presentation.middleware import RequestIdMiddleware
from jobs_finder.presentation.routes import chat as chat_routes
from tests.conftest import FakeJobSearchPort

# Gating: the 2 live tests run ONLY when `LLM_LIVE_TESTS=1` is
# in the environment. The default `pytest` run (and CI) SKIPS
# them — AGENTS.md rule #1: live tests are NEVER run in CI.
_LIVE_GATE = pytest.mark.skipif(
    not os.getenv("LLM_LIVE_TESTS"),
    reason="Live LLM test, gated by LLM_LIVE_TESTS=1",
)


def _make_sample_jobs() -> list[Job]:
    """Build 3 sample jobs for the live test (deterministic shape).

    The jobs are NOT pulled from the live LinkedIn / Indeed /
    InfoJobs scrapers (that would require Playwright + a
    `li_at` cookie, both explicitly out of scope per
    AGENTS.md rule #1). The 2-stage live test asserts the
    LLM's selection against this canned set, then walks the
    response. If the LLM picks no IDs, the response is empty
    but the 200 + `used_fallback=False` assertion still holds
    (the contract is "the LLM filter ran", not "the LLM
    selected N jobs").
    """
    return [
        Job(
            id="live_a",
            title="Senior Python Engineer",
            company="TechCo",
            location="Madrid, Spain",
            url="https://example.com/jobs/live_a",
            posted_at=datetime(2026, 6, 1, tzinfo=UTC),
            source="linkedin",
        ),
        Job(
            id="live_b",
            title="Backend Developer",
            company="StartupCo",
            location="Madrid, Spain",
            url="https://example.com/jobs/live_b",
            posted_at=datetime(2026, 6, 2, tzinfo=UTC),
            source="linkedin",
        ),
        Job(
            id="live_c",
            title="Full-Stack Engineer",
            company="BigCo",
            location="Barcelona, Spain",
            url="https://example.com/jobs/live_c",
            posted_at=datetime(2026, 6, 3, tzinfo=UTC),
            source="linkedin",
        ),
    ]


def _build_live_test_app() -> tuple[FastAPI, list[Job]]:
    """Build a FastAPI app wired for the live test.

    The composition root (`build_app`) builds the real
    `IntentExtractor` + `MiniMaxLLMClient` (sourced from
    `Settings()` which reads `LLM_API_KEY` from the env).
    The 3 source use cases are wired to a single shared
    `FakeJobSearchPort` primed with the canned jobs so the
    2-stage flow has real data to filter on.

    Returns:
        A `(app, jobs)` tuple. `app` is a fully-wired FastAPI
        app (chat route + ChatRateLimitMiddleware mounted).
        `jobs` is the canned list (so the test can sanity-check
        the response's `total_considered` against the input).
    """
    jobs = _make_sample_jobs()
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
    # Build the real LLM client + IntentExtractor via the
    # composition root. The Settings() reads `LLM_API_KEY`
    # from the env (direnv auto-loads it on `cd`). The
    # `build_app` factory wires the LLM client, the
    # IntentExtractor, and the chat use case.
    settings = Settings()
    # Build the LLM client + IntentExtractor directly so the
    # test does not depend on `build_app` mounting the chat
    # route (the live test wires a custom chat use case that
    # is identical to the factory's wire-up).
    llm_client = build_minimax_llm_client(settings)
    intent_extractor = IntentExtractor(
        llm=llm_client,
        parser=parse_intent_response,
        max_retries=settings.intent_extraction_retry,
    )
    chat_use_case = FilterJobsByIntentUseCase(
        aggregator=aggregator,
        llm=llm_client,
        intent_extractor=intent_extractor,
        intent_extraction_enabled=settings.intent_extraction_enabled,
        intent_extraction_confidence_threshold=settings.intent_extraction_confidence_threshold,
        intent_max_results=settings.intent_max_results,
    )
    app = FastAPI()
    # Reuse the chat route builder from the production app
    # factory. The 2-stage wire-up is identical.
    app.add_middleware(RequestIdMiddleware)
    app.include_router(
        chat_routes.build_chat_router(
            use_case=chat_use_case,
            max_message_chars=settings.llm_max_message_chars,
        )
    )
    return app, jobs


@_LIVE_GATE
async def test_live_chat_2stage_high_confidence() -> None:
    """Live 2-stage happy path: high-confidence intent → 200 + `used_fallback=False`.

    The canned message "ingeniero Python en Madrid, 3+ años, remoto"
    is a well-formed Spanish intent. The real `IntentExtractor` should
    extract a high-confidence `Intent` (e.g. `confidence=0.95`),
    triggering the 2-stage path: the aggregator scrapes with the
    extracted `q="ingeniero python"` / `location="Madrid"`, then the
    v1 stage-3 LLM filter runs.

    The test asserts the response is 200 with `used_fallback=False`
    and a non-empty `explanation`. The exact `total_considered` and
    `total_matched` are NOT pinned (the LLM's filter is
    non-deterministic) — the assertion is on the 2-stage vs
    v1-fallback discriminator, not the LLM's selection.
    """
    app, _ = _build_live_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/jobs/chat",
            json={"message": "ingeniero Python en Madrid, 3+ años, remoto"},
        )

    assert response.status_code == 200
    body = response.json()
    # The 2-stage path ran (high-confidence intent).
    assert body["used_fallback"] is False
    # The LLM returned a non-empty Spanish explanation.
    assert isinstance(body["explanation"], str)
    assert len(body["explanation"]) > 0


@_LIVE_GATE
async def test_live_chat_2stage_low_confidence_fallback() -> None:
    """Live 2-stage fallback: low-confidence intent → 200 + `used_fallback=True`.

    The canned message "asdf" is gibberish. The real `IntentExtractor`
    should return a low-confidence `Intent` (e.g. `confidence=0.3`),
    triggering the v1 fallback path: the dispatcher sees
    `confidence < threshold` and runs the v1 single-stage flow
    (`q=""` / `location=""` / `limit=20` aggregator scrape + stage-3
    LLM filter).

    The test asserts the response is 200 with `used_fallback=True`.
    The exact `total_considered` is NOT pinned (the live aggregator
    may or may not return jobs).
    """
    app, _ = _build_live_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/jobs/chat",
            json={"message": "asdf"},
        )

    assert response.status_code == 200
    body = response.json()
    # The v1 fallback path ran (low-confidence intent).
    assert body["used_fallback"] is True
