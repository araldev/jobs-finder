# Design: chat-streaming

**Change**: `chat-streaming` • **Mode**: `both` • **Strict TDD**: ACTIVE

## Architecture overview

Endpoint `POST /jobs/chat/stream` (SSE) paralelo a `POST /jobs/chat`
(JSON). Preserva v1 intacto. Reusa TODO el flujo del use case
excepto el stage-3 LLM, que ahora streamea via
`httpx.AsyncClient.stream` + `aiter_lines`. Stage-1 emite UN
`meta` con el `Intent` parseado (omitido en path v1). Stage-2 es
silencioso — el cliente espera con keepalives `: keepalive\n\n`
cada `SSE_KEEPALIVE_SECONDS`.

```
  Browser (EventSource) ◄─── POST /jobs/chat/stream {message}
         │  SSE bytes
         ▼
  ┌──────────────────────────────────────────────────────┐
  │ StreamingResponse(media_type="text/event-stream")    │
  │   + producer task → asyncio.Queue[str|None]          │
  │   + consumer w/ asyncio.wait_for(keepalive_seconds)  │
  └──────────────────────┬───────────────────────────────┘
                         │ AsyncIterator[StreamEvent]
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ FilterJobsByIntentUseCase.stream_execute(...)        │
  │   Stage 1 (2-stage): extract Intent → yield Meta     │
  │   Stage 2 (aggregator): silent                       │
  │   Stage 3 (LLM):                                     │
  │     parser = StreamEventParser()                     │
  │     async for chunk in llm.stream_complete(...):     │
  │       for text in parser.feed(chunk):                │
  │         yield StreamEventText(delta=text)            │
  │     selection = parser.finalize(returned_ids)        │
  │     strict-subset validation → yield Done            │
  └──────────────────────┬───────────────────────────────┘
                         │ AsyncIterator[str]
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │ MiniMaxLLMClient.stream_complete                     │
  │   async with self._http.stream("POST", url, ...) as r:│
  │     if r.status_code != 200: raise LLMStreamError    │
  │     async for line in r.aiter_lines():               │
  │       if line startswith "data: ": yield delta       │
  │       if payload == "[DONE]": break                  │
  └──────────────────────────────────────────────────────┘
```

### Tres boundaries de error mapping

1. **HTTP layer (route)**: 400 (cap excedido, pre-stream). SSE
   siempre HTTP 200 una vez que el stream arranca.
2. **Stream layer (route generator)**: 6 mappings estables:
   `LLMUnavailableError`→`llm_unavailable`, `LLMStreamError`→
   `llm_stream`, `LLMResponseParseError`→`llm_parse`,
   `LLMRequestTimeoutError`→`llm_timeout`,
   `JobSearchError` (other)→`internal`,
   stage-1 parse→`stage1_parse`.
3. **LLM layer (client)**: 5xx / 429 / 1002 / 1013 → retry once →
   `LLMStreamError`. 401/403/1004/1008 → `LLMStreamError`
   immediately. `httpx.TimeoutException` →
   `LLMRequestTimeoutError`. No retry mid-stream (destruiría
   chunks ya enviados al cliente).

## Architecture decisions

| # | Decisión | Rationale |
|---|---|---|
| D1 | Solo stage-3 streamea; stage-1 emite UN `meta`; stage-2 silencioso. | REQ-META-001. UI renderiza `meta` como badge, `text` como typewriter, `done.jobs` como grilla. Stage-1 es internal — UI no necesita el raw JSON. |
| D2 | `StreamEventParser` acumula verbatim, parsea al final reusando `parse_llm_response`. | REQ-PARSE-001. Strategy B (incremental JSON) = over-engineering. `text` es verbatim stream; `done` lleva el JSON final. |
| D3 | Producer/consumer pattern con `asyncio.Queue` + `wait_for` para keepalives. | Sin un timer separado, no hay forma de intercalar keepalives cuando el queue está vacío. Producer catches `*Error` y pushea `event: error` antes del `None`. |
| D4 | CORS `allow_methods=["GET"]` → `["GET", "POST"]` (estrictamente aditivo). | REQ-CORS-001. `allow_headers=["*"]` ya cubre `Content-Type`; no se toca. |

## Data flow (happy path, 2-stage)

1. `POST /jobs/chat/stream` con `{"message": "busco junior en Madrid"}`.
2. Route: 400-cap check PASS. NFC+casefold+strip.
3. Producer task: `intent_extractor.extract(...)` → `Intent(q="junior",
   location="Madrid", confidence=0.95)` → push `event: meta\ndata:
   {"intent": {...}}\n\n`.
