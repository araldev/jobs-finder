# Tasks: chat-streaming

**Change**: `chat-streaming` • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
**LOC forecast**: ~1495 (single PR, well under 5000 budget)

## Work unit overview

Sliceamos el cambio en 11 work units, cada uno self-contained, committable
independiente, y testeable en aislamiento. Disciplina strict TDD por task:
RED (test que falla) → GREEN (mínimo código) → TRIANGULATE (≥2 casos por
comportamiento) → REFACTOR. Orden de aplicación respeta la dependency chain:
los contracts y las settings van primero (T-007, T-008 son independientes
y desbloquean T-002/T-006); el parser puro (T-003) es el bloque más fácil
de triangular; el client httpx (T-002) depende del Protocol (T-001) y de
la fixture (T-009). El use case (T-004) depende de T-002 + T-003. La ruta
(T-005) depende de T-004 + T-007. El wiring (T-006) cierra todo. Live
test (T-010) valida la captura one-time; docs (T-011) cierran el cambio.
Regresión de v1 (POST /jobs/chat intacto) se valida en T-006 +
T-009/T-010 al correr la suite completa.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1495 |
| 5000-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-always (orchestrator already resolved: auto-launch sdd-apply, 1495 < 5000) |
| Chain strategy | size:exception (not needed; single PR fits) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

> Note: orchestrator's review budget is 5000 (preflight). Design's
> 400-line per-PR guard is well below that. The 1495 LOC is the design's
> number; 400-line guard says single PR is fine.

## Tasks

### T-001: Add LLMStreamError + LLMRequestTimeoutError exceptions

