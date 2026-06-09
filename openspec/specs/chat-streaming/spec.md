# Spec: chat-streaming

**Change**: `chat-streaming` • **Mode**: `both` • **Strict TDD**: ACTIVE

> Spec fundacional: no existe `openspec/specs/chat-streaming/spec.md`
> previo. Al archivar se promoverá a `openspec/specs/chat-streaming/spec.md`
> y los bloques MODIFIED se copiarán a los deltas de `ai-chat-filter` /
> `chat-filter-2stage`.

## Purpose

El frontend web (`frontend-scaffold`, paralelo) necesita renderizar la
respuesta del LLM con efecto "typewriter" — el endpoint v1 devuelve JSON
en 5-8s y muestra una pantalla en blanco inaceptable. Solución: exponer
`POST /jobs/chat/stream` (SSE) que streamea chunk por chunk, preservando
v1 intacto. Este cambio también corrige un bug CORS preexistente
(`allow_methods=["GET"]`) que bloquea TODA comunicación cross-origin POST.

## Requirements

### REQ-SSE-001: Streaming endpoint exists and emits text + done events in order

**Statement**: `POST /jobs/chat/stream` MUST accept the same
`ChatRequest{message}` body as v1 and return
`Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, `X-Accel-Buffering: no`. On LLM success the
stream MUST emit, in this order: (a) zero or one `event: meta` at start,
(b) one or more `event: text` with `{"delta": "<chunk>"}`, (c) one
terminal `event: done` with `{"jobs":[...], "explanation":"...",
"total_considered":N, "total_matched":M, "used_fallback":bool,
"request_id":"..."}`. After `done` the server MUST close the connection.

**Scenarios**:
#### Scenario: Happy-path streaming end-to-end with FakeLLMClient
- **Given** `FakeLLMClient.stream_complete` yields `["match", "ing", " ids"]`
- **And** the aggregator returns jobs `["j1", "j2", "j3"]`
- **When** the client sends `POST /jobs/chat/stream` with
  `{"message": "busco junior en Madrid"}`
- **Then** response is `200`, `Content-Type: text/event-stream`
- **And** parsed events are `meta?` → `text`(×N, concat == "matching ids")
  → `done`(jobs=["j1","j2","j3"], total_matched=3, used_fallback=False,
  request_id=<uuid>)
- **And** the connection closes after `done`

#### Scenario: v1 path skips the meta event
- **Given** `LLM_FILTER_ENABLED=false` (v1 path)
- **And** `FakeLLMClient.stream_complete` yields `["raw", " text"]`
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the parsed event sequence is `text`(×N) → `done`
- **And** NO `meta` event is emitted (stage-1 is skipped in v1 path)

#### Scenario: done event shape matches v1 ChatResponse
- **Given** a successful stream
- **When** the `done` event is parsed
- **Then** it MUST contain the same field names as v1 `ChatResponse`:
  `jobs`, `explanation`, `total_considered`, `total_matched`,
  `used_fallback`, `request_id`
- **And** `jobs` MUST be a JSON array of job objects (not a job ID list)

### REQ-SSE-002: Keepalive comments during quiet periods

**Statement**: The server MUST emit an SSE comment (`: keepalive\n\n`)
every `SSE_KEEPALIVE_SECONDS` (default `15.0`, env
`SSE_KEEPALIVE_SECONDS`, Pydantic bounds `gt=0.0, le=60.0`) during
intervals with no real event — primarily the stage-2 aggregator wait.
When `SSE_KEEPALIVE_SECONDS=0` the feature MUST be disabled. Keepalive
MUST NOT be sent between consecutive `text` events at normal LLM
emission rate.

**Scenarios**:
#### Scenario: Keepalive emitted during slow stage-2 aggregator
- **Given** a fake aggregator that takes 20s to return jobs
- **And** `sse_keepalive_seconds=5.0`
- **When** the client streams `POST /jobs/chat/stream`
- **Then** during the 20s wait the server emits ≥3 SSE comments
  matching `^: keepalive\n\n$`
- **And** no `text` or `done` events appear until the aggregator finishes
- **And** after the aggregator returns, the normal event sequence
  (`text` → `done`) plays out without further keepalives

#### Scenario: Keepalive disabled when SSE_KEEPALIVE_SECONDS=0
- **Given** `SSE_KEEPALIVE_SECONDS=0`
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the server emits NO `: keepalive` comments
- **And** the event sequence (`text` → `done`) is unchanged

#### Scenario: Invalid keepalive value rejected at startup
- **Given** `SSE_KEEPALIVE_SECONDS=120.0` (>60.0 upper bound)
- **When** the backend boots
- **Then** Pydantic MUST raise a `ValidationError` at settings load
- **And** the process MUST NOT start (same fail-fast contract as other
  `Settings` fields)

### REQ-SSE-003: Error events for LLM failures and timeouts

**Statement**: When the LLM call fails (`LLMUnavailableError`,
`LLMStreamError`, `LLMResponseParseError`) or times out
(`LLMRequestTimeoutError`), the server MUST emit exactly one SSE
`event: error` with `data: {"code": "<machine_code>", "message": "..."}`,
where `<machine_code>` ∈ `{"llm_unavailable", "llm_stream", "llm_parse",
"llm_timeout"}`, then close. No retry mid-stream (would destroy sent
chunks). The `error` event is terminal — no `done` follows.

**Scenarios**:
#### Scenario: LLM unavailable surfaces as error event
- **Given** `FakeLLMClient.stream_complete` raises `LLMUnavailableError`
  on the first chunk
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the server emits exactly one `event: error` with
  `{"code": "llm_unavailable", "message": "<reason>"}`
- **And** the connection is closed; no `done` event is emitted

#### Scenario: Parse error surfaces as error event
- **Given** `FakeLLMClient.stream_complete` yields valid chunks
- **And** `StreamEventParser.finalize()` raises `LLMResponseParseError`
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the server emits exactly one `event: error` with
  `{"code": "llm_parse", "message": "<reason>"}`
- **And** the connection is closed
- **And** the partial `text` events sent BEFORE the error are NOT
  rolled back (client already received them)

#### Scenario: Timeout surfaces as error event, upstream allowed to complete
- **Given** the LLM call exceeds `LLM_REQUEST_TIMEOUT_SECONDS`
- **When** the timeout fires
- **Then** the server emits one `event: error` with
  `{"code": "llm_timeout", "message": "..."}`
- **And** the connection is closed
- **And** the upstream httpx stream is NOT explicitly cancelled (per
  the proposal's user decision — cost is negligible)

### REQ-LLM-001: LLMClientPort.stream_complete Protocol method

**Statement**: `LLMClientPort` in `application/ports.py` MUST expose
`async def stream_complete(self, *, system: str, user: str) ->
AsyncIterator[str]` alongside `complete(...)`. The method MUST yield
one string per LLM token (verbatim `choices[0].delta.content` from the
OpenAI-compatible stream). The Protocol stays structural (not
`@runtime_checkable`); conformance is enforced by mypy --strict.
`FakeLLMClient` MUST grow a `stream_complete` method.

**Scenarios**:
#### Scenario: FakeLLMClient satisfies the extended Protocol under mypy --strict
- **Given** `LLMClientPort` now declares `stream_complete`
- **When** mypy --strict is run against `tests/conftest.py` and any
  test module that uses `FakeLLMClient`
- **Then** no mypy errors are reported
- **And** `FakeLLMClient` is structurally assignable to `LLMClientPort`
  (BOTH `complete` AND `stream_complete`)

#### Scenario: stream_complete yields one string per token
- **Given** the LLM emits 3 tokens: `["hello", " world", "!"]`
- **When** a caller iterates `async for chunk in client.stream_complete(...):`
- **Then** exactly 3 iterations occur
- **And** the concatenated chunks == "hello world!"
- **And** the method signature is keyword-only on `system` and `user`
  (mirroring `complete`)

### REQ-LLM-002: MiniMaxLLMClient.stream_complete uses httpx streaming

**Statement**: `MiniMaxLLMClient.stream_complete` MUST use
`httpx.AsyncClient.stream("POST", url, json={"stream": True, ...})` and
`response.aiter_lines()`. For each `data: <json>` line it MUST extract
`choices[0].delta.content` and yield it. If status != 200 it MUST raise
`LLMStreamError` with the status + body excerpt. Reuse the shared
`llm_http_client` from the app lifespan. NO retry mid-stream.

**Scenarios**:
#### Scenario: Parses valid OpenAI-style SSE chunk lines
- **Given** an `httpx.MockTransport` response streams
  `data: {"choices":[{"delta":{"content":"foo"}}]}\n\n` then
  `data: {"choices":[{"delta":{"content":"bar"}}]}\n\n` then
  `data: [DONE]\n\n`
- **When** `MiniMaxLLMClient.stream_complete` is iterated
- **Then** the yielded chunks are `["foo", "bar"]` in that order
- **And** the `[DONE]` sentinel line does NOT produce a yield

#### Scenario: Non-200 status raises LLMStreamError
- **Given** an `httpx.MockTransport` whose response is status `500`
  with body `{"error": "internal"}`
- **When** `MiniMaxLLMClient.stream_complete` is called
- **Then** it raises `LLMStreamError` with the status code embedded
  in the message
- **And** no chunks are yielded

#### Scenario: Empty delta content is skipped (not yielded)
- **Given** a chunk line `data: {"choices":[{"delta":{}}]}\n\n`
  (no `content` field)
- **When** the parser processes it
- **Then** no chunk is yielded for that line (policy: skip empties
  to avoid breaking downstream concatenation)

### REQ-PARSE-001: End-of-stream JSON extraction with strict validation

**Statement**: The `StreamEventParser` (new dataclass in
`infrastructure/llm/_parser.py`) MUST accumulate chunks in
`self.buffer`, expose `feed(chunk) -> Iterator[str]` (yields the chunk
verbatim for live `text` events), and `finalize() -> LLMSelection` that
reuses `parse_llm_response(self.buffer)`. `finalize` MUST strip markdown
code fences (`` ```json ... ``` ``) before parsing. `matching_ids` NOT in
the aggregator's actual returned jobs MUST be filtered out (policy:
silent drop with `WARNING` log; `explanation` preserved).

**Scenarios**:
#### Scenario: Plain JSON buffer parses successfully
- **Given** `StreamEventParser` is fed chunks concatenating to
  `'{"matching_ids":["j1","j2"],"explanation":"These match"}'`
- **When** `finalize()` is called (aggregator returned `j1, j2, j3`)
- **Then** returned selection has `matching_ids == {j1, j2}` and
  `explanation == "These match"`
- **And** `feed()` yielded the chunks verbatim in order

#### Scenario: Markdown-fenced JSON buffer parses after stripping
- **Given** the buffer is
  `` ```json\n{"matching_ids":["j1"],"explanation":"x"}\n``` ``
- **When** `finalize()` is called
- **Then** fences are stripped and the JSON parses
- **And** returned `matching_ids == {j1}`, `explanation == "x"`

#### Scenario: Strict id validation drops hallucinated ids
- **Given** the buffer parses to
  `{"matching_ids":["j1","j9"],"explanation":"all"}`
- **And** the aggregator returned only `j1, j2, j3`
- **When** `finalize()` is called
- **Then** returned `matching_ids == {j1}` (j9 is dropped)
- **And** a `WARNING` log line records the dropped ids
- **And** the `explanation` is preserved unchanged

#### Scenario: Malformed JSON at finalize raises LLMResponseParseError
- **Given** the buffer is `"this is not json at all"`
- **When** `finalize()` is called
- **Then** it raises `LLMResponseParseError` with a message referencing
  buffer length + failure point
- **And** the route catches it and emits `event: error` per REQ-SSE-003

### REQ-META-001: Stage-1 intent metadata as first event

**Statement**: When 2-stage is active and stage-1 produces a valid
`Intent`, the server MUST emit exactly one `event: meta` with
`data: {"intent": <Intent JSON>}` BEFORE the first `event: text`. The
`Intent` JSON MUST contain ONLY the fields the extractor returned (no
fabrication, no defaults). In v1 path (`LLM_FILTER_ENABLED=false`) NO
`meta` is emitted. On stage-1 parse error the stream MUST emit
`event: error` with `code: "stage1_parse"` and close (no fallback).

**Scenarios**:
#### Scenario: Meta event precedes text events in 2-stage path
- **Given** the 2-stage path is active
- **And** the intent extractor returns
  `Intent(q="python", location="Madrid", limit=20, sources=["linkedin"], intent_text="busco python en Madrid")`
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the first event is `event: meta` with
  `data.intent == {"q":"python","location":"Madrid","limit":20,"sources":["linkedin"],"intent_text":"busco python en Madrid"}`
- **And** ALL subsequent events come AFTER the meta in stream order

#### Scenario: Meta event not emitted in v1 path
- **Given** `LLM_FILTER_ENABLED=false` (v1 path)
- **When** the client streams `POST /jobs/chat/stream`
- **Then** the parsed event sequence is `text` → `done` with no `meta`
  event in between

### REQ-CACHE-001: SSE response cache headers

**Statement**: All responses from `POST /jobs/chat/stream` MUST set
`Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, and `X-Accel-Buffering: no` (the last
disables nginx buffering — see REQ-NGINX-001).

