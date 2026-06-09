# Tasks: frontend-scaffold

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2980 LOC |
| 400-line budget risk | Low (single PR, pero sobre el review budget de 5000) |
| Chained PRs recommended | No (user decided single PR) |
| Suggested split | single PR, 10 commits, ~300 LOC avg per commit |
| Delivery strategy | ask-always (resolves to no-stop: 2980 < 5000) |
| Chain strategy | size:exception (single PR accepted) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

> **Nota sobre el budget**: el "400-line budget" del guardrail es el
> patrón del skill `chained-pr`; este proyecto usa **review budget
> 5000** (configurado en el preflight). 2980 LOC está bien debajo
> del límite → single PR, no se necesita decisión del usuario.

## Work unit overview

El frontend se construye en 10 tareas con disciplina **test-after**
(no strict TDD — el proyecto solo aplica TDD estricto a Python, ver
`AGENTS.md`). T-001..T-003 son scaffold puro (Next.js, shadcn,
aesthetic tokens). T-004 es la fundación lógica (types, api, hooks
puros, chat-stream-forwarder). T-005 son los 3 Route Handlers.
T-006 es el shell de layout (root layout, page, providers, topbar,
onboarding). T-007 y T-008 son las dos mitades de UI (search y
chat) en paralelo-friendly. T-009 son los 3 unit tests
(`api.test.ts`, `chat-stream-forwarder.test.ts`,
`useDebouncedValue.test.ts`) — los únicos tests in-scope para v1;
E2E + MSW + component tests van al follow-up
`frontend-test-coverage`. T-010 cierra con docs.

Cada tarea se verifica con `tsc --noEmit` + `next lint` + `next
build` antes de commitear. Los 3 unit tests corren con `vitest
run` antes de cerrar T-009.

## Work units

### T-001: Next.js 15 scaffold + TypeScript strict + Tailwind v4

**Type**: scaffold
**Scope**:
- Correr `npx create-next-app@latest frontend --typescript --tailwind --app --src-dir --import-alias "@/*" --no-eslint --use-npm` desde la raíz del monorepo
- Verificar layout esperado: `frontend/src/app/`, `frontend/public/`
- Fijar versiones de TODAS las dependencias en `package.json` (sin `^`; usar `~` para patch-only)
- `tsconfig.json`: agregar `"noUncheckedIndexedAccess": true` a `compilerOptions`
- Agregar scripts en `package.json`: `dev`, `build`, `start`, `lint`, `typecheck` (`tsc --noEmit`), `test` (`vitest run`)
- Agregar dev-deps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`
- Crear `frontend/.env.example` con `BACKEND_URL=http://localhost:8000`
- Crear `frontend/.gitignore` (Node + Next.js + `.env*` excepto `.env.example`)

**Files**:
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/next.config.ts`
- `frontend/postcss.config.mjs`
- `frontend/tailwind.config.ts` (o CSS-only para v4)
- `frontend/.env.example`
- `frontend/.gitignore`
- `frontend/src/app/page.tsx` (default de create-next-app, se reemplaza en T-006)
- `frontend/src/app/layout.tsx` (default, se modifica en T-003 y T-006)
- `frontend/src/app/globals.css`

**Acceptance**:
- `cd frontend && npm install` completa sin errores
- `cd frontend && npm run dev` arranca y la página default renderiza en `localhost:3000`
- `cd frontend && npm run typecheck` pasa (strict + noUncheckedIndexedAccess)
- `cd frontend && npm run build` succeeds
- `cd frontend && npm run lint` pasa
- Todas las versiones de deps están pinneadas (`~` no `^`)

### T-002: shadcn/ui init con preset `base-nova` + 14 componentes

**Type**: scaffold
**Scope**:
- Correr `npx shadcn@latest init` con preset `base-nova`, template `next`, CSS file `src/app/globals.css`, alias `cn → @/lib/utils`
- Verificar que `components.json` queda commiteado con la config correcta
- Agregar los **14 componentes de v1** (en este orden, para que las dependencias entre componentes se resuelvan en orden topológico):
  1. `button`
  2. `input`
  3. `card`
  4. `badge`
  5. `separator`
  6. `skeleton`
  7. `avatar`
  8. `tooltip`
  9. `scroll-area`
  10. `empty`
  11. `field`
  12. `spinner`
  13. `sonner` (toast notifications)
  14. `dialog`
- Verificar `npx shadcn@latest info` reporta el proyecto correctamente
- Verificar que cada componente tiene su(s) archivo(s) en `src/components/ui/`

**Files**:
- `frontend/components.json`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/separator.tsx`
- `frontend/src/components/ui/skeleton.tsx`
- `frontend/src/components/ui/avatar.tsx`
- `frontend/src/components/ui/tooltip.tsx`
- `frontend/src/components/ui/scroll-area.tsx`
- `frontend/src/components/ui/empty.tsx`
- `frontend/src/components/ui/field.tsx`
- `frontend/src/components/ui/spinner.tsx`
- `frontend/src/components/ui/sonner.tsx`
- `frontend/src/components/ui/dialog.tsx`
- `frontend/src/lib/utils.ts` (el `cn()` que genera shadcn init)

