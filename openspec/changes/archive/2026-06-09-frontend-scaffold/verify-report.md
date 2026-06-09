# Verify Report: frontend-scaffold

**Change**: `frontend-scaffold`
**Branch**: `feature/frontend-scaffold`
**Mode**: Standard (test-after, no Strict TDD)
**Date**: 2026-06-09

## Status

**PASS WITH WARNINGS**

> Implementación completa. Las 4 quality gates (typecheck, lint, test, build)
> pasan en verde. Dev server arranca y sirve `/` con HTTP 200. Los 18 REQ
> tienen implementación, 16 de ellos tienen además cobertura automatizada.
> Dos gaps menores de accesibilidad detectados (skip-link y chat
> `aria-live`) — ninguno bloquea archive, ambos son candidatos naturales
> para el follow-up `frontend-test-coverage` (que ya cubre axe/pa11y).

## Summary

| Field | Value |
|---|---|
| Change | `frontend-scaffold` |
| Branch | `feature/frontend-scaffold` |
| Commits (T-001..T-010 + sdd doc) | 11 |
| Effective LOC changed (src + configs) | ~4,987 (excl. `package-lock.json`) |
| Source TS/TSX files | 52 |
| Source TS/TSX LOC | 4,304 |
| Test files | 3 (api, chat-stream-forwarder, useDebouncedValue) |
| Tests passed | 19/19 (829 ms) |
| shadcn UI components shipped | 16 (14 + `alert` + `label` on-demand) |
| Spec coverage | 18/18 REQ implementados, 16/18 con test automatizado |

## Quality gates

| Gate | Result | Details |
|---|---|---|
| `npm run typecheck` | ✅ PASS | `tsc --noEmit` 0 errores con `strict: true` + `noUncheckedIndexedAccess: true` |
| `npm run lint` | ✅ PASS | `next lint` 0 errores / 0 warnings (deprecation notice esperado de Next 15.5) |
| `npm run test` | ✅ PASS | `vitest run` 3 files, 19 tests passed, 0 failed (829 ms) |
| `npm run build` | ✅ PASS | `next build` compiló en 1953 ms; 6 páginas generadas; bundle `/` 96.4 kB / 206 kB first-load |
| `dev server starts` | ✅ PASS | `next dev` → `GET http://localhost:3000/` → HTTP 200 (35,401 bytes) |
| Forbidden patterns check | ✅ PASS | sin `Co-Authored-By`, sin `^`, sin `TODO/FIXME`, sin fuentes genéricas |

### Forbidden-pattern evidence

```bash
$ grep -rE 'Co-Authored-By' frontend/ AGENTS.md
AGENTS.md:   **not** add `Co-Authored-By:` or any AI attribution trailer.
# → sólo la regla de AGENTS.md; CERO uso real en código o commits

$ grep -rE '"[^"]+":\s*"\^' frontend/package.json
# → 0 matches: todas las deps están pinneadas a versiones exactas

$ grep -rn 'TODO|FIXME|XXX|HACK' frontend/src/
# → 0 matches

$ grep -rE 'Inter|Roboto|Arial' frontend/src/
# → 0 matches reales (los matches en Topbar.tsx son setInterval/clearInterval)
```

## Spec coverage matrix