**Scenarios**:
#### Scenario: Required headers present on a 200 response
- **Given** a successful stream
- **When** the client inspects the response headers
- **Then** `Content-Type` starts with `text/event-stream`
- **And** `Cache-Control: no-cache`, `Connection: keep-alive`, and
  `X-Accel-Buffering: no` are all set

#### Scenario: Headers present even on error events
- **Given** the LLM call will fail
- **When** the client opens the stream
- **Then** the response headers still carry the four required headers
- **And** the body still uses SSE framing for the error event

### REQ-CORS-001: POST methods allowed in CORS

**Statement**: The CORS middleware in `presentation/app_factory.py`
MUST set `allow_methods=["GET", "POST"]` (changed from `["GET"]`).
Configuration MUST also include `Access-Control-Allow-Headers` for
`Content-Type` so JSON POST bodies preflight correctly.

**Scenarios**:
#### Scenario: CORS preflight for POST /jobs/chat/stream succeeds
- **Given** `OPTIONS /jobs/chat/stream` with
  `Origin: http://localhost:3000`,
  `Access-Control-Request-Method: POST`,
  `Access-Control-Request-Headers: content-type`
- **When** the preflight is sent
- **Then** response status is `200` (or `204`)
- **And** `Access-Control-Allow-Origin` includes `http://localhost:3000`
- **And** `Access-Control-Allow-Methods` contains `POST` and `GET`
- **And** `Access-Control-Allow-Headers` includes `content-type`

