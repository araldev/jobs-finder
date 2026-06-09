# Explore: chat-streaming

**Change**: `chat-streaming` • **Mode**: `both` (OpenSpec files + Engram) • **Strict TDD**: ACTIVE
**Date**: 2026-06-09 • **Base**: branch del orquestador (post `fix-linkedin-geoid`)

## Estado actual (relevant to this change)

El backend implementa el chat filter de 2-etapas (`chat-filter-2stage` + `fix-linkedin-geoid`,
1036 tests passing). El endpoint canónico es `POST /jobs/chat` con `ChatResponse` no-streamed.
La arquitectura es:

- **Route** (`presentation/routes/chat.py`): capa fina sobre el use case. Lee `ChatRequest`,
  valida cap, normaliza NFC+casefold+strip, llama `use_case.execute(...)`, mapea excepciones
  (LLM down → 502, parse error → 422). Factory `build_chat_router(use_case=..., max_message_chars=...)`.
- **Use case** (`application/usecases/filter_jobs_by_intent.py`): orquesta stage-1 (intent
  extraction) → stage-2 (aggregator dirigido) → stage-3 (LLM filter). Short-circuit a v1 cuando
  `confidence < threshold`, parse error, o `INTENT_EXTRACTION_ENABLED=false`. Despacha entre
  `_execute_2stage(...)` y `_execute_v1(...)`. V1 path pasa `q=""`/`location=""`/`limit=20` al
  aggregator (compat key con cache).
- **LLM client** (`infrastructure/llm/_client.py`): `MiniMaxLLMClient.complete(*, system, user)
  -> str`. POST a `{base_url}/v1/chat/completions` con `stream: false`. Política de retry
  selectivo: 5xx/429/codes 1002/1013 → 1 retry; 401/403/codes 1004/1008/1001/timeout/other HTTP
  → no retry. Extrae `choices[0].message.content` en una sola llamada.
- **LLM port** (`application/ports.py`): `LLMClientPort(Protocol)` con un solo método
  `complete(*, system, user) -> str`. Sin método de streaming. Test double `FakeLLMClient`
  (local a `test_chat_endpoint_2stage.py`) implementa solo `complete`.
- **Parser** (`infrastructure/llm/_parser.py`): `parse_llm_response(raw: str) -> LLMSelection`.
  Tier 1 (`json.loads(stripped)`) + tier 2 (regex `\{.*\}` greedy con `re.DOTALL`). Raise
  `LLMResponseParseError` si ambos fallan. NO incremental — necesita el texto completo.
- **Schemas** (`presentation/schemas.py`): `ChatRequest{message}` + `ChatResponse{jobs, explanation,
  total_considered, total_matched, used_fallback}`. Sin variante streaming.
- **Settings** (`infrastructure/config.py`): 9 campos LLM + 6 campos intent-extraction con
  `AliasChoices` (model-level prefix `LINKEDIN_` no aplica). Ningún campo para SSE.
- **App factory** (`presentation/app_factory.py`): monta el chat router dentro del bloque
  `if chat_use_case is not None: app.include_router(chat_routes.build_chat_router(...))`.
  CORS middleware con `allow_methods=["GET"]` (línea 666) — **ESTO ES UN PROBLEMA para POST
  cross-origin**. El route `/jobs/chat` actual hace POST y sin embargo el CORS está configurado
  solo para GET: el frontend (cambio `frontend-scaffold`) en otro origen NO podría llamar
  `/jobs/chat` vía POST. Esto es un bug pre-existente que NO se ha reportado aún — REVELADO
  por la lectura de `app_factory.py` para este explore. Hay que arreglarlo en este cambio.
- **Chat rate limit** (`presentation/middleware.py::ChatRateLimitMiddleware`): per-client-IP
  bucket, default 20 rpm. Reutilizar para la nueva ruta streaming.

## Verificación de soporte de streaming en MiniMax (BLOQUEADOR PREGUNTADO)

Web research via Context7 (`platform.minimax.io/api-reference/text-chat-openai`):