**Acceptance**:
- `npx shadcn@latest info` corre sin errores y lista los 14 componentes
- `cn()` es importable desde `@/lib/utils`
- `globals.css` tiene las CSS variables de shadcn (light + dark mode tokens) **incluso si T-003 las va a sobreescribir** (T-003 edita este mismo archivo; el orden T-002 → T-003 es seguro)
- `npm run typecheck` y `npm run build` siguen pasando después de agregar los 14 componentes

### T-003: Aesthetic tokens en globals.css + Geist font

**Type**: aesthetic
**Scope**:
- Editar `frontend/src/app/globals.css` para reemplazar los tokens default de shadcn con los del diseño **Soft/Modern Glass con lavender accent**:
  - **Light mode** (`:root`): `--background: #FAFAF9`, `--foreground: #0A0A0F`, `--card: #FFFFFF`, `--card-foreground: #0A0A0F`, `--accent: #A78BFA` (lavender), `--accent-foreground: #FFFFFF`, `--border: rgba(0,0,0,0.08)`, `--input: rgba(0,0,0,0.08)`, `--ring: #A78BFA`
  - **Dark mode** (`.dark`): `--background: #0A0A0F`, `--foreground: #FAFAF9`, `--card: #1A1A1F`, `--card-foreground: #FAFAF9`, `--accent: #C4B5FD` (lavanda más clara), `--accent-foreground: #0A0A0F`, `--border: rgba(255,255,255,0.08)`, `--input: rgba(255,255,255,0.08)`, `--ring: #C4B5FD`
  - **Glassmorphism utility** (al final de `globals.css`):
    ```css
    @layer utilities {
      .glass {
        @apply backdrop-blur-md bg-card/80 border border-border/50;
      }
    }
    ```
- Configurar dark mode en `tailwind.config.ts` (o en `globals.css` si Tailwind v4 CSS-only): `darkMode: "media"` para que siga `prefers-color-scheme`
- Modificar `frontend/src/app/layout.tsx` para cargar Geist vía `next/font/google`:
  - `const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" })`
  - `const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" })`
  - Aplicar `${geistSans.variable} ${geistMono.variable}` al `<html>`
  - Body con `className="font-sans antialiased"`

**Files**:
- `frontend/src/app/globals.css` (modify — reemplaza tokens default de T-002)
- `frontend/src/app/layout.tsx` (modify — añade fonts; T-006 va a sobreescribir este archivo con QueryClientProvider, pero el font setup se mantiene)
- `frontend/tailwind.config.ts` (modify — `darkMode: "media"`) o `frontend/src/app/globals.css` (Tailwind v4 `@variant dark (...)`)

**Acceptance**:
- `npm run dev` muestra Geist font sin FOUC ni layout shift
- Light mode renderiza background bone-white `#FAFAF9` con botón de búsqueda lavender `#A78BFA`
- DevTools "Emulate prefers-color-scheme: dark" cambia a ink-black `#0A0A0F` automáticamente
- `.glass` utility es utilizable en cualquier componente
- `npm run typecheck` + `npm run build` siguen pasando

### T-004: lib/ (types, api, backend, format, chat-stream-forwarder) + hooks/