#### Scenario: Actual POST to stream succeeds cross-origin
- **Given** a browser at `http://localhost:3000` does `fetch` POST to
  `http://localhost:8000/jobs/chat/stream`
- **When** the request is sent
- **Then** the preflight succeeds (per the scenario above)
- **And** the actual POST returns `200` with the SSE body
- **And** the response carries
  `Access-Control-Allow-Origin: http://localhost:3000`

### REQ-BACKWARDS-COMPAT-001: v1 /jobs/chat endpoint unchanged

**Statement**: The existing `POST /jobs/chat` MUST remain unchanged in
behavior, request schema (`ChatRequest{message}`), response schema
(`ChatResponse`), rate limit, error mapping, and `X-Cache` header
semantics. The ONLY allowed change touching v1 is the CORS
`allow_methods` widening (REQ-CORS-001), strictly additive.

**Scenarios**:
#### Scenario: v1 POST /jobs/chat returns identical response shape
- **Given** the v1 integration test suite
  (`tests/integration/test_chat_endpoint_2stage.py`,
  `test_chat_endpoint_v1.py`) passes pre-change
- **When** the change is applied
- **Then** the same tests pass post-change with zero modifications
- **And** no test under `tests/` is updated to "fix" a v1 regression
  (regressions are real failures, fixed in the new code, not the test)