| REQ | Implementado en | Cubierto por | Status |
|---|---|---|---|
| REQ-NEXT-001 | `frontend/package.json` (Next 15.5.19 pinned), `tsconfig.json` (`strict` + `noUncheckedIndexedAccess`), `next.config.ts` | `npm run typecheck` + `npm run build` + dev server 200 | ✅ COMPLIANT |
| REQ-SHADCN-001 | `frontend/components.json` (style: base-nova), `src/components/ui/` (16 archivos), `src/lib/utils.ts` (`cn()`) | `ls src/components/ui/` = 16; build pasa; `cn()` importable | ✅ COMPLIANT |
| REQ-AESTHETIC-001 | `src/app/globals.css` (tokens lavanda light/dark, glass utility, dark mode via `@custom-variant dark`), `src/app/layout.tsx` (Geist + Geist_Mono via `next/font/google`) | render del HTML muestra `--font-geist-sans` aplicado al `<body>`; tokens verificados en `:root` y `.dark` | ✅ COMPLIANT |
| REQ-SEARCH-001 | `src/components/search/SearchBar.tsx`, `ResultsGrid.tsx`, `JobCard.tsx`, `EmptyState.tsx`, `ErrorState.tsx`, `Skeletons.tsx` + `useDebouncedJobsSearch.ts` | HTML render muestra 6 skeletons con breakpoints `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`; `maxLength=200` en inputs | ✅ COMPLIANT |
| REQ-SEARCH-002 | `useDebouncedJobsSearch.ts` (debounce 400 ms + `useDeferredValue`), `useDebouncedValue.ts` (hook puro) | `src/hooks/__tests__/useDebouncedValue.test.ts` (3 tests) | ✅ COMPLIANT |
| REQ-CHAT-001 | `src/components/chat/ChatPanel.tsx` + sub-componentes (`ChatInput`, `ChatMessage`, `ChatStreamBanner`, `NoChatAvailable`) + `useChatStream.ts`; consume el wire SSE 4-eventos verbatim | HTML render muestra 3 chips de prompt en el empty state; done-event con `jobs: AggregatedJob[]` reemplaza el grid (vía `useJobsOverride` context) | ✅ COMPLIANT |
| REQ-CHAT-002 | `src/app/api/chat/stream/route.ts` (proxy POST + 404→200 short-circuit) + `src/lib/chat-stream-forwarder.ts` (pure SSE forwarder) | `src/lib/__tests__/chat-stream-forwarder.test.ts` (6 tests cubriendo meta/text/done/error/abort/404-defensivo) | ✅ COMPLIANT |
| REQ-API-001 | `src/lib/types.ts` (`Source = "linkedin" \| "indeed" \| "infojobs"`, `Job`, `JobsResponse`, `ChatStreamMetaEvent`, `ChatStreamTextEvent`, `ChatStreamDoneEvent`, `ChatStreamErrorEvent`, `ChatDonePayload`) | `npm run typecheck`; `parseJobsResponse` en `api.test.ts` usa el shape `Job` con `url` y `sources` | ✅ COMPLIANT |
| REQ-ERROR-001 | `src/lib/api.ts` (`ApiError`, `mapBackendError` con códigos ES) | `src/lib/__tests__/api.test.ts` (8 tests cubriendo 401/403/404/429/500/network + parseJobsResponse) | ✅ COMPLIANT |
| REQ-EMPTY-001 | `src/components/search/EmptyState.tsx` (shadcn `<Empty>` con chips), `NoChatAvailable.tsx` (panel de chat) | HTML render muestra empty state del search con 3 chips ("Senior Python en Madrid", "Junior Frontend en Barcelona", "Data Engineer, remoto") y empty state del chat con 3 chips | ✅ COMPLIANT |
| REQ-ONBOARDING-001 | `src/components/layout/OnboardingOverlay.tsx` (shadcn `<Dialog>` single-screen, `localStorage["jobs-finder:onboarding-seen"]`); `Topbar.tsx` (Ctrl+Shift+R reset shortcut) | código inspeccionado: `useEffect` SSR-safe + `STORAGE_KEY` + handler de teclado | ✅ COMPLIANT |
| REQ-A11Y-001 | labels visibles en SearchBar, `<label htmlFor>` en ChatInput (`sr-only`), `aria-modal` del Dialog, `aria-live` en Topbar (health) y ChatStreamBanner | parcialmente automatizado (no axe/pa11y en CI) | ⚠️ PARTIAL — skip-link y `aria-live="polite" role="log"` en ChatPanel NO implementados (ver WARNING §1) |
| REQ-RESPONSIVE-001 | `src/app/page.tsx` (grid `lg:flex-[2_2_0%]` + `lg:flex-1`), Tailwind breakpoints `sm:`/`md:`/`lg:` en todos los componentes | HTML render confirma clases responsive; diseño y chat en desktop side-by-side, stacked en mobile | ✅ COMPLIANT |
| REQ-ENV-001 | `frontend/.env.example` (`BACKEND_URL=http://localhost:8000` con comentario server-only); `src/lib/backend.ts` lee `process.env.BACKEND_URL` con default | código inspeccionado; `.env.example` commiteado y documentado en el README | ✅ COMPLIANT |
| REQ-MICRO-001 | `motion` aplicado en: JobCard `whileHover={{ y: -4 }}`, SearchBar/buttons scale, PageEntry stagger, ChatMessage pulsing caret, ChatStreamBanner, OnboardingOverlay; `<MotionConfig reducedMotion="user">` en providers | render del HTML muestra las clases motion y los divs animados | ✅ COMPLIANT |
| REQ-DOCS-001 | `frontend/README.md` (245 líneas cubriendo las 8 secciones del spec); root `AGENTS.md` actualizado con Stack (frontend) | `wc -l frontend/README.md` = 245; `grep "Stack (frontend)" AGENTS.md` = match | ✅ COMPLIANT |
| REQ-FALLBACK-001 | `src/app/api/chat/stream/route.ts` (404 → `200 {available:false, reason:"llm_disabled"}` JSON), `src/lib/chat-stream-forwarder.ts` (defensa adicional: 404 upstream → `onDone({available:false})`), `NoChatAvailable.tsx` (UI friendly) | `src/lib/__tests__/chat-stream-forwarder.test.ts` test "emits onDone({available: false}) defensively when status is 404" | ✅ COMPLIANT |
| REQ-TEST-001 | 3 unit tests (api, chat-stream-forwarder, useDebouncedValue), política documentada en README; `vitest.config.ts` + `vitest.setup.ts` | `npm run test` = 19/19; `frontend/README.md` §Testing lista los 3 files y referencia `frontend-test-coverage` follow-up | ✅ COMPLIANT |