**Type**: test-first
**Scope**:
- Write failing tests for `LLMStreamError` and `LLMRequestTimeoutError`
  (subclass invariant — must inherit from `LLMUnavailableError` so the
  route's `isinstance` chain discriminates them; distinct repr).
- Implement the two exception classes in
  `backend/src/jobs_finder/infrastructure/llm/exceptions.py`.
**Files**:
- `backend/src/jobs_finder/infrastructure/llm/exceptions.py` (extend)
- `backend/tests/unit/test_llm_exceptions.py` (new, 2 tests)
**Acceptance**:
- RED first; GREEN when classes exist with correct inheritance.
- `mypy --strict` clean.

### T-002: Add sse_keepalive_seconds to Settings + update .env.example

**Type**: test-first
**Scope**:
- Write 4 failing settings tests (default 15.0, le=60 rejects 120.0,
  ge=0 allows 0.0, env var `SSE_KEEPALIVE_SECONDS` loads).
- Implement `sse_keepalive_seconds: float = Field(default=15.0,
  validation_alias=AliasChoices("SSE_KEEPALIVE_SECONDS", ...), ge=0.0, le=60.0)`.
- Add doc block to `backend/.env.example` in "LLM chat filter" section.
**Files**:
- `backend/src/jobs_finder/infrastructure/config.py` (extend)
- `backend/.env.example` (extend)
- `backend/tests/unit/test_chat_settings.py` (new, 4 tests)
**Acceptance**:
- All 4 tests fail without the field; pass with it.
- `.env.example` documents the var + bounds + the "0 disables" semantics.

### T-003: Add stream_complete to LLMClientPort Protocol + extend FakeLLMClient

**Type**: test-first
**Scope**:
- Write a Protocol conformance test using `mypy --strict` (a fixture
  module assigning `FakeLLMClient()` to `LLMClientPort`).
- Extend the Protocol with `async def stream_complete(*, system, user)
  -> AsyncIterator[str]`.
- Add a `stream_complete` method to `FakeLLMClient` in
  `tests/conftest.py` (returns an empty async generator by default; each
  test that needs tokens provides its own override).
**Files**:
- `backend/src/jobs_finder/application/ports.py` (extend Protocol)
- `backend/tests/conftest.py` (extend `FakeLLMClient` with no-op
  `stream_complete` so existing tests don't break)
- `backend/tests/unit/test_llm_port.py` (new, 1 mypy-driven test or
  assignment-compatibility test)
**Acceptance**:
- Protocol extended; existing `FakeLLMClient` users still pass mypy
  (because of the no-op default in conftest).
- New mypy check is GREEN.

### T-004: MiniMaxLLMClient.stream_complete (httpx streaming)

**Type**: test-first
**Scope**:
- Write 5 failing unit tests using `httpx.MockTransport`:
  1. Valid SSE `data: {...}` lines + `[DONE]` → yields verbatim deltas
  2. Empty `delta.content` is skipped (no yield)
  3. Non-200 status → raises `LLMStreamError` with status in message
  4. No retry mid-stream (count MockTransport.handle_async_request
     calls — must be exactly 1)
  5. Malformed JSON line → raises `LLMStreamError` (or whichever the
     design specifies; reuses LLMStreamError per architecture)
- Implement `stream_complete` per the design snippet (httpx
  `.stream("POST", ...)`, `aiter_lines()`, `data: ` prefix strip,
  `[DONE]` sentinel, JSON parse, delta extract, no retry).
**Files**:
- `backend/src/jobs_finder/infrastructure/llm/_client.py` (extend)
- `backend/tests/unit/test_llm_client.py` (extend, +5 tests)
**Acceptance**:
- All 5 tests pass; `mypy --strict` clean.
- Plan B: if `httpx.MockTransport` + `aiter_lines` misbehaves, fallback
  to a custom `httpx.AsyncBaseTransport` subclass.

### T-005: StreamEventParser (pure accumulator + parse-at-end)

**Type**: test-first
**Scope**:
- Write 6 failing unit tests:
  1. `feed(chunk)` yields the chunk verbatim; `buffer` accumulates
  2. Plain JSON buffer → `finalize()` returns `LLMSelection` with
     `matching_ids` and `explanation`
  3. Markdown-fenced buffer → fences stripped, parses
  4. Hallucinated `matching_ids` not in `returned_ids` → silently
     dropped, WARNING log emitted, explanation preserved
  5. Malformed JSON → raises `LLMResponseParseError`
  6. Empty buffer + finalize → raises `LLMResponseParseError`
- Implement `StreamEventParser` dataclass in
  `infrastructure/llm/_parser.py` per design.
**Files**:
- `backend/src/jobs_finder/infrastructure/llm/_parser.py` (extend)
- `backend/tests/unit/test_llm_parser.py` (new, 6 tests)
**Acceptance**:
- All 6 tests pass; pure-function behavior isolated to one instance.

### T-006: FilterJobsByIntentUseCase.stream_execute (sibling of execute)

**Type**: test-first
**Scope**:
- Write 5 failing unit tests:
  1. 2-stage path: `StreamEventMeta` emitted first, then text chunks,
     then Done
  2. v1 path: NO `meta` event; only text + Done
  3. Text chunks emitted in feed order
  4. Empty aggregator → short-circuit to Done (no LLM call)
  5. Done carries jobs in aggregator order (not LLM JSON order)
  6. Hallucinated IDs from LLM dropped (parser → use case contract)
- Add `StreamEventMeta | Text | Done` dataclasses + `stream_execute`
  async generator method + private `_run_stage3_streaming` helper.
  The existing `execute()` method and `_run_stage3` helper stay
  UNCHANGED (REQ-BACKWARDS-COMPAT-001).
- Extend `FakeLLMClient.stream_complete` in test files (or override
  per-test) to return canned chunks.
**Files**:
- `backend/src/jobs_finder/application/usecases/filter_jobs_by_intent.py`
  (extend)
- `backend/tests/unit/test_filter_use_case.py` (extend, +5 tests)
**Acceptance**:
- All 5 tests pass; v1 `execute()` callers see zero behavior change.
- `mypy --strict` clean.

### T-007: Add ChatStreamTextEvent / MetaEvent / DoneEvent schemas

**Type**: test-first
**Scope**:
- Write 3 failing Pydantic round-trip tests.
- Implement the 3 event models in
  `backend/src/jobs_finder/presentation/schemas.py`.
**Files**:
- `backend/src/jobs_finder/presentation/schemas.py` (extend)
- `backend/tests/unit/test_chat_schemas.py` (new, 3 tests)
**Acceptance**:
- All 3 tests pass; `model.model_dump_json()` round-trips cleanly.

### T-008: build_chat_stream_router factory + SSE generator

**Type**: test-first
**Scope**:
- Write 3 unit tests for the factory:
  1. `build_chat_stream_router(...)` returns an `APIRouter` with
     `POST /jobs/chat/stream` registered
  2. Pre-stream 400 fires when `message` > `max_message_chars`
  3. Error mapping table: 6 exception types → 6 machine codes
     (parametrized test)
- Write 10 integration tests (in T-009 they share the test file; here
  we only need the route factory unit tests).
- Implement `build_chat_stream_router(use_case, max_message_chars,
  sse_keepalive_seconds)` in
  `backend/src/jobs_finder/presentation/routes/chat.py` per design
  (producer task + asyncio.Queue + consumer with `wait_for` for
  keepalive + `StreamingResponse`).
- Helpers: `_serialize_event(event, request_id)` →
  `f"event: <name>\ndata: <json>\n\n"`; `_serialize_error(exc)` →
  same shape with `code` + `message`.
**Files**:
- `backend/src/jobs_finder/presentation/routes/chat.py` (extend)
- `backend/tests/unit/test_chat_route.py` (extend, +3 tests)
**Acceptance**:
- All 3 tests pass; factory works with FakeLLMClient + a stub
  aggregator (use the project's existing test fakes).

### T-009: app_factory wiring + CORS fix + integration tests

**Type**: test-first
**Scope**:
- Write 2 new CORS integration tests (POST preflight OPTIONS, POST
  cross-origin real).
- Update existing `test_options_preflight_advertises_get_method` to
  also assert POST (the assertion widens; GET outcome unchanged).
- Write 10 new integration tests for `POST /jobs/chat/stream`
  (happy path, meta in 2-stage, no meta in v1, keepalive during
  slow aggregator, no keepalive when `sse=0`, 400 over-cap,
  error LLM unavailable, error parse, error timeout, headers).
- Update `app_factory.py`:
  - Line ~666: `allow_methods=["GET"]` → `allow_methods=["GET", "POST"]`
  - After v1 chat router block: `app.include_router(
    chat_routes.build_chat_stream_router(...))`
**Files**:
- `backend/src/jobs_finder/presentation/app_factory.py` (extend)
- `backend/tests/integration/test_cors.py` (extend, +2 tests, update
  pre-existing assertion)
- `backend/tests/integration/test_chat_streaming.py` (new, 10 tests)
- `backend/tests/unit/test_chat_wiring.py` (extend, +1 test for
  stream router registration)
**Acceptance**:
- All CORS + streaming integration tests pass.
- v1 `test_chat_endpoint.py` + `test_chat_endpoint_2stage.py` pass
  UNCHANGED (REQ-BACKWARDS-COMPAT-001).
- Full suite GREEN; ruff + mypy clean.

### T-010: Live capture fixture + LIVE-gated test (NEVER in CI)

**Type**: test-first
**Scope**:
- Manual one-time: capture a real MiniMax-M3 SSE response and commit
  it to `tests/fixtures/minimax_streaming_capture.txt` (raw bytes,
  `data: {...}\n\n` lines + `[DONE]`).
- Add a fixture-driven live test gated by
  `pytest.mark.skipif(not os.getenv("LLM_LIVE_TESTS"), reason=...)`
  that reads the capture file and asserts
  `MiniMaxLLMClient.stream_complete` parses it into ≥1 chunk.
- Add a small integration file `test_chat_streaming_live.py` with 1
  test that does an end-to-end live stream (also gated).
**Files**:
- `backend/tests/fixtures/minimax_streaming_capture.txt` (new, manual)
- `backend/tests/integration/test_chat_streaming_live.py` (new, 1 test)
- `backend/tests/unit/test_llm_client.py` (extend, +1 test gated
  by `LLM_LIVE_TESTS=1`)
**Acceptance**:
- Default `pytest` run: tests skip cleanly (not fail).
- `LLM_LIVE_TESTS=1 uv run pytest` runs the gated tests and they pass.
- AGENTS.md rule #1 honored: no live scraping in CI.

### T-011: backend/README.md docs (streaming endpoint + CORS + nginx)

**Type**: docs
**Scope**:
- New section "Chat filter — streaming endpoint" with curl example
  + event-type reference (meta / text / done / keepalive / error).
- CORS fix note in the existing chat-filter section.
- New section "Streaming behind nginx" with the
  `proxy_buffering off;` snippet + 1-line explanation +
  cross-reference to the new endpoint.
**Files**:
- `backend/README.md` (extend, ~80 LOC)
**Acceptance**:
- A `grep` for `proxy_buffering` or `nginx` returns the snippet.
- Section cross-references `POST /jobs/chat/stream`.

## Work unit ordering

Apply in this exact order (each task depends on the previous one's
artifacts being present, except T-001 and T-002 which are
independent and can be parallelized in different commits if desired):

1. T-001 (exceptions) — independent foundation
2. T-002 (settings + .env.example) — independent foundation
3. T-003 (Protocol + FakeLLMClient stub) — enables T-004
4. T-004 (`MiniMaxLLMClient.stream_complete`) — depends on T-003
5. T-005 (`StreamEventParser`) — independent pure function
6. T-006 (use case `stream_execute`) — depends on T-004 + T-005
7. T-007 (schemas) — small independent block
8. T-008 (route factory) — depends on T-006 + T-007
9. T-009 (app_factory wiring + integration tests) — depends on T-008
10. T-010 (live capture + LIVE-gated tests) — depends on T-004 (capture
    validates the client)
11. T-011 (README docs) — last; can ship in the same commit as T-009

T-001 and T-002 are interchangeable in the order. T-005 is independent
of T-003/T-004 (parser is a pure function with no LLM dep), so it can
ship in any order between T-002 and T-006.

## PR slice recommendation

- **PR strategy**: single-pr (1495 LOC, well under 5000 budget)
- **Work units in PR1**: T-001 through T-011
- **Commit slicing** (work-unit-commits skill):
  - Commit 1: T-001 (exceptions foundation)
  - Commit 2: T-002 (settings + env var)
  - Commit 3: T-003 (Protocol + FakeLLMClient stub)
  - Commit 4: T-004 (httpx streaming client + tests)
  - Commit 5: T-005 (StreamEventParser pure)
  - Commit 6: T-006 (use case `stream_execute` + tests)
  - Commit 7: T-007 (Pydantic schemas)
  - Commit 8: T-008 (route factory + unit tests)
  - Commit 9: T-009 (CORS fix + app wiring + integration tests) +
    T-011 (docs) — wire everything + ship the change
  - Commit 10: T-010 (live fixture + gated tests) — separate because
    it requires manual capture; can be a follow-up commit if the
    capture is done after the main PR merges
- **Review budget forecast**: 1495 LOC

## Strict TDD discipline (per `_shared/strict-tdd.md`)

For each task T-001 through T-009:
1. Write the failing test(s) FIRST in the test file
2. Run `cd backend && uv run pytest tests/unit/test_<file>.py -x`,
   confirm RED
3. Implement the smallest change to make it GREEN
4. Run the same pytest, confirm GREEN
5. Run `cd backend && uv run mypy` + `cd backend && uv run ruff check
   && uv run ruff format --check`, confirm CLEAN
6. Move to the next task

T-010 is special: the fixture is a manual capture, not a generated
artifact. The test reads the committed file. RED → GREEN happens
manually during the capture; subsequent runs are GREEN-by-fixture.

T-011 is docs-only — no TDD loop.

## Pre-apply checklist

- [x] All T-NNN files identified
- [x] All test files identified
- [x] Dependency order documented
- [x] Single PR (1495 LOC < 5000 budget)
- [x] No code changes outside `backend/` (only `backend/.env.example`
      and `backend/README.md` touched, both inside `backend/`)
- [x] `backend/.env.example` updated (T-002)
- [x] `backend/README.md` updated (T-011)

## Result contract (return at the end)

- **status**: `ok`
- **executive_summary**: 11 task breakdown slicing the 1495-LOC
  chat-streaming change into dependency-ordered, TDD-strict work
  units. Foundation (T-001/T-002) is independent; Protocol
  extension (T-003) unlocks the client (T-004); pure parser (T-005)
  runs in parallel; use case (T-006) joins client + parser; route
  (T-008) and wiring (T-009) close the loop; live capture (T-010)
  and docs (T-011) ship the change. Single PR (1495 LOC < 5000
  budget); no chained split needed.
- **artifacts**:
  - `openspec/changes/chat-streaming/tasks.md` (this file)
  - Engram `sdd/chat-streaming/tasks` (topic_key)
- **next_recommended**: `sdd-apply` (orchestrator will auto-launch
  because 1495 < 5000 budget; no user prompt needed)
- **risks**:
  - T-004: `httpx.MockTransport` + `aiter_lines` may misbehave on
    httpx 0.28.x; Plan B is a custom `AsyncBaseTransport` subclass.
  - T-010: requires a manual one-time capture of a real
    MiniMax-M3 stream. If the user forgets to do the capture,
    T-010 blocks (tests skip cleanly without it, but no
    production-fidelity validation).
  - T-006: the v1 `execute()` path must remain zero-behavior-change
    (REQ-BACKWARDS-COMPAT-001); the v1 integration tests in
    `test_chat_endpoint.py` + `test_chat_endpoint_2stage.py` are
    the regression anchor — they MUST pass unchanged.
- **skill_resolution**: `paths-injected` (`_shared/sdd-phase-common.md`
  loaded via orchestrator's preflight)
- **task_count**: 11
- **loc_forecast**: 1495
- **pr_recommendation**: `single-pr`