#### Scenario: v1 endpoint registered alongside stream endpoint
- **Given** the app is built with chat enabled
- **When** the routes are inspected
- **Then** BOTH `POST /jobs/chat` and `POST /jobs/chat/stream` are
  registered
- **And** both share the same per-user rate limit middleware
  (REQ-CHAT-002 from the v1 spec)

### REQ-NGINX-001: Documented nginx configuration

**Statement**: `backend/README.md` MUST document the required nginx
config for the `/jobs/chat/stream` location: `proxy_buffering off;` —
SSE breaks if nginx buffers. Docs MUST also mention the
`X-Accel-Buffering: no` response header the server sets automatically.

**Scenarios**:
#### Scenario: README contains the nginx snippet
- **Given** the `backend/README.md` file
- **When** a reader searches for `proxy_buffering` or `nginx`
- **Then** they find a concrete nginx `location` block with
  `proxy_buffering off;` and a one-line explanation of why
- **And** the section cross-references the `POST /jobs/chat/stream`
  endpoint doc

### REQ-ERROR-MAPPING-001: Domain exceptions mapped to SSE error events

**Statement**: The `StreamEventParser`, the use case's `stream_execute`,
and the route's generator MUST translate domain exceptions to SSE
`event: error` events with a stable machine code:
`LLMUnavailableError`→`llm_unavailable`, `LLMStreamError`→`llm_stream`,
`LLMResponseParseError`→`llm_parse`,
`LLMRequestTimeoutError`→`llm_timeout`, `JobSearchError` (other)→
`internal`, stage-1 intent parse failure→`stage1_parse`. The HTTP
status of the SSE response is ALWAYS `200` once the stream has
started. Only pre-stream validation failures return non-200,
matching v1 behavior.

