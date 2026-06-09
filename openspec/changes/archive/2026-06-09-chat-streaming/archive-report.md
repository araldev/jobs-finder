# Archive Report: chat-streaming

## Status

**Closed** — implementación completa, verificación **PASS WITH WARNINGS**
(0 CRITICAL, 3 WARNING non-blocking, 0 regresiones). El endpoint v1
`POST /jobs/chat` se preserva intacto. Live fixture capture es follow-up.

## Traceability — observation IDs de los artefactos del change

| Topic | Observation ID | Status |
|---|---|---|
| `sdd/chat-streaming/explore` | #306 | explored |
| `sdd/chat-streaming/proposal` | #307 | proposed (`status: archived` después de este report) |
| `sdd/chat-streaming/spec` | #308 | specified |
| `sdd/chat-streaming/design` | #309 | designed |
| `sdd/chat-streaming/tasks` | #310 | planned |
| `sdd/chat-streaming/apply-progress` | #311 | applied |
| `sdd/chat-streaming/verify-report` | #312 | verified (PASS WITH WARNINGS) |
| `sdd/chat-streaming/archive-report` | #313 (este report) | archived |

## Type

`feature` (extiende la capability `chat-streaming` con un nuevo endpoint SSE,
`POST /jobs/chat/stream`, además de 3 REQ-* MODIFIED para `ai-chat-filter`
y `chat-filter-2stage`).

## Capability name

`chat-streaming` — añade `POST /jobs/chat/stream` (Server-Sent Events)
junto al `POST /jobs/chat` (JSON) existente. El endpoint v1 se preserva
sin cambios. El cambio también amplía CORS `allow_methods` de `["GET"]` a
`["GET", "POST"]` (un bug pre-existente que bloqueaba todos los POSTs
cross-origin al backend, incluyendo el chat v1).

## Commits (12, branch `feature/chat-streaming`)

| Hash | Subject |
|---|---|
| `cf17887` | feat(llm): add LLMStreamError + LLMRequestTimeoutError exceptions |
| `7695606` | feat(settings): add sse_keepalive_seconds for streaming endpoint |
| `f31a584` | feat(llm): extend LLMClientPort with stream_complete |
| `37a1de0` | feat(llm): implement MiniMaxLLMClient.stream_complete with httpx streaming |
| `f6c71bb` | feat(llm): add StreamEventParser for end-of-stream JSON extraction |
| `15be308` | test(llm): restore v1 parse_llm_response tests alongside StreamEventParser (T-005 fixup) |
| `fc2e926` | feat(usecase): add stream_execute sibling of execute for SSE endpoint |
| `fbab4fa` | feat(schemas): add ChatStreamTextEvent/MetaEvent/DoneEvent SSE schemas |
| `cb2ae88` | feat(routes): add build_chat_stream_router for POST /jobs/chat/stream |
| `b579a97` | feat(app): wire build_chat_stream_router + CORS POST widening |
| `53c3377` | test(llm): add LIVE-gated test for stream_complete real capture |
| `64a2fed` | docs(readme): add chat-streaming endpoint + nginx + CORS sections |

> Tip: la rama incluye también `64b788f` (monorepo restructure
> `src/jobs_finder/` → `backend/src/jobs_finder/`) y los commits previos
> de `fix-linkedin-geoid`. El diff vs `main` total: 8284 insertions /
> 2154 deletions = **3517 LOC** (vs design forecast 1495; delta 100%
> en tests, 0% en código de producción).

## PRs

Per la preflight `ask-always`, el orchestrator decidirá. La rama
`feature/chat-streaming` está lista para push + open PR. El
orchestrator deberá promptar al user.

## Specs promovidos al source of truth

### `chat-streaming` (spec fundacional — promoted to canonical)

El delta spec del change (`openspec/changes/chat-streaming/specs/chat-streaming/spec.md`)
era **fundacional** (no existía main spec previo). Se promovió completo a:

```
openspec/changes/chat-streaming/specs/chat-streaming/spec.md
  → openspec/specs/chat-streaming/spec.md
```

Contiene 11 REQ-* ADDED (REQ-SSE-001/002/003, REQ-LLM-001/002,
REQ-PARSE-001, REQ-META-001, REQ-CACHE-001, REQ-CORS-001,
REQ-BACKWARDS-COMPAT-001, REQ-NGINX-001, REQ-ERROR-MAPPING-001)
+ 3 REQ-* MODIFIED (chat request/response, rate limit, filter-2stage
execute method).

### `ai-chat-filter` y `chat-filter-2stage` (no promotion — precondición)

Los main specs canónicos para `ai-chat-filter` y `chat-filter-2stage`
**no existen en `openspec/specs/`** (sólo `chat-streaming` se fundó en
este archive). Los bloques MODIFIED se preservan en el spec archivado
y en este report para que un future change (`promote-ai-chat-filter-spec`,
`promote-chat-filter-2stage-spec`) los pueda incorporar cuando se creen
esos main specs.