- **Confirmado**: MiniMax soporta `stream: true` en `POST /v1/chat/completions`.
- **Wire format**: `Content-Type: text/event-stream` (SSE). Cada chunk es un
  `ChatCompletionChunk` OpenAI-compatible con `choices[0].delta.content` (string incremental).
- **Modelo soportado**: la doc muestra `MiniMax-M2.7` (el default de la doc). Nuestro
  `LLM_MODEL=MiniMax-M3` (default en `Settings`) — **asumimos el mismo contrato OpenAI
  ChatCompletionChunk** (la spec del `stream: true` field no depende del modelo, solo del
  endpoint). Verificable con una captura real one-time (AGENTS.md rule #1).
- **Cita**: "The `text/event-stream` endpoint returns `ChatCompletionChunk` objects, which
  represent streaming output. Each chunk contains a portion of the generated content,
  allowing for real-time responses. The `stream` parameter in the request should be set to
  `true` to enable this feature."

**Conclusión**: el riesgo técnico está mitigado por docs oficiales. La verificación final es
la captura manual one-time de un stream real para confirmar el delta shape exacto en M3
(committed as fixture, nunca en CI).

## Áreas afectadas

- `backend/src/jobs_finder/presentation/routes/chat.py` — añadir `build_chat_stream_router`
  (factory paralelo a `build_chat_router`).
- `backend/src/jobs_finder/application/ports.py` — añadir `stream_complete` al
  `LLMClientPort` Protocol.
- `backend/src/jobs_finder/application/usecases/filter_jobs_by_intent.py` — añadir
  `stream_execute(...)` que yields `StreamEvent` (variante del `execute(...)` actual).
- `backend/src/jobs_finder/infrastructure/llm/_client.py` — añadir `stream_complete` en
  `MiniMaxLLMClient` (httpx `client.stream("POST", ...)` + `iter_lines`).
- `backend/src/jobs_finder/infrastructure/llm/_parser.py` — añadir `StreamEventParser`
  (acumulador + parse-at-end, O opción B más compleja).
- `backend/src/jobs_finder/presentation/schemas.py` — añadir `ChatStreamTextEvent`,
  `ChatStreamMetaEvent`, `ChatStreamDoneEvent`.
- `backend/src/jobs_finder/presentation/app_factory.py` — registrar el nuevo router en
  el bloque `if chat_use_case is not None`. **Y arreglar CORS** (`allow_methods` debe
  incluir `POST`).
- `backend/src/jobs_finder/infrastructure/config.py` — añadir `sse_keepalive_seconds`
  (default 15.0) y posiblemente `llm_stream_enabled` (kill switch) si el costo
  incremental lo justifica.
- `backend/src/jobs_finder/infrastructure/llm/exceptions.py` — añadir `LLMStreamError`
  (subclass de `JobSearchError`) para errores de transporte durante el stream.
- `backend/src/jobs_finder/infrastructure/llm/_factory.py` — leer el nuevo `Settings` flag
  si existe.
- `backend/.env.example` — documentar `SSE_KEEPALIVE_SECONDS` y (si aplica)
  `LLM_STREAM_ENABLED`.
- `backend/tests/fixtures/minimax_streaming_capture.txt` (NEW) — captura one-time de un
  stream real (per AGENTS.md rule #1; never in CI).
- `backend/tests/unit/test_llm_client.py` — tests de `stream_complete` con MockTransport.
- `backend/tests/unit/test_llm_parser.py` — tests del parser streaming (acumulación + end parse).
- `backend/tests/unit/test_filter_use_case.py` — tests de `stream_execute(...)` (event sequence).
- `backend/tests/unit/test_chat_route.py` — tests del nuevo `/jobs/chat/stream` route.
- `backend/tests/integration/test_chat_streaming.py` (NEW) — end-to-end con FakeLLMClient
  que implementa `stream_complete`.
- `backend/tests/integration/test_chat_endpoint_2stage.py` — añadir 1 test que verifica
  que `POST /jobs/chat` (no streaming) sigue funcionando (regresión).
- `backend/tests/unit/test_chat_wiring.py` — test de que el stream router se registra
  cuando `chat_use_case` se construye.
- `backend/README.md` — documentar el nuevo endpoint + CORS fix + el keepalive.

## Enfoques considerados

### A. Acumular texto crudo + parse-at-end (RECOMENDADO)

- **Cómo**: el stream emite `event: text` con cada `delta.content` chunk. Al final del
  stream, el parser acumulador intenta `json.loads(accumulated)`; si falla, tier 2 regex.
  La respuesta final lleva el `LLMSelection` parseado.
- **Pros**: reusa el `parse_llm_response` existente casi verbatim. Mínima complejidad. La
  `explanation` (string corto) llega al final del stream como parte del payload `done` —
  la UI la renderiza después de los `text` chunks. Stage-1 emite texto crudo al cliente
  por consistencia de protocolo (la UI decide si mostrarlo o no).
- **Cons**: la `explanation` no se streama carácter por carácter (llega en bloque al final).
  Esto es aceptable porque `explanation` es ~200-400 chars y el stream live ya terminó.
- **Esfuerzo**: Low.

### B. Extracción incremental de JSON (over-engineering)

- **Cómo**: en cada chunk, intentar `json.loads(buffer)`. Si parsea, yield del payload.
  Continuar acumulando por si hay más.
- **Pros**: el `explanation` se streama como texto también.
- **Cons**: doble-buffering (el modelo emite el JSON carácter por carácter; el parser
  intenta parsear después de CADA char — muchos `json.JSONDecodeError` por chunk). Hay
  que distinguir entre JSON streaming y JSON one-shot. Complejidad alta; beneficio
  marginal.
- **Esfuerzo**: High.

**Recomendación**: A. La razón principal es que el `text` del stream YA da feedback
visual al usuario durante la generación de la `explanation` (miniMax emite el JSON
crudo, que contiene `matching_ids` y `explanation`; los caracteres de la `explanation`
son visibles como texto live). Solo el `JSON` parsing se hace al final. La UI
frontend decide si parsear el `data: text` acumulado y mostrarlo en typewriter, o
ignorar el stream de stage-3 y mostrar el `done` event.

## CORS — bloqueador descubierto

`app_factory.py:666` declara `allow_methods=["GET"]`. Esto bloquea CORS preflight de
un POST cross-origin. El endpoint existente `POST /jobs/chat` tiene el MISMO bug
(no nos dimos cuenta antes porque todos los clientes del backend son server-side o
same-origin en dev). El nuevo `POST /jobs/chat/stream` requiere POST cross-origin
desde el frontend `frontend-scaffold`.

**Opciones de fix**:
1. Cambiar a `allow_methods=["GET", "POST"]` (mínimo cambio; cubre todos los routes actuales).
2. Cambiar a `allow_methods=["*"]` (más permisivo; alineado con `allow_headers=["*"]`).
3. Set explícito `["GET", "POST"]` (defensa-en-profundidad: lista los métodos que el
   API realmente soporta).

**Recomendación**: Opción 3 (explícito `["GET", "POST"]`). Cubre `GET` (todas las rutas
de búsqueda), `POST` (chat v1 + chat stream), y rechaza el resto (PUT, DELETE, etc. que
no existen en el API). Documentar en la sección de CORS del README. Ningún test
existente cubre `OPTIONS` preflight cross-origin (`test_cors.py` solo verifica
`allow_origins`), así que necesitamos añadir al menos 1 test que verifique que
`/jobs/chat` y `/jobs/chat/stream` son accesibles vía cross-origin POST.

## Parser streaming

`StreamEventParser` (nuevo dataclass + función en `_parser.py`):

```python
class StreamEventParser:
    buffer: str = ""

    def feed(self, chunk: str) -> Iterator[str]:
        """Yield each text chunk verbatim. Append to internal buffer."""
        self.buffer += chunk
        yield chunk  # raw text forwarded to the SSE `text` event

    def finalize(self) -> LLMSelection:
        """Parse the accumulated buffer. Raise on failure."""
        return parse_llm_response(self.buffer)  # reuse existing tier-1+tier-2
```

El route instancia `StreamEventParser` antes de empezar a streamear stage-3. Cada
chunk del LLM se pasa a `parser.feed(chunk)` y se yielda como `event: text`. Cuando
el LLM cierra el stream, se llama `parser.finalize()` para obtener el `LLMSelection`;
el route arma el `ChatResponse` y lo envía como `event: done`.

**Alternativa rechazada**: pasar TODO el buffer al parser en CADA chunk (re-parsear
todo cada vez). Costo O(n²) en chars; innecesario porque el `text` event es forward
del chunk raw.

## Stage-1 vs stage-3 streaming

El use case emite eventos en este orden:

1. **Meta event** (opcional, configurable por flag): lleva el `Intent` parseado
   stage-1 (q, location, experience_years, etc.). Default ON — la UI puede mostrar
   "Buscando: Python, Madrid, 3+ años, remoto" antes de que llegue stage-3. Skip si
   `intent_extraction_enabled=False` o `INTENT_EXTRACTION_ENABLED=false` (v1 path).
2. **Keepalive comments** (`: keepalive\n\n`) durante el aggregator stage-2 wait.
3. **Text events** desde stage-3 LLM stream.
4. **Done event** con el `ChatResponse` completo (mismo body shape que `POST /jobs/chat`
   no-streaming).

**Por qué NO streameamos stage-1 raw text**: stage-1 es un internal step; el JSON que
genera es la "intent" que la UI no necesita ver carácter por carácter. Streamear el
raw text de stage-1 expondría detalles internos del pipeline (e.g. el modelo
añadiendo `<think>...</think>` blocks) que la UI tendría que filtrar. La decisión:
stage-1 es silencioso, stage-3 streama el `explanation`+`matching_ids` como JSON
crudo (el cual la UI puede renderizar como typewriter, ignorando los caracteres de
JSON syntax si lo desea).

## Wire format propuesto

```
event: meta
data: {"intent": {"q": "python", "location": "Madrid", "confidence": 0.95}}

: keepalive\n\n                                       (enviado cada SSE_KEEPALIVE_SECONDS durante el aggregator wait)

event: text
data: {"delta": "{"}

event: text
data: {"delta": "\"matching"}

event: text
data: {"delta": "_ids\": [\"a\""}

...

event: done
data: {"jobs": [...], "explanation": "...", "total_considered": 5, "total_matched": 3, "used_fallback": false, "request_id": "..."}

\n\n                                                   (stream closed)
```

Justificación:
- `event: meta` ANTES de empezar a streamear stage-3: la UI sabe qué estamos buscando.
- `event: text` chunks: live typewriter.
- `event: done` con el payload completo (mismo body que `POST /jobs/chat`): la UI
  renderiza esto al final (o lo usa para actualizar el `state` interno).
- Keepalive comment `: keepalive\n\n` durante aggregator wait: previene
  timeouts de proxies (nginx, CloudFront) y browsers (Chrome: 60s idle default).
- JSON-encoded data lines: el browser parsea con `EventSource.data` automáticamente.

## Abort / cancel

Per user decision: NO abortamos el upstream LLM call cuando el cliente desconecta.
El backend deja correr el stream hasta el final y simplemente cierra el socket.
Razón: la complejidad de abortar safely (cancelar el httpx request, manejar la
excepción en el generator) no se justifica por $0.0025/call. Documentar en el
README como limitation.

## Test surface

- **Unit**:
  - `test_llm_client.py::test_stream_complete_yields_text_chunks` — happy path
    (MockTransport que devuelve SSE-formatted bytes; assert chunks en orden).
  - `test_llm_client.py::test_stream_complete_handles_minimax_codes` — 5xx mid-stream
    debe propagar `LLMStreamError`; partial chunks no se pierden.
  - `test_llm_parser.py::test_stream_event_parser_accumulates` — feed de chunks
    uno por uno, assert que `buffer` crece y los yields son verbatim.
  - `test_llm_parser.py::test_stream_event_parser_finalize_uses_tier_1` — markdown
    fence se parsea via tier 2.
  - `test_filter_use_case.py::test_stream_execute_yields_meta_text_done` — secuencia
    completa de eventos con FakeLLMClient.
  - `test_filter_use_case.py::test_stream_execute_v1_path_no_meta_event` —
    `INTENT_EXTRACTION_ENABLED=false` → solo `text` + `done`.
  - `test_chat_route.py::test_stream_route_emits_sse_chunks` — parsear el body del
    StreamingResponse, assert `event:` y `data:` lines en orden.
  - `test_chat_route.py::test_stream_route_sends_keepalive` — configurar un
    aggregator fake que tarda 20s, assert que hay al menos 1 keepalive comment.
- **Integration**:
  - `test_chat_streaming.py::test_end_to_end_2stage_streaming` — happy path 2-stage
    con `FakeLLMClient.stream_complete` que emite `{"matching_ids": [...]}` en
    chunks.
  - `test_chat_streaming.py::test_end_to_end_v1_fallback_streaming` — v1 path.
  - `test_chat_streaming.py::test_cors_post_chat_stream_preflight` — OPTIONS
    preflight con `Origin: http://localhost:3000` → 200 con
    `Access-Control-Allow-Methods: ...POST...`.
  - `test_chat_endpoint_2stage.py::test_v1_endpoint_still_works_post_cors_fix`
    (modify or add) — regression anchor para el cambio de CORS.
- **Live (gated by `LLM_LIVE_TESTS=1`)**:
  - `test_chat_streaming_live.py::test_live_stream_2stage_high_confidence` — un
    test LIVE que exercise el path completo con `MiniMax-M3` real. Sigue el pattern
    de `test_chat_live.py`. Solo corre si `LLM_LIVE_TESTS=1`.

## Risks

1. **CORS preflight broken pre-existente** — `app_factory.py:666` `allow_methods=["GET"]`.
   El nuevo endpoint expone el bug. Se ARREGLA en este cambio (añadir `"POST"`).
2. **nginx buffering** — el default de nginx es `proxy_buffering on` que bufferiza
   responses > una threshold. Solución documented (no code) en el README: "if you
   deploy behind nginx, set `proxy_buffering off;` for `/jobs/chat/stream`". CloudFront
   tiene el mismo comportamiento. Documentar sin arreglar.
3. **`httpx` streaming + MockTransport** — el test debe yieldar SSE bytes. Verificable
   con `httpx.MockTransport(handler)` + un `handler` que devuelve
   `httpx.Response(200, content=<async iterator of bytes>)`. La doc de httpx confirma
   que MockTransport soporta `aiter_bytes` responses.
4. **MiniMax-M3 streaming format unknown** — la doc muestra M2.7. Asumimos mismo
   contrato (ChatCompletionChunk con `delta.content`). Verificar con captura real
   one-time (T-002 manual, AGENTS.md rule #1). Si M3 emite un delta shape diferente,
   el `stream_complete` falla y se ajusta. Riesgo BAJO.
5. **Generator exceptions mid-stream** — si el LLM cierra el stream abruptamente
   o un chunk tiene JSON malformado, el generator lanza. FastAPI's
   `StreamingResponse` lo convierte en 500 mid-stream (el cliente ya recibió algunos
   chunks — la UI debe manejar esto gracefully). Documentar.
6. **Cost double-billing en retry mid-stream** — la v1 tiene retry para 5xx/429. En
   streaming, un retry mid-stream NO TIENE SENTIDO (ya emitimos chunks al cliente).
   Política para streaming: NO retry; cualquier error mid-stream → `LLMStreamError`
   propagado. Documentar la diferencia.
7. **Token usage tracking** — el LLM emite `usage` solo en el último chunk de
   muchos providers; en streaming podemos capturar el `usage` para logging. Out of
   scope para v1; el route loggea solo el `request_id` final.

## Ready for Proposal

**Yes** — proceed to `sdd-propose` with:
- Wire format SSE definido (text + meta + done + keepalive).
- Strategy A (acumular + parse-at-end) recomendada.
- CORS fix incluido (POST añadido a `allow_methods`).
- Stage-1 silencioso, stage-3 streamea raw JSON.
- LOC forecast 350-550 (single PR, dentro del budget de 5000).
- Riesgos documentados con mitigaciones.
