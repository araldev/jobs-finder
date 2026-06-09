# Proposal: chat-streaming

**Change**: `chat-streaming` • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
**Date**: 2026-06-09

## Intent

El cambio `frontend-scaffold` (próximo en este repo) introduce la primera UI web
para `jobs-finder`. La UI necesita renderizar la respuesta del LLM con efecto
"typewriter" (live text chunks). El endpoint actual `POST /jobs/chat` devuelve
el JSON completo en ~5-8s — acceptable para el uso backend-only, pero crea
una UX de "pantalla en blanco" en la web. La solución más simple y robusta
es exponer un nuevo endpoint `POST /jobs/chat/stream` que streama la respuesta
del LLM chunk por chunk vía **Server-Sent Events (SSE)** sobre HTTP/1.1 nativo
de FastAPI. La ruta v1 (`POST /jobs/chat`) se PRESERVA sin cambios — no
breaking change para clientes existentes. Adicionalmente, este cambio ARREGLA
un bug CORS pre-existente descubierto durante el explore: `allow_methods=["GET"]`
bloquea POST cross-origin (el frontend en `localhost:3000` no podría llamar
ningún POST del backend).

## Scope

### In Scope

- **Nuevo endpoint** `POST /jobs/chat/stream` (SSE, `media_type="text/event-stream"`).
  Acepta el mismo body que `POST /jobs/chat` (`ChatRequest{message}`) y emite
  SSE events con la respuesta streameada.
- **Wire format SSE** (3 tipos de evento + keepalive):
  - `event: meta` (opcional, omitido en v1 path): `{"intent": {...}}` con el
    `Intent` parseado de stage-1, emitido ANTES de empezar stage-3.
  - `event: text` (repetido N veces): `{"delta": "<chunk>"}` con cada
    `delta.content` que el LLM emite. Live typewriter.
  - `event: done` (uno, al final): `{"jobs": [...], "explanation": "...",
    "total_considered": N, "total_matched": M, "used_fallback": bool,
    "request_id": "..."}` con el mismo body shape que el v1 `ChatResponse`.
  - Comentarios `: keepalive\n\n` cada `SSE_KEEPALIVE_SECONDS` (default 15.0)
    durante aggregator stage-2 wait para evitar proxy/browser timeouts.
- **Stream `LLMClientPort`**: añadir `stream_complete(*, system, user) ->
  AsyncIterator[str]` al Protocol alongside `complete(...)`. Concrete
  implementation en `MiniMaxLLMClient` usa `httpx.AsyncClient.stream("POST",
  ...)` + `aiter_lines` + parsea cada `data: <json>` line del SSE. NO retry
  mid-stream (un retry destruiría los chunks ya enviados al cliente).
- **Streaming parser**: `StreamEventParser` (nuevo dataclass) acumula chunks
  en `self.buffer` y los yields verbatim como `text` events. Al final, llama
  al parser existente `parse_llm_response(self.buffer)` (reusa tier-1+tier-2
  sin cambios). Estrategia A (acumular + parse-at-end) — strategy B
  (incremental JSON) es over-engineering.
- **Stage-1 silencioso, stage-3 streamea**: stage-1 emite solo un `meta` event
  con el `Intent` parseado (no streameamos el raw text del LLM de stage-1 —
  es internal). Stage-3 streama el raw `delta.content` (el cual ES el JSON
  output que contiene `matching_ids` y `explanation`). La UI frontend
  decide cómo renderizar el raw text de stage-3 (typewriter character-by-
  character, o esperar al `done` event para el JSON estructurado).
- **CORS fix**: `app_factory.py:666` cambia de `allow_methods=["GET"]` a
  `allow_methods=["GET", "POST"]` (explícito, defensa-en-profundidad). Cubre
  TODOS los POST del API (chat v1, chat stream, futuro). NO CORS preflight
  test existe en el repo; añadimos uno en este cambio.
- **Keepalive**: `Settings.sse_keepalive_seconds: float = Field(default=15.0,
  validation_alias=AliasChoices("SSE_KEEPALIVE_SECONDS", "sse_keepalive_seconds"))`.
  El route generator envía un comentario SSE (`: keepalive\n\n`) cada N segundos
  durante el stage-2 wait. Default 15.0 (Chrome idle timeout = 60s; 15s
  deja margen para 3 keepalives antes del timeout).