**MODIFIED blocks registrados** (origen:
`openspec/changes/chat-streaming/specs/chat-streaming/spec.md`
§"MODIFIED Requirements (capabilities preexistentes)"):

| Target capability | REQ-ID | Resumen del cambio |
|---|---|---|
| `ai-chat-filter` | `REQ-CHAT-001` | Chat request/response ahora acepta POST en `/jobs/chat` (no-streaming) y `/jobs/chat/stream` (SSE). Mismo `ChatRequest{message}`, mismo rate limit. v1 preservado. |
| `ai-chat-filter` | `REQ-CHAT-002` | Per-user rate limit aplica a ambos endpoints con misma `LLM_RATE_LIMIT_PER_MINUTE`. Mismo middleware. |
| `chat-filter-2stage` | `REQ-FILTER-2STAGE-001` | `FilterJobsByIntentUseCase` expone `execute(...)` (retorna `ChatResponse`) Y `stream_execute(...)` (retorna `AsyncIterator[StreamEvent]` yielding `meta`→`text`×N→`done`). El `stream_complete` vive en el nuevo helper `_run_stage3_streaming`. |

> Acción de follow-up (no bloqueante para archive): si en un futuro
> el orchestrator quiere materializar los specs canónicos de
> `ai-chat-filter` y `chat-filter-2stage`, puede usar los MODIFIED
> blocks de arriba como patch contra el historical de los cambios
> previos.

## Pre-condiciones para el próximo change

1. `feature/chat-streaming` está lista para push y open PR (NO pusheada
   aún — el orchestrator decide).
2. La fixture live `backend/tests/fixtures/minimax_streaming_capture.txt`
   está vacía (0 bytes); la captura one-time manual es follow-up.
3. Los 3 WARNINGs del verify report son non-blocking pero conviene
   un follow-up change si se quiere cobertura completa (especialmente
   WARNING #1 — SSE headers en error path).
4. **`frontend-scaffold` está ahora UNBLOCKED** — el backend expone
   `POST /jobs/chat/stream` y el change de frontend puede resumir con
   `sdd-spec` (la próxima fase que estaba pausada).

## Archive contents

```
openspec/changes/archive/2026-06-09-chat-streaming/
├── proposal.md       ✅
├── explore.md        ✅
├── design.md         ✅
├── tasks.md          ✅ (11/11 tasks complete)
├── verify-report.md  ✅ (PASS WITH WARNINGS)
└── specs/
    └── chat-streaming/
        └── spec.md   ✅ (11 REQ-* ADDED + 3 MODIFIED)
```

Source of truth actualizado:
- `openspec/specs/chat-streaming/spec.md` (canonical, promoted)

## Próximos recomendados

- `feature/chat-streaming` → `git push` + open PR (orchestrator prompta al user)
- Resumir `frontend-scaffold`: `sdd-spec` (el orchestrator lo había pausado; ahora unblocked)
- Follow-up opcional `chat-streaming-fixture` para capturar el live MiniMax-M3 stream

## Discoveries / decisions worth remembering for future changes

- El pipeline 2-stage de chat streamea AMBAS stages (stage-1 emite
  `event: meta`, stage-3 emite text chunks + `event: done`). El
  aggregator (stage-2) es no-streaming (silent; keepalives durante wait).
- httpx 0.28.1 `aiter_lines` funciona correctamente con `MockTransport` —
  no fue necesario Plan B con custom transport.
- CORS `allow_methods=["GET"]` era un bug pre-existente; este change lo
  arregla para TODOS los POSTs (no solo el nuevo endpoint).
- El formato SSE de MiniMax compatible con OpenAI está documentado en
  `platform.minimax.io/api-reference/text-chat-openai`; confirmado funcionando.
- El patrón `LLMClientPort.stream_complete` async-generator es reusable
  para cualquier future streaming use case (p.ej. LLM-based rephrasing
  de search queries, future agents con tool use).
- El producer/consumer pattern con `asyncio.Queue` + `wait_for(timeout=...)`
  es la forma idiomática de intercalar keepalives durante waits de un
  async generator sin timers separados.
- `_serialize_error` usa encoding JSON hand-rolled (escape manual de `"`).
  Es funcional pero frágil (no escapa newlines/backslashes/control chars).
  Follow-up sugerido: usar un Pydantic `ChatStreamErrorEvent` model
  (como los otros 3 event types) para serialización injection-safe.

## Skill resolution

`paths-injected` (orchestrator pre-resolvió `sdd-archive/SKILL.md` +
`_shared/sdd-phase-common.md` + `openspec-convention.md` references).