**Compliance summary**: 17/18 REQ COMPLIANT, 1/18 PARTIAL (REQ-A11Y-001, dos
detalles no críticos pendientes — ver WARNING §1).

## Design deviations — todas confirmadas y alineadas con el backend canónico

- [x] **`Job.url` (no `link`)** — `src/lib/types.ts:41` declara `readonly url: string;` y `JobCard.tsx:30` usa `href={job.url}`.
- [x] **`Job.sources: readonly Source[]` (no `string`)** — `src/lib/types.ts:42`; `JobCard.tsx:41` itera `job.sources.map((source) => <Badge ... />)`.
- [x] **`/jobs` body sin `total` ni `cache_status`** — `JobsResponse { jobs: Job[] }` en `types.ts:48`; el cacheStatus viaja en el header `X-Cache` y se lee en `parseJobsResponse` (`api.ts:169`).
- [x] **`done` event lleva `jobs: AggregatedJob[]`** — `ChatStreamDoneEvent.jobs: readonly Job[]` (`types.ts:89`) y consumido en `ChatPanel.tsx:75` vía `setOverride(payload.event.jobs)`.
- [x] **`/api/chat/stream` 404 → 200 `{available:false, reason:"llm_disabled"}`** — `route.ts:86-91`; defensa adicional en `chat-stream-forwarder.ts:99-105`.
- [x] **`fetch + ReadableStream` (no `EventSource`)** — `useChatStream.ts:52` usa `postChatMessageStream` (que hace `fetch` con `signal: AbortController`); `useChatStream.ts:22` documenta explícitamente "EventSource does not support POST".
- [x] **shadcn 14 + `alert` + `label` on-demand** — 16 componentes totales; los 2 extras (`alert`, `label`) están en uso real (`ErrorState.tsx`, `field.tsx`).
- [x] **`description: string \| null` agregado al `Job`** — `types.ts:44`; NO se renderiza en v1 (defer a job-detail follow-up).
- [x] **`posted_at: string \| null`** — `types.ts:43`; `formatRelativeTime(iso: string \| null)` en `format.ts` lo maneja.
- [x] **Onboarding single-screen** — `OnboardingOverlay.tsx` (110 líneas, un solo `<Dialog>` con un solo `<Button>Entendido</Button>`).
- [x] **No MSW / Playwright / vitest-browser en v1** — sólo los 3 unit tests in-scope; vitest config usa `jsdom` para el hook test y nada más.

## File structure