**Scenarios**:
#### Scenario: Each domain exception maps to its machine code
- **Given** a parametrized test covering the 6 exception types
- **When** each exception is raised inside `stream_execute` (or the
  route generator)
- **Then** the SSE stream contains exactly one `event: error` with
  the expected `code` field
- **And** the response HTTP status is `200`
- **And** no `done` event is emitted after the error

#### Scenario: Pre-stream validation returns 400 (not SSE)
- **Given** a request with `message` length > `max_message_chars`
- **When** the client sends `POST /jobs/chat/stream`
- **Then** the response status is `400` with a JSON error body
  (matching v1's validation contract)
- **And** the response is NOT an SSE stream

## MODIFIED Requirements (capabilities preexistentes)

> Al archivar, estos bloques se copiarán a los deltas correspondientes
> en `openspec/changes/chat-streaming/specs/<domain>/spec.md`.

### MODIFIED — ai-chat-filter::REQ-CHAT-001 (chat request/response)
**Statement (updated)**: Chat requests MUST be accepted on BOTH
`POST /jobs/chat` (non-streaming) and `POST /jobs/chat/stream` (SSE).
Same `ChatRequest{message}` body, same per-user rate limit. v1's
response shape and status codes are preserved verbatim
(REQ-BACKWARDS-COMPAT-001). Stream contract: REQ-SSE-001/002/003 +
REQ-META-001 + REQ-CACHE-001. (Previously: only `POST /jobs/chat`
existed.) **Scenarios**: REQ-SSE-001 happy path, REQ-BACKWARDS-COMPAT-001.

### MODIFIED — ai-chat-filter::REQ-CHAT-002 (per-user rate limit)
**Statement (updated)**: The per-user rate limit MUST apply to BOTH
endpoints with the same `LLM_RATE_LIMIT_PER_MINUTE` value. Shared key:
a v1 request and a stream request within the same minute count as 2.
**Scenarios**: existing rate-limit tests + new test against the stream
endpoint (stub LLM).
### MODIFIED — chat-filter-2stage::REQ-FILTER-2STAGE-001 (execute method)
**Statement (updated)**: `FilterJobsByIntentUseCase` MUST expose BOTH
`execute(...)` (returns `ChatResponse`) AND `stream_execute(...)`
(returns `AsyncIterator[StreamEvent]` yielding `meta`→`text`×N→`done`).
Shared dispatch + validation. `stream_execute` is the only path that
yields `StreamEventMeta` (2-stage branch) and multiple `StreamEventText`
chunks. The `stream_complete` call lives in the new
`_run_stage3_streaming` helper. (Previously: only `execute(...)`.)
**Scenarios**: REQ-SSE-001 + REQ-META-001.

## Out of scope

- WebSocket alternative (SSE covers the unidirectional case).
- Aborting the upstream LLM call when the client disconnects (user
  decision: cost is negligible; complexity not worth it).
- Per-event backpressure (LLM emits 30-50 tok/s; browser keeps up).
- Persisting streams in Redis / message queues (streams are ephemeral).
- Multi-turn conversation history (single-shot chat).
- Tool use / function calling.
- Prompt caching (not supported by MiniMax-M3 with `thinking: disabled`).
- Token usage tracking mid-stream (`request_id` log at end is enough).
- Frontend changes (covered by `frontend-scaffold`).
- Replacing the v1 endpoint (preserved as the non-streaming fallback).

## Open questions

None — all decisions resolved in the proposal phase. Two items
nailed down during spec writing, flagged to the `frontend-scaffold`
consumer for awareness (do NOT block the backend spec):

1. **Empty delta content** (REQ-LLM-002 third scenario): policy is
   "skip empty strings, don't yield them". The frontend's accumulator
   should treat absent chunks as "no typewriter tick", not "type a space".
2. **Strict id validation** (REQ-PARSE-001 third scenario): hallucinated
   `matching_ids` are dropped silently with a `WARNING` log. The
   `explanation` is NOT rewritten. Surfacing dropped IDs in the UI is a
   follow-up; the SSE wire format does not carry them today.

## Acceptance criteria

- [ ] All REQ-* covered by passing tests in
      `tests/integration/test_chat_streaming.py` (NEW) + modified
      unit test files.
- [ ] Strict TDD evidence: every requirement has RED → GREEN →
      TRIANGULATE trail; test files exist BEFORE implementation files.
- [ ] `cd backend && uv run pytest` GREEN, 0 regressions on the
      1036-test baseline.
- [ ] `cd backend && uv run mypy --strict` clean.
- [ ] `cd backend && uv run ruff check` clean.
- [ ] `cd backend && uv run ruff format --check` clean.
- [ ] `POST /jobs/chat` (v1) integration tests pass WITHOUT
      modification (REQ-BACKWARDS-COMPAT-001).
- [ ] CORS preflight `OPTIONS /jobs/chat/stream` (Origin
      `http://localhost:3000`) returns
      `Access-Control-Allow-Methods: GET, POST` (REQ-CORS-001).
- [ ] Keepalive: 5s fake-aggregator wait +
      `sse_keepalive_seconds=2.0` asserts ≥2 `: keepalive`
      comments arrived (REQ-SSE-002).
- [ ] All 6 error-mapping scenarios pass with stable `code` values
      (REQ-ERROR-MAPPING-001).
- [ ] Live test gated by `LLM_LIVE_TESTS=1` via
      `pytest.mark.skipif(not os.getenv("LLM_LIVE_TESTS"), ...)`
      (REQ-LLM-002).
- [ ] `backend/README.md` contains the nginx `proxy_buffering off`
      snippet + cross-reference to the streaming endpoint
      (REQ-NGINX-001).
- [ ] `backend/.env.example` documents `SSE_KEEPALIVE_SECONDS`
      default + bounds.
- [ ] Fixture `tests/fixtures/minimax_streaming_capture.txt` exists
      and is exercised by
      `test_llm_client.py::test_stream_complete_parses_real_capture`
      (one-time manual capture, never in CI per AGENTS.md rule #1).