- **Tests** (TDD-strict):
  - Unit: `stream_complete` con `httpx.MockTransport`, `StreamEventParser`
    con accumulator scenarios, `stream_execute` con FakeLLMClient, route
    SSE parsing.
  - Integration: end-to-end con FakeLLMClient que implementa `stream_complete`,
    CORS preflight test, keepalive emission test, regression anchor para
    `POST /jobs/chat` (no-streaming) intacto.
  - Live (gated `LLM_LIVE_TESTS=1`, never in CI): 1-2 tests contra MiniMax-M3
    real. Sigue el pattern de `test_chat_live.py`.
  - Fixture one-time (AGENTS.md rule #1, never in CI): captura manual de un
    stream real de MiniMax-M3 → `backend/tests/fixtures/minimax_streaming_capture.txt`.
- **Documentación**: `backend/README.md` añade el nuevo endpoint en la sección
  "AI Chat Filter" + CORS + SSE behind nginx caveat + keepalive semantics.

### Out of Scope

- WebSocket alternative (SSE cubre el caso; no necesitamos bidirectional).
- Abortar el upstream LLM call cuando el cliente desconecta (decidido por
  user; el stream se deja correr; $0.0025/call no justifica la complejidad).
- Per-event backpressure (browsers consumen SSE a velocidad del network;
  el LLM emite ~30-50 tokens/s — el cliente puede跟不上 sin problema).
- Persistir el stream en Redis / message queue (out of scope; el stream es
  ephemeral per-request).
- Multi-turn conversation history (el chat es single-shot; multi-turn es
  un follow-up change).
- Tool use / function calling (no aplica a MiniMax-M3 en nuestro caso).
- Prompt caching (no soportado por MiniMax-M3 con `thinking: disabled`).
- Token usage tracking mid-stream (out of scope; logging del `request_id`
  final es suficiente para ops).
- Frontend changes (cubierto por `frontend-scaffold` change).
- Reemplazar el v1 `POST /jobs/chat` (se preserva como fallback no-streaming;
  el v1 sigue siendo el default).

## Capabilities

### New Capabilities

- `chat-streaming`: cubre los REQs de streaming SSE (capability nueva; el
  test surface en `tests/integration/test_chat_streaming.py`).

### Modified Capabilities

- `ai-chat-filter` (extendido): REQ-CHAT-001 (chat request/response) ahora
  tiene una variante streaming. REQ-CHAT-002 (per-user rate limit) aplica
  también a la ruta stream (mismo middleware).
- `chat-filter-2stage` (extendido): la pipeline 2-stage ahora streama
  stage-3; el use case expone un nuevo método `stream_execute(...)` que
  yields `StreamEvent` (no reemplaza el `execute(...)` actual).

## Approach

**Capas**:

1. **Port layer** (`application/ports.py`): extender `LLMClientPort` con
   `stream_complete(*, system, user) -> AsyncIterator[str]`. Mantener
   `complete(...)` intacto (el v1 path lo sigue usando).
2. **Infrastructure** (`infrastructure/llm/_client.py`): implementar
   `stream_complete` con httpx streaming. Política:
   - `client.stream("POST", url, json=body_with_stream_true, headers=...)`.
   - `async with stream: response = await stream.__aenter__()`.
   - Si status != 200: raise `LLMStreamError` (no retry).
   - `async for line in response.aiter_lines():` parsea cada `data: <json>`
     line → extrae `choices[0].delta.content` → yield.
   - Al final: `await stream.__aexit__(...)`. Si la última line tiene
     `usage`, log (out of scope to surface to client).
3. **Parser** (`infrastructure/llm/_parser.py`): añadir `StreamEventParser`
   (dataclass con `buffer: str` + `feed(chunk) -> Iterator[str]` +
   `finalize() -> LLMSelection`).
4. **Use case** (`application/usecases/filter_jobs_by_intent.py`): añadir
   `async def stream_execute(*, message, q, location, limit, sources) ->
   AsyncIterator[StreamEvent]`. Refactor: extraer `_run_stage3_streaming(...)`
   que internamente llama `llm.stream_complete(...)` y yields `StreamEvent`
   chunks. El dispatcher (`_execute_2stage` vs `_execute_v1`) se reusa;
   solo cambia el return type. Antes del stage-3, yield `StreamEventMeta` con
   el `Intent` parseado (en 2-stage path) o skip (en v1 path).
5. **Schemas** (`presentation/schemas.py`): añadir
   `ChatStreamTextEvent{delta: str}`,
   `ChatStreamMetaEvent{intent: Intent | None}`,
   `ChatStreamDoneEvent{jobs, explanation, total_considered, total_matched,
   used_fallback, request_id}`.
6. **Route** (`presentation/routes/chat.py`): añadir
   `build_chat_stream_router(*, use_case, max_message_chars, sse_keepalive_seconds) -> APIRouter`.
   El handler:
   - Valida cap (mismo 400 que v1).
   - Normaliza message (mismo NFC+casefold+strip).
   - Construye un `asyncio.Queue[str | None]` interno.
   - Crea una task que itera `use_case.stream_execute(...)` y pushea
     cada `StreamEvent` a la queue (serializado como SSE `event: ...\ndata: ...\n\n`).
   - El `StreamingResponse(media_type="text/event-stream")` consume la
     queue y yielda bytes. Si la queue está vacía por `sse_keepalive_seconds`,
     yielda `: keepalive\n\n` y sigue.
   - Si el client cierra la conexión, la task sigue (no abortamos el LLM).
   - Excepciones: `LLMUnavailableError` → SSE `event: error` con detail,
     luego cierra. `LLMResponseParseError` → SSE `event: error` con
     detail, luego cierra. `JobSearchError` global → SSE `event: error`.
7. **App factory** (`presentation/app_factory.py`):
   - Fix CORS: `allow_methods=["GET", "POST"]` (línea 666).
   - En el bloque `if chat_use_case is not None:`, además de registrar
     `build_chat_router`, registrar `build_chat_stream_router` con
     `sse_keepalive_seconds=effective_settings.sse_keepalive_seconds`.
8. **Settings** (`infrastructure/config.py`): añadir `sse_keepalive_seconds`
   con Pydantic bounds `gt=0.0, le=60.0`.
9. **Exceptions** (`infrastructure/llm/exceptions.py`): añadir
   `LLMStreamError(JobSearchError)` (mismo patrón que `LLMUnavailableError`).
10. **Fixture** (`tests/fixtures/minimax_streaming_capture.txt`): captura
    one-time manual (AGENTS.md rule #1; never in CI). Reusado por
    `test_llm_client.py::test_stream_complete_parses_real_capture`.

## Affected Areas

| Area | Impact | Descripción |
|---|---|---|
| `application/ports.py` | Modified | `LLMClientPort` añade `stream_complete` (Protocol). |
| `infrastructure/llm/_client.py` | Modified | `MiniMaxLLMClient.stream_complete` (httpx streaming). |
| `infrastructure/llm/_parser.py` | Modified | `StreamEventParser` (acumula + parse-at-end). |
| `infrastructure/llm/exceptions.py` | Modified | `LLMStreamError` (new). |
| `infrastructure/config.py` | Modified | `sse_keepalive_seconds` field. |
| `application/usecases/filter_jobs_by_intent.py` | Modified | `stream_execute(...)` AsyncIterator. |
| `presentation/routes/chat.py` | Modified | `build_chat_stream_router` factory. |
| `presentation/schemas.py` | Modified | `ChatStreamTextEvent/MetaEvent/DoneEvent`. |
| `presentation/app_factory.py` | Modified | Registra stream router + CORS fix. |
| `.env.example` | Modified | Doc de `SSE_KEEPALIVE_SECONDS`. |
| `README.md` | Modified | Sección streaming + CORS caveat. |
| `tests/fixtures/minimax_streaming_capture.txt` | NEW | Captura one-time. |
| `tests/unit/test_llm_client.py` | Modified | Tests `stream_complete`. |
| `tests/unit/test_llm_parser.py` | Modified | Tests `StreamEventParser`. |
| `tests/unit/test_filter_use_case.py` | Modified | Tests `stream_execute`. |
| `tests/unit/test_chat_route.py` | Modified | Tests SSE route. |
| `tests/unit/test_chat_wiring.py` | Modified | Test stream router registration. |
| `tests/integration/test_chat_streaming.py` | NEW | E2E tests. |
| `tests/integration/test_chat_endpoint_2stage.py` | Modified | Regression anchor (v1 intact). |
| `tests/integration/test_cors.py` | Modified | CORS preflight test (POST). |
| `tests/integration/test_chat_streaming_live.py` | NEW | 1-2 LIVE tests (gated). |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| CORS preflight broken pre-existente | High (ya broken) | Fix en este cambio (`allow_methods` → `["GET", "POST"]`). Test añadido. |
| MiniMax-M3 streaming format diff de M2.7 | Low | Captura one-time (T-002). La doc OpenAI spec garantiza mismo shape. |
| httpx MockTransport + SSE bytes | Low | httpx 0.27 soporta `aiter_bytes` en MockTransport responses. |
| nginx buffering de SSE | Medium (production concern) | Documentar en README: `proxy_buffering off` para `/jobs/chat/stream`. |
| Generator exceptions mid-stream | Medium | Catch en route → SSE `event: error` + close. Documentar en el wire format. |
| Retry mid-stream destruiría UX | High (decidido) | NO retry en `stream_complete`. Documentar diferencia con `complete`. |
| Abort client disconnect | High (no implementado) | Decidido por user: no abortar. Documentar como limitation. |
| `httpx.AsyncClient` pooling con streaming | Low | Reusar el `llm_http_client` del lifespan (mismo client que `complete`). |
| 2 LLM calls × 2 stages = 4 cost | Low | Mismo cost que v1 ($0.005/req 2-stage). Streaming no cambia cost. |
| Live test fragility (network) | Low | Gated por `LLM_LIVE_TESTS=1`. Default skip. 1-2 tests only. |
| Token usage tracking | Low | Out of scope; logging del `request_id` final es suficiente. |

## Rollback Plan

- Revertir el commit único (single PR) con `git revert <hash>`.
- Alternativa quirúrgica: el flag `LLM_FILTER_ENABLED=false` desactiva TODO el
  chat (incluyendo el stream router). La ruta v1 sigue funcionando.
- `SSE_KEEPALIVE_SECONDS=0` desactiva el keepalive (el generator no envía
  comentarios, solo events; los proxies que bufferizan pueden timeoutear
  durante stage-2 wait — degradación visible).
- El CORS fix `allow_methods=["GET", "POST"]` es estrictamente aditivo
  (cubre métodos que el API ya soporta); no se rompe ningún cliente
  existente que funcione con GET.

## Dependencies

- **Frontend `frontend-scaffold`** (cambio paralelo): la UI debe usar
  `EventSource` API (o `fetch` con ReadableStream parser para POST).
  Spec de wire format está en este proposal — el frontend agent puede
  empezar a implementar el consumer en paralelo (la UI es headless
  de la implementación backend).
- **MiniMax-M3 streaming support**: confirmado en docs (ver explore
  §"Verificación de soporte de streaming en MiniMax"). Verificación
  final = captura one-time (T-002).

## Success Criteria

- [ ] `POST /jobs/chat/stream` emite SSE events correctos end-to-end
      con un `FakeLLMClient.stream_complete` que devuelve chunks.
- [ ] Stage-3 raw text streama como `event: text` chunks en orden.
- [ ] `event: done` lleva el mismo body shape que el v1 `ChatResponse`.
- [ ] Keepalive comments emitidos cada `SSE_KEEPALIVE_SECONDS` durante
      aggregator stage-2 wait (verificable con un fake aggregator que
      tarda 20s).
- [ ] CORS preflight `OPTIONS /jobs/chat/stream` con
      `Origin: http://localhost:3000` → 200 con
      `Access-Control-Allow-Methods: GET, POST`.
- [ ] `POST /jobs/chat` (v1) intacto: 1036 tests baseline + 0 regresiones.
- [ ] `MiniMaxLLMClient.stream_complete` soporta la captura real de
      MiniMax-M3 (1 LIVE test gated por `LLM_LIVE_TESTS=1`).
- [ ] 4 quality gates GREEN: `pytest`, `mypy --strict`, `ruff check`,
      `ruff format --check`.
- [ ] `backend/README.md` documenta el nuevo endpoint + CORS fix +
      nginx caveat + keepalive semantics.

## LOC Forecast

**Estimate**: 400-600 LOC (production + tests + docs).

- Production code: ~200 LOC (`stream_complete` 80, `StreamEventParser` 30,
  `stream_execute` 60, route 50, schemas 30, exceptions 10, settings 10,
  app_factory 10, .env.example 10).
- Test code: ~250 LOC (unit + integration, MockTransport scenarios,
  SSE parsing, keepalive, CORS, LIVE).
- Docs: ~50 LOC (README streaming section + CORS caveat).

**Review budget**: 5000 líneas (orchestrator's `ask-always` strategy).
**400-line per-PR guard**: this change is well under 800 lines — **single PR**.

**Decision needed before apply: No**
**Chained PRs recommended: No**
**400-line budget risk: Low**

## Strict TDD Reminder

Strict TDD mode is ACTIVE for this change. The `sdd-apply` phase will:

1. Read `_shared/strict-tdd.md` and follow it verbatim.
2. Use `cd backend && uv run pytest` as the test runner.
3. For EACH task: RED (failing test first) → GREEN (minimum code) →
   TRIANGULATE (≥2 cases per behavior) → REFACTOR.
4. Live tests gated by `LLM_LIVE_TESTS=1` (NEVER in CI).
5. `httpx.MockTransport` for LLM client streaming tests.
6. Avoid `expect(result).toEqual([])` without a companion non-empty test.
7. Pure function preference: `StreamEventParser.feed()` + `.finalize()`
   are pure-ish (state isolated to one instance); test in isolation.

The `sdd-verify` phase will check the TDD Cycle Evidence table + assertion
quality (Step 5f) + cross-reference test files exist + actually pass.

## Suggested Tasks (high-level; `sdd-tasks` will plan formally)

- T-001: extend `LLMClientPort` con `stream_complete` Protocol method +
  implementar en `MiniMaxLLMClient` (httpx `client.stream("POST", ...)` +
  `aiter_lines` + parse SSE `data:` lines).
- T-002: captura one-time manual de un SSE stream real de MiniMax-M3 →
  commit `tests/fixtures/minimax_streaming_capture.txt` (per AGENTS.md rule #1,
  never in CI).
- T-003: añadir `StreamEventParser` a `infrastructure/llm/_parser.py`
  (accumulate + parse-at-end, reusa `parse_llm_response` para el final).
- T-004: refactor `FilterJobsByIntentUseCase` con `stream_execute(...)` que
  yields `StreamEvent` (meta + text + done). El dispatcher 2-stage / v1
  se reusa; el `_run_stage3_streaming` es nuevo.
- T-005: añadir `ChatStreamTextEvent`, `ChatStreamMetaEvent`,
  `ChatStreamDoneEvent` schemas en `presentation/schemas.py`.
- T-006: añadir `LLMStreamError` a `infrastructure/llm/exceptions.py`.
- T-007: añadir `sse_keepalive_seconds: float = Field(default=15.0, ...)`
  a `Settings`. Documentar en `.env.example`.
- T-008: implementar `build_chat_stream_router` en
  `presentation/routes/chat.py` con `StreamingResponse(media_type="text/event-stream")`
  + keepalive generator + `event: error` para excepciones.
- T-009: registrar el stream router en `app_factory.build_app()` y
  arreglar CORS (`allow_methods=["GET", "POST"]`).
- T-010: tests (TDD-first per strict mode):
  - Unit: `stream_complete` (MockTransport), `StreamEventParser`
    (accumulate + finalize), `stream_execute` (event sequence),
    SSE route (event order + keepalive).
  - Integration: end-to-end con FakeLLMClient.stream_complete,
    CORS preflight (POST), v1 regression anchor.
  - LIVE (gated): 1 test contra MiniMax-M3 con la captura fixture.
- T-011: actualizar `backend/README.md` con la sección streaming
  + CORS fix + nginx `proxy_buffering` caveat + keepalive semantics.
- T-012: full suite GREEN + ruff + mypy clean.

## Enfoques descartados

- **Strategy B (incremental JSON parsing)**: descartada por over-engineering.
  Beneficio marginal (explanation streamed) vs. costo (doble-buffering,
  many `json.JSONDecodeError` por chunk). Ver explore §"Enfoques considerados".
- **WebSocket alternative**: descartada por complejidad (WS upgrade, ping/pong,
  reconexión manual). SSE cubre el caso unidireccional server→client que
  necesitamos. Standard para chat UIs.
- **Chunked-transfer-encoding raw (no SSE)**: descartada por ergonomía del
  cliente. SSE da `event:` typed messages + auto-reconnect + comment-based
  keepalive built-in. Cero benefit de ir raw.
- **LLM call abort on client disconnect**: descartada por decisión del user
  (costo $0.0025 no justifica la complejidad de `asyncio.CancelledError`
  propagation + httpx stream cancellation).
- **Multi-stage stream (stage-1 + stage-3 ambos streameando raw text)**:
  descartada por diseño (stage-1 es internal; UI no necesita ver el JSON
  raw del intent). Solo emitimos el `Intent` parseado como `meta` event.