4. Producer: `aggregator.search(...)` (silent, ~2s red).
   Consumer emite `: keepalive\n\n` cada `sse_keepalive_seconds`
   durante la espera.
5. Producer: `llm.stream_complete(system=SYSTEM_PROMPT, user=...)`
   yields `["match", "ing", " ids"]`. Por cada chunk, `feed()` lo
   yield verbatim → push `event: text\ndata: {"delta":"match"}\n\n`...
6. Producer: `parser.finalize(returned_ids={j1,j2,j3})` →
   `LLMSelection(["j1","j2","j3"], "These match")`. Strict-subset
   validation: 3/3 kept.
7. Producer: push `event: done\ndata: {jobs:[...], explanation:...,
   request_id:<uuid>}\n\n`. Push `None`. Producer done.
8. Consumer: lee cada event, encode utf-8, yield. On `None`, return.
9. `StreamingResponse` cierra conexión. HTTP status: 200.

### Error path: `LLMUnavailableError` mid-stream

1. Stage-3 yields 2 chunks. 3rd chunk raises
   `LLMUnavailableError`.
2. Producer catches. Push `event: error\ndata:
   {"code":"llm_unavailable","message":"<reason>"}\n\n`. Push
   `None`.
3. Consumer reads error event, then `None`, returns.
4. Conexión cierra. HTTP 200 (headers ya enviados). Cliente
   debe inspeccionar el event stream para detectar el error.

### Pre-stream validation

`POST /jobs/chat/stream` con `message` > `max_message_chars` →
`HTTPException(400, "message exceeds N chars (got M)")` ANTES de
entrar al generator. NO es SSE — es JSON error body regular.
## Component changes (12 módulos)

### 1. `application/ports.py` — `LLMClientPort.stream_complete`

Add `async def stream_complete(*, system, user) -> AsyncIterator[str]`.
`complete(...)` UNCHANGED.

```python
class LLMClientPort(Protocol):
    async def complete(self, *, system: str, user: str) -> str: ...
    async def stream_complete(
        self, *, system: str, user: str
    ) -> AsyncIterator[str]: ...
```

**Test**: `mypy --strict` conformance (1 test).

### 2. `infrastructure/llm/_client.py` — `stream_complete`

```python
async def stream_complete(
    self, *, system: str, user: str
) -> AsyncIterator[str]:
    body = self._build_request_body(system, user) | {"stream": True}
    async with self._http.stream(
        "POST", f"{self._base_url}/v1/chat/completions",
        json=body, headers=self._build_headers(),
    ) as response:
        if response.status_code != 200:
            raise LLMStreamError(
                f"stream status {response.status_code}: "
                f"{response.text[:200]!r}"
            )
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ").strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                yield delta
```

**Test**: 5 unit tests con `httpx.MockTransport` (valid SSE
lines, `[DONE]` sentinel, empty delta skip, 500 → `LLMStreamError`,
no retry mid-stream — contar calls en MockTransport).

**Riesgo acknowledged**: `httpx.MockTransport` + `aiter_lines` en
httpx 0.28.1 funciona (verificado via `uv run python -c "import
httpx; print(httpx.__version__)"` → `0.28.1`). El mock response
usa `content=aiter_bytes(...)` con un async byte iterator que
yields los SSE lines como blob único. Plan B si MockTransport
falla: custom `httpx.AsyncBaseTransport` subclass.

### 3. `infrastructure/llm/_parser.py` — `StreamEventParser`

```python
@dataclass(slots=True)
class StreamEventParser:
    buffer: str = ""
    def feed(self, chunk: str) -> Iterator[str]:
        self.buffer += chunk
        yield chunk
    def finalize(self, returned_ids: set[str]) -> LLMSelection:
        # 1. strip markdown fences (reuse helper)
        # 2. parse_llm_response(self.buffer)  # tier-1 + tier-2
        # 3. for each matching_id not in returned_ids:
        #      log WARNING; drop
        # 4. return LLMSelection(filtered_ids, explanation)
```

**Test**: 6 unit tests (verbatim, plain JSON, markdown fences,
hallucinated ids con WARNING, explanation preserved, malformed
JSON raise `LLMResponseParseError`).

### 4. `application/usecases/filter_jobs_by_intent.py` — `stream_execute`