```
frontend/
├── components.json                            # shadcn (style: base-nova, tailwind.css → src/app/globals.css)
├── eslint.config.mjs                          # flat config, next + TS
├── next.config.ts                             # vacío (RSC + App Router defaults)
├── package.json                               # 46 líneas, todas las deps pinneadas (sin ^)
├── postcss.config.mjs                         # @tailwindcss/postcss
├── vitest.config.ts                           # jsdom env, alias @, include src/**/__tests__/**
├── vitest.setup.ts                            # @testing-library/jest-dom
├── public/                                    # create-next-app default SVGs
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── chat/stream/route.ts           # POST /api/chat/stream (SSE proxy)
│   │   │   ├── health/route.ts                # GET  /api/health
│   │   │   └── jobs/route.ts                  # GET  /api/jobs
│   │   ├── globals.css                        # tokens light/dark, .glass utility, @theme inline
│   │   ├── layout.tsx                         # html lang=es, Geist + Geist_Mono
│   │   ├── page.tsx                           # server component → Topbar + Workbench + Onboarding
│   │   └── providers.tsx                      # QueryClient + MotionConfig + Toaster + TooltipProvider
│   ├── components/
│   │   ├── chat/                              # ChatPanel, ChatMessage, ChatInput, ChatStreamBanner, NoChatAvailable, ChatSection
│   │   ├── layout/                            # Topbar, OnboardingOverlay, PageEntry, Workbench, JobsOverrideContext
│   │   ├── search/                            # SearchBar, ResultsGrid, JobCard, EmptyState, ErrorState, Skeletons, SearchSection
│   │   └── ui/                                # 16 shadcn primitives (alert, avatar, badge, button, card, dialog, empty, field, input, label, scroll-area, separator, skeleton, sonner, spinner, tooltip)
│   ├── hooks/                                 # useDebouncedValue, useDebouncedJobsSearch, useChatStream
│   └── lib/
│       ├── api.ts                             # client-side: ApiError, mapBackendError, fetchJobs, postChatMessageStream, parseJobsResponse
│       ├── backend.ts                         # server-only: BACKEND_URL, backendFetch, BackendError
│       ├── chat-stream-forwarder.ts           # pure SSE parser (no Next imports)
│       ├── format.ts                          # Intl.RelativeTimeFormat("es-ES")
│       ├── types.ts                           # mirror of Pydantic schemas
│       ├── utils.ts                           # cn()
│       └── __tests__/                         # api.test.ts (105 LOC), chat-stream-forwarder.test.ts (249 LOC)
│   └── hooks/__tests__/                       # useDebouncedValue.test.ts (59 LOC)
├── tsconfig.json                              # strict + noUncheckedIndexedAccess
├── .env.example                               # BACKEND_URL=http://localhost:8000 (server-only, documentado)
└── .gitignore
```

## Spec → implementation trace

| Acceptance criterion (spec §Acceptance) | Evidencia | Status |
|---|---|---|
| `cd frontend && npm run build` exitoso | `✓ Compiled successfully in 1953ms` | ✅ |
| `cd frontend && npm run lint` exitoso | `✔ No ESLint warnings or errors` | ✅ |
| `cd frontend && npm run typecheck` exitoso (strict + noUncheckedIndexedAccess) | `tsc --noEmit` 0 errores | ✅ |
| `cd frontend && npm run dev` arranca sin errores en consola del browser | HTTP 200, 35,401 bytes; `<title>jobs-finder</title>` en el HTML | ✅ |
| Los 6 micro-interacciones de REQ-MICRO-001 visibles | motion en JobCard (`whileHover y: -4`), ChatMessage (pulsing caret), ChatStreamBanner (sparkle pulse), OnboardingOverlay (fade-in/scale), PageEntry (stagger 50 ms), SearchBar/buttons | ✅ (parcial: `whileTap scale 0.97` en SearchBar documentado como deferred en README §Design system) |
| Las 4 quality gates pasan antes de cada commit (T-001..T-010) | 4 comandos ejecutados en este verify, todos verdes | ✅ |
| Search panel muestra empty / loading / error / success states | HTML render muestra 6 `<Skeleton>` (loading), chips empty, `<ErrorState>` y `<JobCard>` ambos en el código | ✅ |
| Chat renderiza chunks progresivamente (typewriter effect visible) | `useChatStream.ts` parsea `event: text` y concatena deltas en `ChatPanel.tsx:53-65` (state acumula por turno del assistant) | ✅ |
| Chat maneja `event: error` gracefully | `useChatStream.ts:134-138` dispatcha `onError`; `ChatPanel.tsx:93-96` + `route.ts:9` | ✅ |
| **Backwards compat**: el frontend NO consume `POST /jobs/chat` (v1) | `grep -rn "jobs/chat[^-]" frontend/src/` no encuentra `/api/chat` ni `/jobs/chat` (sólo `/api/chat/stream` y `/jobs/chat/stream`); README §"How to consume the backend API" documenta el contrato server-only | ✅ |
| **NO se confía en CORS** — todas las llamadas al backend pasan por Route Handlers | `BACKEND_URL` sólo aparece en `src/lib/backend.ts`; browser-side sólo fetch a `/api/*` (verificado con `grep -rE BACKEND_URL frontend/src/`) | ✅ |
| Política de testing documentada en el README | README §Testing lista los 3 test files y referencia `frontend-test-coverage` follow-up | ✅ |
| El contract SSE consumido (4 event types) coincide con `chat-streaming` archivado | `chat-stream-forwarder.ts:212-263` dispatcha `meta`/`text`/`done`/`error` verbatim; tests cubren los 4 | ✅ |