**Type**: foundation
**Scope**:
- **`src/lib/types.ts`**: tipos alineados con el backend canónico (ver obs #316, decisiones de diseño):
  - `type Source = "linkedin" | "indeed" | "infojobs"`
  - `interface Job { id: string; title: string; company: string; location: string; url: string; sources: Source[]; posted_at: string | null; description: string | null }`
  - `interface JobsResponse { jobs: Job[] }` (sin `total` ni `cache_status` en el body — esos viven en headers)
  - `type CacheStatus = "HIT" | "MISS"`
  - `interface SearchResult { jobs: Job[]; cacheStatus: CacheStatus }` (cliente-friendly, usado por los hooks)
  - Tipos de SSE events: `MetaEvent`, `TextEvent`, `DoneEvent`, `ErrorEvent`
  - `interface ChatDonePayload { jobs: Job[]; explanation: string; total_considered: number; total_matched: number; used_fallback: boolean; request_id: string }`
  - `interface ChatUnavailable { available: false; reason: "llm_disabled" }`
- **`src/lib/api.ts`** (client-side, browser-safe): `class ApiError extends Error` con `status`, `code`, `requestId`, `retryAfter?`. Función `mapBackendError(status, body, requestId)`. Funciones `fetchJobs({ keywords, location, limit, sources })` y `postChatMessageStream({ message })` que llaman a los Route Handlers (NUNCA al backend directo). Helper `parseJobsResponse(res): SearchResult` que lee `X-Cache` header.
- **`src/lib/backend.ts`** (server-only, marcado con `import "server-only"`): `const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"`. Helper `async function backendFetch(path, init): Promise<Response>` que añade `X-Forwarded-By: jobs-finder-frontend` y timeouts. Valida env al import-time.
- **`src/lib/format.ts`**: `formatRelativeTime(iso: string | null): string` ("2 days ago", "Just now", "30+ days ago") usando `Intl.RelativeTimeFormat`.
- **`src/lib/chat-stream-forwarder.ts`** (PURO, sin imports de Next.js): exporta `async function forwardChatStream({ backendResponse, controller, onMeta, onText, onDone, onError }): Promise<void>`. Lee `backendResponse.body` como `ReadableStream`, parsea SSE chunks (separador `\n\n`, formato `event: ...\ndata: ...`), invoca callbacks tipados. Maneja `controller.signal` para abort. Si `backendResponse.status === 404`, emite `onDone({ available: false, reason: "llm_disabled" })` directamente (la conversión 404→200 la hace el Route Handler, pero el forwarder debe ser defensivo).
- **`src/hooks/useDebouncedValue.ts`**: hook genérico `useDebouncedValue<T>(value: T, delayMs: number): T`. Usa `useEffect` con `setTimeout`, cleanup cancela timer.

**Files**:
- `frontend/src/lib/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/backend.ts`
- `frontend/src/lib/format.ts`
- `frontend/src/lib/chat-stream-forwarder.ts`
- `frontend/src/hooks/useDebouncedValue.ts`

**Acceptance**:
- `npm run typecheck` pasa (strict + noUncheckedIndexedAccess)
- Todos los tipos importables desde `@/lib/types`, `@/lib/api`, etc.
- `forwardChatStream` es puro: dado un `ReadableStream` de `fetch()`, parsea eventos correctamente. CERO imports de `next/*`.
- `backend.ts` tiene `import "server-only"` al top
- `api.ts` no tiene `import "server-only"` (es client-side)

### T-005: Route Handlers (3 archivos)

**Type**: route-handlers
**Scope**:
- **`src/app/api/jobs/route.ts`** (GET):
  - Lee `keywords`, `location`, `limit`, `sources` de `request.nextUrl.searchParams`
  - Construye query string para el backend: `BACKEND_URL + "/jobs?" + qs`
  - `await backendFetch(path, { headers: { "X-Forwarded-By": "jobs-finder-frontend" } })`
  - Forwardea el body como `NextResponse.json(jobsBody, { status: backendRes.status })` con headers seleccionados copiados: `X-Cache`, `X-Request-Id`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
  - Mapea errores 5xx/429/404 a `ApiError` shape vía el `mapBackendError` (re-exportado de `lib/api.ts`)
- **`src/app/api/chat/stream/route.ts`** (POST):
  - Lee `{ message }` del body (valida con zod o manual type guard)
  - Si mensaje vacío → 400 con `{ error: { code: "empty_message", message: "..." } }`
  - Construye el request al backend: `POST BACKEND_URL/jobs/chat/stream` con `{ message }`
  - Usa `forwardChatStream` para reenviar el SSE al cliente
  - **CRÍTICO (REQ-FALLBACK-001)**: si `backendRes.status === 404`, responde `200` con `{ available: false, reason: "llm_disabled" }` como `application/json` (NO como SSE). El cliente NUNCA ve un 404.
  - Content-Type: `text/event-stream` para el caso normal
  - Maneja `AbortSignal` de `request.signal` para cleanup
- **`src/app/api/health/route.ts`** (GET):
  - `await backendFetch(BACKEND_URL + "/health")`
  - Forwardea status + body tal cual (sin mapeo). El topbar usa el 200/503 para el indicator visual.

**Files**:
- `frontend/src/app/api/jobs/route.ts`
- `frontend/src/app/api/chat/stream/route.ts`
- `frontend/src/app/api/health/route.ts`

**Acceptance**:
- `npm run typecheck` pasa
- `npm run build` succeeds
- `npm run lint` pasa
- Smoke test manual con backend corriendo en :8000:
  - `curl http://localhost:3000/api/jobs?keywords=python&location=madrid` → 200 con JSON
  - `curl http://localhost:3000/api/health` → 200 o 503 según el backend
  - `curl -X POST -H "Content-Type: application/json" -d '{"message":"junior"}' http://localhost:3000/api/chat/stream` → SSE stream con `meta` y `done` (o `{available:false}` si `LLM_FILTER_ENABLED=false`)

### T-006: Layout (root layout, providers, page, topbar, onboarding overlay, page entry)

**Type**: layout
**Scope**:
- **`src/app/providers.tsx`** (client component): wraps children con
  - `QueryClientProvider` de `@tanstack/react-query` (QueryClient con `staleTime: 60_000`, `refetchOnWindowFocus: false`)
  - `<Toaster />` de `sonner` con posición `top-right`
  - Custom `useReducedMotion` provider (lee `prefers-reduced-motion` y expone context)
  - `<TooltipProvider>` de shadcn
- **`src/app/layout.tsx`** (modify): root HTML con `${geistSans.variable} ${geistMono.variable}` aplicado al `<html>`, body con `font-sans antialiased`, `<Providers>` wrapping children
- **`src/app/page.tsx`** (server component): renderiza `<Topbar />`, luego un grid responsive (`<SearchSection />` 2/3 cols, `<ChatSection />` 1/3 col en desktop; stacked en mobile), `<OnboardingOverlay />` montado pero invisible si ya se vio
- **`src/components/layout/Topbar.tsx`** (client): app title "jobs-finder" a la izquierda, backend status indicator (green dot si `/api/health` 200, gray si 503, red si network error) a la derecha. Escucha `Ctrl+Shift+R` global y limpia `localStorage.onboarding_seen` (con `confirm()` prompt)
- **`src/components/layout/OnboardingOverlay.tsx`** (client): single screen con shadcn `Dialog`. Texto: *"Welcome to jobs-finder. Search across LinkedIn, Indeed, and InfoJobs in one place. Then chat with an AI assistant to refine your results by intent, location, or experience level."* Botón "Got it" cierra y setea `localStorage.onboarding_seen = "true"`. Se muestra si `localStorage.getItem("onboarding_seen") !== "true"` en mount. Usa `framer-motion` AnimatePresence.
- **`src/components/layout/PageEntry.tsx`** (client): wrapper que aplica `motion.div` con stagger animation a children (50ms entre topbar → search → results → chat). Respeta `useReducedMotion`.

**Files**:
- `frontend/src/app/layout.tsx` (modify — preserva el font setup de T-003)
- `frontend/src/app/providers.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/components/layout/Topbar.tsx`
- `frontend/src/components/layout/OnboardingOverlay.tsx`
- `frontend/src/components/layout/PageEntry.tsx`

**Acceptance**:
- `npm run dev` muestra layout con Geist font, topbar con título, backend indicator (green/gray/red)
- Onboarding aparece en primera visita (no `localStorage` key)
- Click "Got it" cierra y setea `localStorage.onboarding_seen = "true"`
- Refresh no muestra el overlay de nuevo
- `Ctrl+Shift+R` limpia el key (con confirm) y muestra el overlay
- Stagger animation: topbar → search → results → chat con 50ms delay
- `useReducedMotion` (DevTools "Emulate prefers-reduced-motion: reduce") desactiva las animaciones
- `npm run typecheck` + `npm run lint` + `npm run build` pasan

### T-007: Search components (SearchBar, ResultsGrid, JobCard, EmptyState, ErrorState, Skeletons, useDebouncedJobsSearch)

**Type**: search-ui
**Scope**:
- **`src/components/search/SearchBar.tsx`** (client): dos `<Input>` (keywords, location) + `<Button>` "Search". Controlled inputs. Enter o click → submit. Layout responsive: stack vertical en mobile, horizontal en desktop.
- **`src/components/search/ResultsGrid.tsx`** (client): grid 1 col mobile / 2 tablet / 3 desktop. Recibe `jobs: Job[]` por prop. Renderiza `<JobCard>` por job.
- **`src/components/search/JobCard.tsx`** (client): `<Card>` con title, company, location, **un `<Badge>` por cada `source` en `Job.sources`** (LinkedIn → bg-[#0A66C2], Indeed → bg-[#6B46C1], InfoJobs → bg-[#F97316]), posted time ("2 days ago" vía `formatRelativeTime`), `<a>` link a `Job.url` con `target="_blank" rel="noopener noreferrer"`. **NO botón "Copy link" en v1** (deferido). Hover: `motion.div` con `y: -4` + shadow.
- **`src/components/search/EmptyState.tsx`** (client): shadcn `<Empty>` con `<EmptyMedia variant="icon">` (search icon), headline "Find your next role", 3 chips: `["Senior Python Developer in Madrid", "Junior Frontend in Barcelona", "Data Engineer, remote"]`. Click en chip → setea los inputs y dispara search.
- **`src/components/search/ErrorState.tsx`** (client): shadcn `<Alert variant="destructive">` con error code, message, `request_id` (si está en el `ApiError`), botón "Retry" que llama `refetch()`.
- **`src/components/search/Skeletons.tsx`** (server-renderable): 6 `<Skeleton>` cards replicando la grid layout.
- **`src/hooks/useDebouncedJobsSearch.ts`** (client): wrap de `useQuery` con:
  - Query key: `["jobs", debouncedKeywords, debouncedLocation]`
  - 400ms debounce sobre los inputs (usa `useDebouncedValue`)
  - Default values: `{ keywords: "Software Engineer", location: "Madrid" }` (REQ-DQ-001)
  - `staleTime: 60_000`
  - `placeholderData: keepPreviousData`
  - Returns: `{ data, isLoading, isError, error, refetch }`

**Files**:
- `frontend/src/components/search/SearchBar.tsx`
- `frontend/src/components/search/ResultsGrid.tsx`
- `frontend/src/components/search/JobCard.tsx`
- `frontend/src/components/search/EmptyState.tsx`
- `frontend/src/components/search/ErrorState.tsx`
- `frontend/src/components/search/Skeletons.tsx`
- `frontend/src/hooks/useDebouncedJobsSearch.ts`

**Acceptance**:
- Typing en search input NO dispara requests en cada keystroke (debounce 400ms)
- Después de 400ms de inactividad, el request dispara
- Initial mount corre un search default ("Software Engineer" + "Madrid") SIN flash de empty state (data se considera "loading" → skeletons)
- Loading state muestra 6 skeletons
- Success muestra los results en el grid responsive
- Error muestra el `<Alert>` con retry
- Empty state aparece solo si el usuario limpia los inputs y vuelve a buscar sin resultados
- Click en chip dispara search con esos valores
- Hover en card lifte la card
- Source badges son color-coded correctamente
- `npm run typecheck` + `npm run lint` + `npm run build` pasan

### T-008: Chat components (ChatPanel, ChatMessage, ChatInput, ChatStreamBanner, NoChatAvailable, useChatStream)

**Type**: chat-ui
**Scope**:
- **`src/components/chat/ChatPanel.tsx`** (client): right-side panel en desktop, tab/bottom-sheet en mobile (`md:hidden` toggle). Wrapper con `glass` utility. Renderiza `<ChatStreamBanner>`, lista de `<ChatMessage>`, `<ChatInput>`.
- **`src/components/chat/ChatMessage.tsx`** (client): bubble. User: right-aligned, `bg-accent text-accent-foreground`. Assistant: left-aligned, `bg-card border border-border`. Typewriter effect con `framer-motion` cuando llegan chunks de text (respeta `useReducedMotion`).
- **`src/components/chat/ChatInput.tsx`** (client): `<textarea>` autosize + `<Button>` "Send". Enter → send, Shift+Enter → newline. Button disabled mientras `isStreaming`, muestra `<Spinner>`.
- **`src/components/chat/ChatStreamBanner.tsx`** (client): banner encima de los mensajes con el `meta` event (e.g. "Searching for: Madrid, junior, ..."). Animación de pulse con `motion.div`.
- **`src/components/chat/NoChatAvailable.tsx`** (client): mensaje amigable "Chat is not available right now. The search results above are still searchable." con icono de shadcn. Se muestra cuando `useChatStream` recibe `{available: false}`.
- **`src/hooks/useChatStream.ts`** (client): SSE consumer hook.
  - `useChatStream({ onMeta, onText, onDone, onError })` retorna `{ isStreaming, send, cancel }`
  - `send(message)`: `fetch('/api/chat/stream', { method: 'POST', body: JSON.stringify({ message }), signal })`. Lee `response.body` como `ReadableStream`, parsea SSE chunks (o el caso `{available:false}`), invoca callbacks.
  - `cancel()`: aborta el `AbortController`.

**Files**:
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/components/chat/ChatMessage.tsx`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ChatStreamBanner.tsx`
- `frontend/src/components/chat/NoChatAvailable.tsx`
- `frontend/src/hooks/useChatStream.ts`

**Acceptance**:
- Typear mensaje + Enter dispara el stream
- Texto aparece progresivamente (typewriter)
- Meta banner muestra el intent
- En `done`, el results grid es **reemplazado** con `done.jobs` (el subset filtrado) — esto se coordina con T-007 a través de un state compartido o query invalidation
- En `error`, `<Alert>` se muestra
- En 404 (LLM_FILTER_ENABLED=false), `NoChatAvailable` se muestra con texto amigable
- Send button disabled durante in-flight, muestra `<Spinner>`
- Mobile (≤768px): chat panel colapsa a un tab/sheet
- Tablet (768-1024px): side-by-side con chat más angosto
- Desktop (≥1024px): side-by-side con chat ancho completo
- `npm run typecheck` + `npm run lint` + `npm run build` pasan

### T-009: Unit tests (api, chat-stream-forwarder, useDebouncedValue) + vitest config

**Type**: tests
**Scope**:
- **`vitest.config.ts`**: `environment: "jsdom"`, alias `@ → ./src`, setup file `vitest.setup.ts` que importa `@testing-library/jest-dom`
- **`vitest.setup.ts`**: import `@testing-library/jest-dom`
- **`src/lib/__tests__/api.test.ts`** (≥ 5 tests):
  1. `ApiError` class tiene `status`, `code`, `requestId`, `retryAfter?`
  2. `mapBackendError(500, body, reqId)` → `ApiError` con `code: "internal_error"`
  3. `mapBackendError(429, body, reqId)` con `Retry-After` header → `ApiError` con `retryAfter`
  4. `mapBackendError(404, body, reqId)` → `ApiError` con `code: "not_found"`
  5. `mapBackendError(401/403, body, reqId)` → `ApiError` con `code: "unauthorized"` o `"forbidden"`
  6. Network failure (`fetch` throws) → `ApiError` con `code: "network_error"`
- **`src/lib/__tests__/chat-stream-forwarder.test.ts`** (≥ 4 tests):
  1. Forwarder parsea `meta` event y llama `onMeta` con el payload
  2. Forwarder parsea `text` events múltiples y concatena → llama `onText` incremental
  3. Forwarder parsea `done` event y llama `onDone` con `ChatDonePayload`
  4. Forwarder parsea `error` event y llama `onError` con el `ApiError`
  5. Forwarder aborta limpio cuando `controller.signal` se dispara
  6. Forwarder maneja `backendResponse.status === 404` → emite `onDone({available: false, reason: "llm_disabled"})` (defensivo, aunque el Route Handler ya lo mapea)
  - Test isolation: usa `new ReadableStream({ start(controller) { controller.enqueue(textEncoder.encode(...)) } })` para simular el backend
- **`src/hooks/__tests__/useDebouncedValue.test.ts`** (≥ 3 tests):
  1. Hook retorna el value inicial inmediatamente
  2. Después de `delayMs` ms, retorna el último value (no valores intermedios)
  3. Re-render con nuevo value antes del delay cancela el timer anterior

**Files**:
- `frontend/vitest.config.ts`
- `frontend/vitest.setup.ts`
- `frontend/src/lib/__tests__/api.test.ts`
- `frontend/src/lib/__tests__/chat-stream-forwarder.test.ts`
- `frontend/src/hooks/__tests__/useDebouncedValue.test.ts`

**Acceptance**:
- `npm run test` corre los 3 test files y pasan todos
- `npm run typecheck` pasa (tests son type-strict con `tsconfig` que incluye `src/**/__tests__/**`)
- `npm run build` sigue succeeding (tests no rompen el build — `vitest.config.ts` está fuera del `tsconfig` de Next, o tiene su propio `tsconfig`)
- `npm run lint` pasa
- Cobertura mínima de los 3 files in-scope es ~80% (no enforced, pero se verifica manualmente)

### T-010: Documentation (frontend/README.md, AGENTS.md update, .env.example)

**Type**: docs
**Scope**:
- **Reemplazar `frontend/README.md`** (placeholder actual) con un README real que cubra:
  - Stack: Next.js 15, React 19, TypeScript strict, Tailwind v4, shadcn/ui (base-nova), TanStack Query, framer-motion, sonner
  - Setup: `npm install`, `cp .env.example .env.local`
  - Scripts: `dev`, `build`, `start`, `lint`, `typecheck`, `test`
  - Project structure (árbol de `frontend/src/`)
  - Env vars: `BACKEND_URL` (server-only, default `http://localhost:8000`)
  - **"How to consume the backend API"**: nunca hablar directo al backend; siempre via Route Handlers en `src/app/api/`
  - **"Design system"**: tokens del aesthetic (light/dark, lavender accent, glass utility) y cómo usarlos
  - **"How to run a smoke test"**: pasos para verificar que el frontend habla con el backend (curl examples)
- **Actualizar `AGENTS.md` raíz**:
  - Workspaces table: `frontend/` → `Next.js 15 · React 19 · TypeScript · Tailwind v4 · shadcn/ui` · `frontend/package.json`
  - Agregar sección "Stack (frontend)" análoga a la del backend
  - Agregar `frontend/` a la sección "How to run" con los comandos npm
- **Verificar `frontend/.env.example`** (creado en T-001): documenta `BACKEND_URL=http://localhost:8000` con un comentario explicando que es server-only

**Files**:
- `frontend/README.md` (replace)
- `AGENTS.md` (modify)

**Acceptance**:
- `frontend/README.md` es non-empty y accurate (cubre las 8 secciones listadas)
- Root `AGENTS.md` documenta el frontend workspace (Workspaces table + Stack section + How to run)
- `frontend/.env.example` está accurate y documenta el server-only nature de `BACKEND_URL`
- `npm run build` sigue succeeding (los docs no afectan el build)

## Work unit ordering

```
T-001 (scaffold) ──┐
                    ├─→ T-002 (shadcn) ─→ T-003 (aesthetic tokens)
                    │                                  │
                    └──────────────────────────────────┴─→ T-004 (lib + hooks)
                                                                  │
                                                                  ├─→ T-005 (Route Handlers)
                                                                  │
                                                                  └─→ T-006 (layout/page)
                                                                              │
                                                                              ├─→ T-007 (search UI)
                                                                              │
                                                                              └─→ T-008 (chat UI)
                                                                                       │
                                                                                       └─→ T-009 (unit tests)
                                                                                                  │
                                                                                                  └─→ T-010 (docs)
```

**Reglas de dependencia**:
- T-001 + T-002 + T-003 deben completar **antes** de T-004 (lib/ necesita el proyecto, shadcn utils, y los tokens CSS resueltos)
- T-004 debe completar **antes** de T-005 + T-007 + T-008 (Route Handlers + componentes dependen de types + api + forwarder)
- T-006 debe completar **antes** de T-007 + T-008 (el page layout hostea las secciones de search y chat)
- T-007 y T-008 pueden hacerse en cualquier orden (T-008 también necesita T-006)
- T-009 debe correr **después** de T-004 (los tests prueban lib/chat-stream-forwarder.ts y hooks/useDebouncedValue.ts)
- T-010 es el último

**Commits sugeridos** (10 commits, 1 por task, conventional commits):
1. `chore(frontend): scaffold Next.js 15 with TypeScript strict and Tailwind v4`
2. `chore(frontend): init shadcn/ui with base-nova preset and 14 components`
3. `feat(frontend): add Soft/Modern Glass aesthetic tokens and Geist font`
4. `feat(frontend): add lib (types, api, backend, format, chat-stream-forwarder) and hooks`
5. `feat(frontend): add Route Handlers for /api/jobs, /api/chat/stream, /api/health`
6. `feat(frontend): add root layout, providers, page shell, topbar, onboarding overlay`
7. `feat(frontend): add search components and useDebouncedJobsSearch hook`
8. `feat(frontend): add chat components and useChatStream hook`
9. `test(frontend): add unit tests for api, chat-stream-forwarder, useDebouncedValue`
10. `docs(frontend): add README and update root AGENTS.md`

## PR slice recommendation

- **Strategy**: single PR (2980 LOC < 5000 review budget)
- **Commits**: 10 conventional commits, ~300 LOC avg
- **Review focus areas** (call out en el PR description):
  1. T-001–T-003 (scaffold): confirmar pinning, tokens, font
  2. T-004 (lib/): los **types son el contrato crítico** con el backend — leer con cuidado
  3. T-005 (Route Handlers): el 404→200 conversion y el SSE forwarding son la lógica no-trivial
  4. T-008 (chat): el `useChatStream` hook + typewriter son la UX más compleja

## Test policy (REQ-TEST-001, test-after para frontend v1)

- **Strict TDD**: NOT applied (frontend, Python-only en este proyecto)
- **In-scope tests** (T-009): 3 unit tests para funciones puras testables
- **Out-of-scope** (deferido a `frontend-test-coverage`): E2E tests, MSW para HTTP mocking, component tests para shadcn, visual regression
- **Verification gates por task**: `tsc --noEmit` + `next lint` + `next build` deben pasar **antes** de commitear

## Pre-apply checklist

- [x] Las 10 tasks tienen acceptance criteria claros
- [x] Dependency order documentado
- [x] Test policy claro (test-after, 3 unit tests in v1)
- [x] Single PR recommendation (2980 < 5000)
- [x] No code changes fuera de `frontend/` (excepto root `AGENTS.md` en T-010)
- [x] `frontend/.env.example` documenta `BACKEND_URL`
- [x] Tipos TS alineados con backend canónico (obs #316)
- [x] 404 → 200 conversion documentado (REQ-FALLBACK-001)
- [x] SSE forwarder como pure function (testable)
- [x] Aesthetic tokens (lavender, glass) en T-003
- [x] Default search query en T-007 (REQ-DQ-001)

## Risks

- **T-005 (Route Handlers)**: el smoke test con curl requiere que el backend esté corriendo en `:8000`. Si el backend no está up, los curl fallan — el sdd-apply agent debe documentar esto en el PR description pero no es bloqueante.
- **T-008 (chat)**: el typewriter effect con `framer-motion` puede tener jank en devices low-end. Mitigación: `useReducedMotion` desactiva la animación.
- **T-002 (shadcn add)**: el orden topológico de `npx shadcn add` puede fallar si una dep no está. El scope lista el orden 1-14 explícitamente para minimizar retries.
- **T-001 (create-next-app)**: el flag `--no-eslint` se usa porque `next lint` se prefiere; si create-next-app version mismatch, fallback a setup manual de `package.json`.
- **T-003 (dark mode)**: Tailwind v4 con `darkMode: "media"` requiere `@custom-variant dark` en CSS (no en `tailwind.config.ts`); el sdd-apply debe verificar qué versión de Tailwind instaló T-001.