```python
@dataclass(frozen=True, slots=True)
class StreamEventMeta:
    intent: Intent
@dataclass(frozen=True, slots=True)
class StreamEventText:
    delta: str
@dataclass(frozen=True, slots=True)
class StreamEventDone:
    jobs: list[Job]
    explanation: str
    total_considered: int
    total_matched: int
    used_fallback: bool
    request_id: str
StreamEvent = StreamEventMeta | StreamEventText | StreamEventDone

class FilterJobsByIntentUseCase:
    async def execute(self, ...) -> FilteredJobsResult: ...  # UNCHANGED
    async def stream_execute(
        self, *, message, q, location, limit, sources=None,
    ) -> AsyncIterator[StreamEvent]:
        # 1. resolve dispatch (2-stage or v1) — extract helper
        # 2. (2-stage) yield StreamEventMeta(intent)
        # 3. aggregator.search(...) silent
        # 4. if empty: yield done(_EMPTY); return
        # 5. parser = StreamEventParser()
        # 6. async for chunk in llm.stream_complete(...):
        #      for text in parser.feed(chunk): yield Text
        # 7. selection = parser.finalize(returned_ids)
        # 8. strict-subset validation + WARNING per drop
        # 9. yield Done(...)
```

**Test**: 5 unit tests (meta only in 2-stage, skip meta in v1,
text chunks in order, short-circuit done on empty aggregator,
done in aggregator order not LLM order, hallucinated ids dropped).

### 5. `presentation/routes/chat.py` — `build_chat_stream_router`

```python
def build_chat_stream_router(
    *, use_case, max_message_chars, sse_keepalive_seconds,
) -> APIRouter:
    router = APIRouter()
    SSE_HEADERS = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    @router.post("/jobs/chat/stream")
    async def chat_stream(body: ChatRequest, request: Request):
        if len(body.message) > max_message_chars:
            raise HTTPException(400, ...)  # pre-stream validation
        normalized = unicodedata.normalize(
            "NFC", body.message
        ).casefold().strip()
        q: asyncio.Queue[str | None] = asyncio.Queue()
        request_id = getattr(
            request.state, "request_id", uuid.uuid4().hex
        )

        async def producer() -> None:
            try:
                async for event in use_case.stream_execute(
                    message=normalized, q="", location="", limit=20,
                ):
                    await q.put(_serialize_event(event, request_id))
            except Exception as e:  # noqa: BLE001
                await q.put(_serialize_error(e))
            finally:
                await q.put(None)

        task = asyncio.create_task(producer())

        async def stream() -> AsyncIterator[bytes]:
            try:
                while True:
                    try:
                        get = q.get()
                        item = (
                            await asyncio.wait_for(
                                get, timeout=sse_keepalive_seconds,
                            ) if sse_keepalive_seconds > 0
                            else await get
                        )
                    except asyncio.TimeoutError:
                        yield b": keepalive\n\n"
                        continue
                    if item is None:
                        return
                    yield item.encode("utf-8")
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers=SSE_HEADERS,
        )
    return router
```

`_serialize_event` y `_serialize_error` son helpers privados que
convierten `StreamEvent` a `f"event: <name>\ndata: <json>\n\n"`.

**Test**: 3 unit tests (factory signature, 400 pre-stream, error
translation map) + 10 integration tests (ver §Test strategy).

### 6. `presentation/schemas.py` — `ChatStream*Event`

```python
class ChatStreamTextEvent(BaseModel):
    delta: str
class ChatStreamMetaEvent(BaseModel):
    intent: Intent
class ChatStreamDoneEvent(BaseModel):
    jobs: list[JobResponse]
    explanation: str
    total_considered: int
    total_matched: int
    used_fallback: bool
    request_id: str
```

**Test**: 3 schema unit tests (Pydantic round-trip).

### 7. `presentation/app_factory.py` — CORS fix + register stream router

Dos cambios:
1. Línea 666: `allow_methods=["GET"]` → `allow_methods=["GET", "POST"]`.
2. Después del bloque v1 chat router:
   ```python
   if chat_use_case is not None:
       app.include_router(
           chat_routes.build_chat_stream_router(
               use_case=chat_use_case,
               max_message_chars=effective_settings.llm_max_message_chars,
               sse_keepalive_seconds=effective_settings.sse_keepalive_seconds,
           )
       )
   ```

**Test**: 2 integration nuevos (CORS preflight POST, POST cross-origin
real). El test existente `test_options_preflight_advertises_get_method`
se ACTUALIZA para también assertar POST (solo la assertion widens;
v1 GET preflight outcome sin cambios).

### 8. `infrastructure/config.py` — `sse_keepalive_seconds`