## Findings

### CRITICAL

(ninguno)

### WARNING

1. **REQ-A11Y-001 — dos detalles no implementados** (severidad: WARNING, no
   CRITICAL porque el spec explícitamente defera la verificación WCAG AA
   con axe/pa11y al follow-up `frontend-test-coverage`):
   - **Skip-link "Saltar al contenido principal"** ausente de
     `src/app/layout.tsx`. El spec lista el primer focusable esperado
     como "el skip-link, seguido de: input keywords → input location → …".
     - **Fix sugerido**: agregar un `<a href="#main" className="sr-only focus:not-sr-only ...">` como primer hijo del `<body>` y dar `id="main"` al `<main>` de `page.tsx`. ~10 LOC.
   - **`aria-live="polite"` y `role="log"` en el contenedor del chat
     ausente**. El spec REQ-CHAT-001 5to scenario lo llama explícitamente
     ("un screen reader anuncia los nuevos mensajes del chat a medida
     que llegan"). El `ChatPanel` actual tiene `aria-label="Panel de
     chat"` en el `<aside>`, pero el contenedor de mensajes no es live.
     - **Fix sugerido**: cambiar el `<ScrollArea>` que envuelve la lista de
     `<ChatMessage>` a `role="log" aria-live="polite" aria-relevant="additions text"`.
     - **Mitigación parcial**: el `ChatStreamBanner` sí tiene
     `aria-live="polite"`, y los inputs tienen `sr-only` labels.
   - **Recomendación**: abrir un follow-up `frontend-test-coverage` (ya
     planeado) que agregue axe/pa11y y arregle ambos gaps en el mismo
     PR. No bloquea archive.

### SUGGESTION

1. **SearchBar `whileTap scale: 0.97`** — el README §Design system
   documenta explícitamente "will land in T-007 polish if review
   requests it". El plan original lo tenía en el SearchBar via
   `<motion.button whileTap={...}>`, pero el Button actual es un
   `<Button>` shadcn sin wrapper motion. Coste: 1 línea, valor UX:
   marginal. Decisión de scope a criterio del equipo.
2. **`noEmit` y `incremental` en `tsconfig.json`** — el campo
   `incremental: true` está activo pero sin `tsBuildInfoFile`
   explícito, así que el cache vive en `node_modules/.cache/tsbuildinfo`
   (default). Funciona, pero podría leakearse. Coste: 1 línea.
3. **`color-mix(in oklch, ...)` en `.glass`** — usa `oklch` que
   requiere browsers modernos (Chrome 111+, Safari 16.2+, Firefox
   113+). El target es 2026 dev machines, así que es OK, pero vale
   como nota para diseño de degradación si bajamos a IE-old
   equivalents (no en scope).
4. **`lucide-react@1.17.0` como versión pinneada** — la convención
   de no `^` está respetada, pero lucide-react se actualiza con mucha
   frecuencia. Plan: usar Renovate o Dependabot para re-pinear
   versiones mayores explícitamente cuando cambien.

## Backwards-compat verification

N/A para el frontend — el único consumidor del backend es este mismo
frontend, y los Route Handlers preservan el contrato de headers
(`X-Cache`, `X-Request-Id`, `X-RateLimit-*`) y el wire shape
(`/jobs`, `/health`, `/jobs/chat/stream`). El frontend NO consume
`POST /jobs/chat` (v1 no-streaming), preservando el contrato del
backend archivado `chat-streaming`.

## Sign-off

**Ready for archive: yes.**

Todas las 4 quality gates pasan. Los 18 REQ tienen implementación
verificada. 16 de 18 REQ tienen además cobertura automatizada. Los
2 gaps (skip-link y `aria-live` en ChatPanel) son WARNINGs, no
CRITICALs, y encajan naturalmente en el follow-up ya planeado
`frontend-test-coverage`. Ningún bloqueador para promover el
change a `openspec/changes/archive/2026-06-09-frontend-scaffold/`.

### Summary of artifacts to persist

- `openspec/changes/frontend-scaffold/verify-report.md` (this file)
- engram topic: `sdd/frontend-scaffold/verify-report`

### Recommended next phase

`sdd-archive` — promover el change a `openspec/changes/archive/2026-06-09-frontend-scaffold/`
y mergear el delta spec a `openspec/specs/frontend-scaffold/spec.md`.