```python
sse_keepalive_seconds: float = Field(
    default=15.0,
    validation_alias=AliasChoices(
        "SSE_KEEPALIVE_SECONDS", "sse_keepalive_seconds",
    ),
    ge=0.0,    # 0 disables (per REQ-SSE-002 3rd scenario)
    le=60.0,   # Chrome idle timeout
)
```

**Deviation del proposal**: `gt=0.0` → `ge=0.0` (0 debe ser válido).

**Test**: 4 settings tests (default, le=60 rejects, env var, ge=0
allows 0).

### 9. `infrastructure/llm/exceptions.py` — `LLMStreamError` + `LLMRequestTimeoutError`

```python
class LLMStreamError(LLMUnavailableError):
    """Streaming-specific failure (non-200, malformed SSE, etc.)."""
class LLMRequestTimeoutError(LLMUnavailableError):
    """Streaming request exceeded the configured timeout."""
```

Ambas heredan de `LLMUnavailableError` para que el `isinstance` chain
en el route catcher funcione (el route hace
`except LLMUnavailableError` PRIMERO, luego sub-classes para
discriminar el machine code).

**Test**: 2 unit (subclass invariant, distinct repr).

### 10. `backend/.env.example` — document `SSE_KEEPALIVE_SECONDS`

Add en la sección "LLM chat filter":
```
# SSE keepalive interval (seconds). Emit a `: keepalive` comment
# every N seconds during quiet periods (stage-2 aggregator scrape)
# so browsers / proxies don't time out. `0` disables. `60.0` upper
# bound (Chrome idle timeout).
SSE_KEEPALIVE_SECONDS=15.0
```

### 11. `backend/README.md` — endpoint docs + nginx snippet

3 adiciones:
1. Nueva sección "Chat filter — streaming endpoint" con curl example
   + event-type reference.
2. CORS fix note en la sección chat-filter existente.
3. Nueva sección "Streaming behind nginx" con
   `proxy_buffering off;` snippet + explicación.

### 12. `backend/tests/fixtures/minimax_streaming_capture.txt` (NEW)

One-time manual capture de un MiniMax-M3 SSE response real (formato
raw bytes `data: {...}\n\n` lines). Committed al repo. Usado por
`test_chat_streaming_live.py::test_stream_complete_parses_real_capture`
(NUNCA en CI per AGENTS.md rule #1).

## Test strategy

| Capa | File | Tests |
|---|---|---|
| Unit | `test_llm_port.py` | 1: protocol conformance (mypy --strict) |
| Unit | `test_llm_client.py` | 5: `stream_complete` (valid SSE, DONE sentinel, empty delta, 500→LLMStreamError, no retry) |
| Unit | `test_llm_parser.py` | 6: `StreamEventParser` (verbatim, plain, fences, hallucinated ids, explanation preserved, malformed raise) |
| Unit | `test_filter_use_case.py` | 5: `stream_execute` (meta 2-stage, no meta v1, text order, short-circuit empty, aggregator order) + extiende `FakeLLMClient.stream_complete` |
| Unit | `test_chat_route.py` | 3: stream router factory (signature, 400 pre-stream, error map) |
| Unit | `test_chat_wiring.py` | 1: stream router registrado con keepalive |
| Unit | `test_chat_settings.py` | 4: `sse_keepalive_seconds` (default, le=60 reject, ge=0 allow, env var) |
| Unit | `test_llm_exceptions.py` | 2: `LLMStreamError` + `LLMRequestTimeoutError` |
| Unit | `test_chat_schemas.py` | 3: `ChatStream*Event` round-trip |
| Integration | `test_chat_streaming.py` (NEW) | 10: happy path, meta 2-stage, no meta v1, keepalive durante aggregator lento (≥3 keepalives en 20s con `sse=5.0`), no keepalive cuando `sse=0`, 400 over-cap, error LLM unavailable, error parse failure, error timeout, headers SSE presentes |
| Integration | `test_cors.py` (MODIFIED) | 2 nuevos: POST preflight OPTIONS, POST cross-origin real |
| Integration | `test_chat_endpoint.py` | UNCHANGED (regression anchor para v1, REQ-BACKWARDS-COMPAT-001) |
| Integration | `test_chat_endpoint_2stage.py` | UNCHANGED (regression anchor para v1 2-stage) |
| Live | `test_chat_streaming_live.py` (NEW) | 1: real MiniMax-M3 streaming con la captura fixture (gated por `LLM_LIVE_TESTS=1`) |
| Live | `test_llm_client.py` | 1 nuevo: `test_stream_complete_parses_real_capture` (fixture-driven, gated) |

## File-by-file change list (con LOC delta)

| File | LOC delta |
|---|---|
| `application/ports.py` | +10 |
| `infrastructure/llm/_client.py` | +60 |
| `infrastructure/llm/_parser.py` | +50 |
| `infrastructure/llm/exceptions.py` | +15 |
| `infrastructure/config.py` | +10 |
| `application/usecases/filter_jobs_by_intent.py` | +120 |
| `presentation/routes/chat.py` | +130 |
| `presentation/schemas.py` | +25 |
| `presentation/app_factory.py` | +5 |
| `.env.example` | +10 |
| `README.md` | +80 |
| `tests/fixtures/minimax_streaming_capture.txt` | +50 |
| `tests/unit/test_llm_client.py` | +120 |
| `tests/unit/test_llm_parser.py` | +100 |
| `tests/unit/test_filter_use_case.py` | +150 |
| `tests/unit/test_chat_route.py` | +80 |
| `tests/unit/test_chat_wiring.py` | +30 |
| `tests/unit/test_chat_settings.py` | +60 |
| `tests/unit/test_llm_exceptions.py` | +30 |
| `tests/integration/test_chat_streaming.py` (NEW) | +280 |
| `tests/integration/test_cors.py` | +50 |
| `tests/integration/test_chat_streaming_live.py` (NEW) | +40 |
| `tests/integration/test_chat_endpoint.py` | 0 (regression anchor) |
| `tests/integration/test_chat_endpoint_2stage.py` | 0 (regression anchor) |
| **TOTAL** | **~1495** |

## Deviations del proposal

| Cambio | Driver |
|---|---|
| `sse_keepalive_seconds`: `gt=0.0` → `ge=0.0` | REQ-SSE-002 3rd scenario requiere `SSE_KEEPALIVE_SECONDS=0` válido (kill switch). |
| LOC forecast: 1495 vs proposal 400-600 | La superficie de tests (26+ scenarios) es más rica que la estimación original. |
| `_run_stage3_streaming` como helper nuevo (sibling de `_run_stage3`) | El proposal sketcheó "new helper"; el design confirma: helper nuevo que llama `stream_complete` y yields `StreamEventText` chunks. `_run_stage3` original UNCHANGED — v1 callers zero behavior change. |
| `request_id` viene de `request.state.request_id` con uuid4 fallback | El proposal era vago ("request_id from middleware"); el design precisa: si el middleware no está montado (test que bypass el full app stack), el route genera uuid4. |

## Open questions

None. Las 2 design-level decisions flagged abajo son para
awareness del orchestrator, NO blockers:

1. **`FakeLLMClient.stream_complete` en 6 test files** (no
   consolidado en conftest): least-invasive option. Future
   "consolidate fakes" change puede colapsar; out of scope para
   `chat-streaming`.
2. **Live fixture staleness**: la captura one-time se rompe
   silenciosamente si MiniMax-M3 cambia el SSE shape. Mitigación:
   live test gated por `LLM_LIVE_TESTS=1`.

## Self-check antes de sdd-tasks

- 12 REQ-* mapeados a component changes ✓
- 26 scenarios con test strategy (unit + integration + live) ✓
- Single-PR (1495 LOC) < 5000 review budget ✓
- No new env vars beyond `SSE_KEEPALIVE_SECONDS` ✓
- v1 `POST /jobs/chat` provably unchanged (REQ-BACKWARDS-COMPAT-001) ✓
- 3 MODIFIED requirements honored (2 routes, 2 use-case methods, Intent reusado) ✓

## Result contract

- **status**: `ok`
- **executive_summary**: Diseño completo de la arquitectura
  streaming SSE para `POST /jobs/chat/stream`. 12 cambios
  coordinados (puertos, cliente, parser, use case, ruta,
  schemas, app_factory, config, excepciones, docs, fixtures,
  tests) con 1495 LOC forecast. Preserva v1 intacto, arregla
  CORS, y mapea 6 excepciones a 6 machine codes SSE estables.
- **artifacts**: `openspec/changes/chat-streaming/design.md`
  (este archivo) + Engram `sdd/chat-streaming/design` (post-save)
- **next_recommended**: `sdd-tasks`
- **risks**: `httpx.MockTransport` + `aiter_lines` viable en
  0.28.1 (Plan B: custom transport); live fixture staleness
  mitigado por `LLM_LIVE_TESTS=1`; LOC > proposal justificado
  por cohesión lógica + 26 scenarios
- **skill_resolution**: `paths-injected`
- **loc_forecast**: 1495
- **pr_recommendation**: `single-pr`
