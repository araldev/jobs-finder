# Design: frontend-scaffold

> Cambia la estética del producto, no la verdad del backend.
> Los tipos TS son espejo 1:1 de los Pydantic schemas actuales. Donde el
> spec del frontend divergía del backend, el diseño se alinea con el
> backend canónico (ver "Deviations from the spec" al final).

## Architecture overview

Tres capas: **Browser (cliente)** → **Next.js server (Route Handlers)** →
**FastAPI backend (localhost:8000 en dev)**. El browser NUNCA habla
directo al backend; todo el tráfico pasa por Route Handlers
server-side (REQ-ENV-001). El server lee `BACKEND_URL` desde
`process.env`; el cliente no tiene acceso a esa variable (es
server-only, sin prefijo `NEXT_PUBLIC_`).

```text
┌─────────────────────────────────────────────────────────────┐
│ Browser (Client Components)                                  │
│                                                              │
│  SearchBar  ──debounce 400ms──┐                              │
│                               │                              │
│  ChatInput  ──Enter / click──┐│                              │
│                              ▼▼                              │
│                    useDebouncedJobsSearch                    │
│                    useChatStream (SSE consumer)              │
│                              │                               │
│                              ▼                               │
│   /api/jobs?keywords=...&location=...    (GET, JSON)        │
│   /api/chat/stream  (POST, body: {message})                  │
│   /api/health  (GET, JSON) — optional topbar indicator       │
└──────────────────────────────┬──────────────────────────────┘
                               │ same-origin fetch
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Next.js Server (Node runtime)                                │
│                                                              │
│  src/app/api/jobs/route.ts        ── GET ──► BACKEND_URL/jobs│
│  src/app/api/chat/stream/route.ts ── POST ──► BACKEND_URL/  │
│                                              jobs/chat/stream│
│  src/app/api/health/route.ts      ── GET ──► BACKEND_URL/    │
│                                              health          │
│                                                              │
│  Each Route Handler:                                         │
│   1. validates input (zod, light)                            │
│   2. fetch(BACKEND_URL + path, { headers: {Accept,...}})     │
│   3. for SSE: pipe readable stream event-by-event            │
│   4. forwards X-Request-Id, X-Cache, X-RateLimit-* headers   │
│   5. maps backend 4xx/5xx to typed ApiError (only for        │
│      non-SSE handlers; SSE keeps the 200 + error event)      │
│                                                              │
│  env: process.env.BACKEND_URL (default http://localhost:8000)│
└──────────────────────────────┬──────────────────────────────┘
                               │ server-to-server, no CORS
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI Backend                                              │
│                                                              │
│  GET  /jobs            AggregatedJobsResponse                 │
│  POST /jobs/chat/stream   SSE: meta → text* → done|error    │
│  GET  /health         {"status": "ok"}                       │
│  (5 v1 endpoints also exist; frontend does NOT consume them)│
└──────────────────────────────────────────────────────────────┘
```

### Data flow — search (JSON)

```text
1. User types in SearchBar
2. useDebouncedJobsSearch waits 400ms after last keystroke
3. react-query useQuery fires GET /api/jobs?keywords=…&location=…&limit=20
4. Route Handler validates query (zod) and reads process.env.BACKEND_URL
5. Route Handler does fetch(BACKEND_URL + "/jobs" + qs)
6. Backend returns AggregatedJobsResponse { jobs: [...] } + headers
   (X-Cache, X-Request-Id, X-RateLimit-Remaining, X-Aggregator-Sources,
    X-Aggregator-Errors when partial failure)
7. Route Handler returns Response with the same body + selected headers
8. react-query caches the response by query key
9. ResultsGrid re-renders
```

### Data flow — chat (SSE)

```text
1. User types in ChatInput and presses Enter
2. useChatStream does fetch("/api/chat/stream", {
     method: "POST",
     body: JSON.stringify({message: "..."}),
   })  — no EventSource because POST + body
3. Route Handler validates body (zod), reads process.env.BACKEND_URL
4. Route Handler does fetch(BACKEND_URL + "/jobs/chat/stream", {
     method: "POST", body: {message}, signal: abortSignal
   })
5. Backend SSE stream arrives (Content-Type: text/event-stream)
6. Route Handler pipes the stream: for each chunk it parses SSE
   frames, validates the event name (meta | text | done | error),
   and re-emits them with the same shape (event: <name>\ndata: …\n\n)
   plus the cache headers (Cache-Control: no-cache, etc.)
7. On backend disconnect mid-stream → Route Handler emits
   event: error\ndata: {"code":"stream_interrupted",…}\n\n and closes
8. On backend 404 (LLM_FILTER_ENABLED=false) → Route Handler returns
   200 {available: false, reason: "llm_disabled"} (REQ-FALLBACK-001)
9. Browser's useChatStream reads the stream chunk by chunk and
   dispatches: meta → ChatStreamBanner; text → append to last
   assistant message (motion fade-in per chunk); done → replace the
   ResultsGrid with done.jobs; error → Alert with code+message
```

## Component changes

Para cada componente: ruta → propósito en 1 línea → props shape →
comportamientos clave. shadcn primitives referenciados entre
llaves; motion entre paréntesis angulares. Detalles de implementación
(animaciones, a11y, edge cases) viven inline en cada bloque.

### Layout

- **`src/app/layout.tsx`** — root layout. Carga Geist + Geist_Mono via
  `next/font/google`, aplica CSS vars en `<html>`, monta `<Providers>`.
  Pinta skip-link (REQ-A11Y-001). `<body>` usa `bg-background
  text-foreground font-sans`. Sin ThemeProvider; dark mode via
  `prefers-color-scheme` en `globals.css`.
- **`src/app/page.tsx`** — main page (server component). Renderiza
  `<Topbar>` + `<SearchPage>` (client) en grid responsive
  (REQ-RESPONSIVE-001). Mobile: stack vertical con `<Tabs>` para
  Results/Chat. `md+`: grid 2-col (60/40 en tablet, 65/35 en `lg+`).
- **`src/app/providers.tsx`** — client wrapper para `QueryClientProvider`
  (react-query) + `<Toaster richColors>` (sonner). El QueryClient se
  crea con `staleTime: 30_000` por default.
- **`src/components/layout/Topbar.tsx`** — `backdrop-blur-md bg-card/70
  border-b`. Logo wordmark izquierda, `HealthDot` derecha, botón
  "Reiniciar onboarding" con `<Tooltip>`. Props:
  `{ health: { ok: boolean } | null, onResetOnboarding: () => void }`.
- **`src/components/layout/OnboardingOverlay.tsx`** — `<Dialog>` con
  `aria-modal="true"`, single screen. Lee/escribe
  `localStorage["jobs-finder:onboarding-v1"]` en `useEffect`
  (SSR-safe). Atajo oculto `Ctrl+Shift+R` limpia la clave.

### Search

- **`src/components/search/SearchBar.tsx`** — `useForm` + zod
  (`{keywords: 1..200, location: 1..200, limit: 1..100}`). Render:
  dos `<Input>` con label visible + `<Button type="submit">` con
  `<motion.button whileTap={{ scale: 0.97 }}>`. Submit actualiza
  useState lifted en la page. A11y: `<label htmlFor>`,
  `aria-describedby` al error.
- **`src/components/search/ResultsGrid.tsx`** — container grid
  `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`. Switch por
  `status` de react-query: pending→`<Skeletons>`, error→
  `<ErrorState>`, empty→`<EmptyState>`, success→map `<JobCard>`.
- **`src/components/search/JobCard.tsx`** — shadcn `<Card>`
  `rounded-2xl shadow-sm`. Header: title + `<Badge>` por cada
  `source` (LinkedIn `#0A66C2` / Indeed `#2164F4` / InfoJobs
  `#FF7F32`). Body: company + location (`MapPin` icon) +
  `posted_at` formateado por `formatRelativeTime`. Footer: link
  externo `target="_blank" rel="noopener" ArrowUpRight`. Props:
  `{ job: AggregatedJob }`. Puro (sin state/effects).
  `<motion.div whileHover={{ y: -2, scale: 1.01 }} transition={{ duration: 0.2 }}>`.
- **`src/components/search/EmptyState.tsx`** — shadcn `<Empty>`.
  Dos variantes: "no-results" (con copy de "no encontramos" + botón
  "Limpiar filtros") y "first-visit" (3 chips clickeables que
  escriben en el SearchBar).
- **`src/components/search/ErrorState.tsx`** — shadcn `<Alert>`
  variant="destructive". 502/503 copy + botón "Reintentar"
  (invalidate query). 429 incluye `retryAfter`. Cualquier error
  preserva `request_id` en `<details>`.
- **`src/components/search/Skeletons.tsx`** — 6 `<Skeleton>` con
  shape de JobCard. `animate-pulse` built-in.
- **`src/hooks/useDebouncedJobsSearch.ts`** — wrap de `useQuery`
  con debounce 400ms (custom `useDebouncedValue`). Query key
  `["jobs", keywords, location, limit, sources]`. `staleTime: 30s`,
  `placeholderData: keepPreviousData`, `enabled: keywords &&
  location` post-debounce. En `select` expone
  `{ jobs, cacheStatus, requestId }` (headers via `apiFetch`).

### Chat

- **`src/components/chat/ChatPanel.tsx`** — container
  `aria-live="polite" role="log"`. Glass SOLO en el panel
  (`backdrop-blur-md bg-card/80 border-border/50 rounded-2xl`).
  Header con título + botón "Limpiar". Body: `<ScrollArea>` con
  lista de `<ChatMessage>`. Empty: `<EmptyState>` con 3 chips de
  refinamiento. Footer: `<ChatInput>`. Si `chatAvailable === false`:
  `<Alert>` no-bloqueante + `<Tooltip>` con how-to-fix. Mobile: full
  width sin glass. Props: `{ messages, onSend, status,
  chatAvailable, onClear }`.
- **`src/components/chat/ChatMessage.tsx`** — burbuja por message.
  User: `bg-primary rounded-2xl rounded-tr-sm`. Assistant:
  `bg-muted rounded-2xl rounded-tl-sm`. Avatar opcional izquierda
  (Bot icon). Si `error` definido: `<Alert>` interno con
  `code + message`. Motion: cada chunk = `<motion.span initial=
  {{opacity:0}} animate={{opacity:1}} transition={{duration:0.1}}>`
  (REQ-MICRO-001d).
- **`src/components/chat/ChatInput.tsx`** — `<form onSubmit>` +
  `<Input>` + `<Button>`. `disabled` mientras streaming; muestra
  `<Spinner>` en vez del icono `Send`. Enter envía, Shift+Enter
  newline. A11y: `<label className="sr-only">`. Props:
  `{ onSend, disabled }`.
- **`src/components/chat/ChatStreamBanner.tsx`** — banner cuando
  llega `event: meta`. Copy: "Buscando: {intent_text ?? formatted}".
  `<motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}>`.
- **`src/hooks/useChatStream.ts`** — `fetch + ReadableStream` (no
  `EventSource`, necesitamos POST). State: `{ status, messages,
  currentText, error, meta, chatAvailable }`. Parsea stream manual
  con `parseSSEChunk`, mantiene buffer entre reads, dispatcha por
  event. Acepta `onDone(jobs)` callback que el padre usa para
  reemplazar el results data. Cleanup: `AbortController.abort()` en
  unmount.

### Infrastructure

- **`src/lib/api.ts`** — `class ApiError { code, message, status,
  requestId }`. `mapResponseError(res, requestId): ApiError` mapea
  401/403/404/429/5xx → mensajes ES. `apiFetch<T>(path, init):
  Promise<{ data: T, headers: Headers }>` wrapper thin. NO toca
  SSE.
- **`src/lib/types.ts`** — espejo 1:1 de los Pydantic schemas (ver
  bloque dedicado más abajo).
- **`src/lib/utils.ts`** — `cn` (re-export shadcn),
  `formatRelativeTime(iso | null)` (`Intl.RelativeTimeFormat("es")`),
  `parseSSEChunk(chunk): Array<{event, data}>` (puro, test-able).
- **`src/lib/backend.ts`** — `BACKEND_URL = process.env.BACKEND_URL
  ?? "http://localhost:8000"`. `backendFetch(path, init)` server-only.
  `forwardHeaders(res, source)` copia `X-Request-Id`, `X-Cache`,
  `X-RateLimit-*`, `X-Aggregator-Sources`, `X-Aggregator-Errors`.
- **`src/lib/chat-stream-forwarder.ts`** — `parseSSEChunk` (puro) +
  `buildForwarderStream(upstreamBody, signal): ReadableStream`
  (test-able). Es el core no-trivial del Route Handler — exportado
  para que el test unit lo cubra sin tocar Next.js runtime.
- **`src/app/api/jobs/route.ts`** — `export async function GET(req)`:
  zod-validates query, `backendFetch("/jobs?" + qs)`, forward body +
  headers. 4xx/5xx: forward as-is. Sin unit test (lógica de 8 líneas).
- **`src/app/api/chat/stream/route.ts`** — `export async function
  POST(req)`: zod-validates `{message}`, `backendFetch("/jobs/chat/
  stream", POST, body, signal)`. Si 404 upstream: 200
  `{available:false, reason:"llm_disabled"}` (REQ-FALLBACK-001). Si
  SSE: pipeline via `buildForwarderStream`; upstream cut → emit
  `event: error\ndata: {"code":"stream_interrupted",…}\n\n`. Headers
  SSE: `text/event-stream`, `no-cache`, `keep-alive`,
  `X-Accel-Buffering: no`. **Unit-tested** via
  `src/lib/chat-stream-forwarder.ts`.
- **`src/app/api/health/route.ts`** — `export async function GET()`:
  `backendFetch("/health")` con timeout 2s; ok → 200
  `{status:"ok", backend:true}`, fail → 200
  `{status:"degraded", backend:false}` (nunca 5xx — es indicator
  visual, no debe romper el page render).

## Data flow

El ASCII del inicio cubre el wire-level. Los steps numerados abajo
documentan **decisiones de diseño por step** (no son un trace de
debugging — el trace es el ASCII).

### Search — decisiones por step

| Step | Decisión | Por qué |
|---|---|---|
| 1 | `react-hook-form` para validación declarativa (zod resolver) | El backend ya tiene constraints 1..200; duplicarlas en el cliente da UX inmediata (no espera al 422) |
| 2 | Debounce custom (`useDebouncedValue`) en lugar de `use-debounce` | Un dep menos; la lógica es 5 líneas; testeable sin DOM |
| 5 | Route Handler NO agrega `X-Forwarded-For` en v1 (no hay rate limit per-IP) | El rate limit del backend es per-API-key, no per-IP (REQ-RL-001). Reservar el header para cuando el rate limit crezca |
| 7 | Forward `X-Cache`, `X-Request-Id`, `X-Aggregator-Sources`, `X-Aggregator-Errors` | El cliente puede mostrar "Mostrando resultados cacheados" en dev; el `request_id` se preserva para soporte (REQ-ERROR-001) |
| 8 | `staleTime: 30s` (no `0`) | El backend ya cachea 60s; el cliente evita re-firing innecesario en navegación back/forward |

### Chat — decisiones por step

| Step | Decisión | Por qué |
|---|---|---|
| 2 | El hook agrega el user message al state ANTES de hacer fetch | UX: el usuario ve su mensaje aparecer instantáneamente (REQ-CHAT-001 2do scenario: el botón Send muestra spinner) |
| 3 | `fetch` (no `EventSource`) | EventSource es GET-only; el endpoint es POST. Usamos `ReadableStream` manual para parsear SSE |
| 6 | El forwarder emite events VERBATIM (`event: name\ndata: json\n\n`) | El cliente no necesita lógica de re-mapping; confianza 1:1 con el backend canónico |
| 7 | El cliente mantiene un `buffer: string` entre reads (SSE puede partir un evento entre 2 chunks) | El protocolo SSE no garantiza frame boundaries; buffering es necesario |
| 8d | El `done` event REEMPLAZA el grid del search (no agrega) | REQ-CHAT-001 4to scenario: el chat refina, no acumula. El botón "Limpiar filtro" del chat restaura el último search state |
| 9 | `AbortController.abort()` en unmount O cuando el usuario cierra el panel | Evita un LLM call que sigue corriendo en el server si el usuario navega away |

## API integration (firm-level)

| Route Handler | Method | Backend target | Body in | Body out |
|---|---|---|---|---|
| `/api/jobs` | GET | `GET /jobs?keywords&location&limit&sources&use_fallback` | — | `AggregatedJobsResponse` + headers |
| `/api/chat/stream` | POST | `POST /jobs/chat/stream` | `{message: string}` | SSE stream OR `{available:false, reason}` |
| `/api/health` | GET | `GET /health` | — | `{status, backend}` |

`use_fallback` es un query param que el Route Handler puede traducir
a la lógica del backend si en el futuro el aggregator expone un modo
"usar la cache TTL sin importar freshness". En v1 se forwarda tal
cual al backend (que actualmente lo ignora) — el param está reservado.

## TypeScript types (espejo del backend canónico)

`src/lib/types.ts`:

```typescript
// Source names. Mirror of AGGREGATOR_SOURCES in
// backend/src/jobs_finder/presentation/schemas.py.
export type Source = "linkedin" | "indeed" | "infojobs"

// AggregatedJob: one job in the /jobs response.
// Mirror of AggregatedJobResponse. Note: the field is `url` (Pydantic
// HttpUrl → JSON string), NOT `link`. The frontend spec called it
// `link` but the backend schema is `url` — we follow the backend.
export interface AggregatedJob {
  id: string
  title: string
  company: string
  location: string
  url: string
  description: string | null
  posted_at: string | null  // ISO-8601, may be null
  sources: Source[]         // always >= 1, source-priority order
}

// AggregatedJobsResponse: the body of GET /jobs.
// Total/cache_status are NOT in the body — they live in the response
// headers (X-Cache, X-Aggregator-Sources, X-Aggregator-Errors).
export interface AggregatedJobsResponse {
  jobs: AggregatedJob[]
}

// Intent (stage-1 extractor output, mirrored from application/ports.py).
// Only used to type the parsed 'meta' event payload.
export interface Intent {
  q: string | null
  location: string | null
  experience_years: number | null
  remote: boolean | null
  employment_type: "full_time" | "part_time" | "contract" | "internship" | "freelance" | null
  confidence: number  // [0.0, 1.0]
  notes: string | null
}

// SSE event payloads (mirror of ChatStreamMetaEvent, ChatStreamTextEvent,
// ChatStreamDoneEvent from backend/src/jobs_finder/presentation/schemas.py).
export interface ChatStreamMetaPayload {
  intent: Intent
}
export interface ChatStreamTextPayload {
  delta: string
}
export interface ChatStreamDonePayload {
  jobs: AggregatedJob[]
  explanation: string
  total_considered: number
  total_matched: number
  used_fallback: boolean
  request_id: string
}
export interface ChatStreamErrorPayload {
  code: "llm_unavailable" | "llm_stream" | "llm_parse" | "llm_timeout"
       | "stage1_parse" | "internal" | "stream_interrupted"
  message: string
}

// Discriminated union for SSE events (client-side).
export type ChatStreamEvent =
  | { type: "meta"; data: ChatStreamMetaPayload }
  | { type: "text"; data: ChatStreamTextPayload }
  | { type: "done"; data: ChatStreamDonePayload }
  | { type: "error"; data: ChatStreamErrorPayload }

// Typed error for non-SSE paths (api.ts).
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public override readonly message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

// Discriminated union for the /api/chat/stream first response.
// When the backend 404s (LLM disabled), the Route Handler returns
// 200 with this shape — the client never sees a 404.
export type ChatAvailabilityResponse =
  | { available: true }
  | { available: false; reason: "llm_disabled" | "backend_unreachable" }
```

## Test strategy (test-after selectivo, REQ-TEST-001)

| Layer | What | How |
|---|---|---|
| Static | strict TS | `npm run typecheck` = `tsc --noEmit`. Required in CI. |
| Static | ESLint | `npm run lint`. shadcn's default config + Next.js. |
| Build | Next.js build | `npm run build`. Catch SSR/RSC errors. |
| Unit | `api.ts` error mapping | `src/lib/__tests__/api.test.ts`. Mock `fetch` global; 8 cases (200, 401, 403, 404, 429+Retry-After, 5xx, network, JSON parse). |
| Unit | `parseSSEChunk` + forwarder | `src/lib/__tests__/chat-stream-forwarder.test.ts`. Pure: input string → output frames. Cases: single event, multi-line data, partial chunk, unknown event name, re-emit verbatim. |
| Unit | `useDebouncedValue` | `src/hooks/__tests__/useDebouncedValue.test.ts` (vitest + `@testing-library/react`). Edge: 0ms delay, equal value, rapid changes. |
| Manual | UI states | Documented in `frontend/README.md` → "How to verify". 3 viewports (375/768/1280), 6 micro-interactions, onboarding re-flow, empty/error/loading states. |
| E2E | (deferred) | Follow-up change `frontend-test-coverage` adds vitest + @testing-library + MSW + Playwright. |

vitest setup: `vitest.config.ts` con `environment: "node"` para
`api.test.ts` y `chat-stream-forwarder.test.ts` (no necesitan DOM), y
`environment: "jsdom"` solo para el hook test. Coverage de los tests
unitarios vive en `src/**/__tests__/*.test.ts` (per-file colocated).

## File-by-file change list (LOC forecast ~2980)

| File | Action | LOC |
|---|---|---|
| `frontend/package.json` | Create | 60 |
| `frontend/tsconfig.json` | Create | 40 |
| `frontend/next.config.ts` | Create | 30 |
| `frontend/tailwind.config.ts` (v4 uses CSS-first) | (n/a) | 0 |
| `frontend/postcss.config.mjs` | Create | 10 |
| `frontend/components.json` (shadcn) | Create | 30 |
| `frontend/.env.example` | Create | 10 |
| `frontend/.gitignore` | Create | 30 |
| `frontend/src/app/globals.css` | Create | 150 (CSS vars + glass utilities) |
| `frontend/src/app/layout.tsx` | Create | 50 |
| `frontend/src/app/page.tsx` | Create | 30 |
| `frontend/src/app/providers.tsx` (react-query + sonner) | Create | 50 |
| `frontend/src/app/api/jobs/route.ts` | Create | 50 |
| `frontend/src/app/api/chat/stream/route.ts` | Create | 130 |
| `frontend/src/app/api/health/route.ts` | Create | 30 |
| `frontend/src/components/layout/Topbar.tsx` | Create | 100 |
| `frontend/src/components/layout/OnboardingOverlay.tsx` | Create | 120 |
| `frontend/src/components/search/SearchBar.tsx` | Create | 140 |
| `frontend/src/components/search/ResultsGrid.tsx` | Create | 100 |
| `frontend/src/components/search/JobCard.tsx` | Create | 120 |
| `frontend/src/components/search/EmptyState.tsx` | Create | 110 |
| `frontend/src/components/search/ErrorState.tsx` | Create | 90 |
| `frontend/src/components/search/Skeletons.tsx` | Create | 40 |
| `frontend/src/components/chat/ChatPanel.tsx` | Create | 160 |
| `frontend/src/components/chat/ChatMessage.tsx` | Create | 110 |
| `frontend/src/components/chat/ChatInput.tsx` | Create | 90 |
| `frontend/src/components/chat/ChatStreamBanner.tsx` | Create | 50 |
| `frontend/src/hooks/useDebouncedJobsSearch.ts` | Create | 130 |
| `frontend/src/hooks/useDebouncedValue.ts` | Create | 30 |
| `frontend/src/hooks/useChatStream.ts` | Create | 180 |
| `frontend/src/lib/api.ts` | Create | 110 |
| `frontend/src/lib/types.ts` | Create | 120 |
| `frontend/src/lib/utils.ts` (cn + formatRelativeTime + parseSSEChunk) | Create | 90 |
| `frontend/src/lib/backend.ts` (server-only) | Create | 60 |
| `frontend/src/lib/chat-stream-forwarder.ts` (pure, test-able) | Create | 100 |
| `frontend/src/lib/__tests__/api.test.ts` | Create | 100 |
| `frontend/src/lib/__tests__/chat-stream-forwarder.test.ts` | Create | 150 |
| `frontend/src/hooks/__tests__/useDebouncedValue.test.ts` | Create | 60 |
| `frontend/vitest.config.ts` | Create | 30 |
| `frontend/README.md` (reemplazo) | Modify | 200 |
| `AGENTS.md` (raíz) | Modify | +30 (sección Workspaces) |
| **TOTAL** | | **~2980 LOC** |

## Aesthetic design details (REQ-AESTHETIC-001)

- **Accent color**: lavanda `#A78BFA` (primary). Justificación: 2026
  trend, gender-neutral, contrasta limpiamente con los badges de
  LinkedIn blue / Indeed purple-ish / InfoJobs orange (los tres son
  saturated, lavanda es un mid-tone pastel que no compite). Peach
  `#FDA4AF` es el fallback si lavanda se siente "frío" en user testing.
- **Light mode "bone white"**: `#FAFAF9` (`--background`). NO pure
  `#FFFFFF` — el off-white es parte del "soft" de la estética.
- **Dark mode "ink"**: `#0A0A0F` (`--background`). Casi-negro, no
  jet-black — el off-tone evita el contraste agresivo.
- **Card surfaces**: light `#FFFFFF` @ 80% opacity en glass contexts,
  100% en results grid (los cards sólidos se LEEN mejor).
- **Border radius**: `rounded-2xl` (cards, panels), `rounded-full`
  (buttons, badges), `rounded-lg` (inputs, alerts).
- **Shadows**: `shadow-sm` (cards), `shadow-lg` (chat panel = elevated
  above results), `shadow-xl` (modal/onboarding overlay).
- **Glassmorphism recipe** (aplicado SOLO en topbar + chat panel):
  - `backdrop-blur-md` (12px)
  - `bg-card/80` (light: rgba(255,255,255,.8); dark: rgba(26,26,31,.8))
  - `border border-border/50`
  - Los `JobCard` en el results grid son `bg-card` sólido (no glass)
    para legibilidad de texto
- **Motion** (motion v12 + `useReducedMotion`):
  - Page entry: stagger children 50ms (Topbar → SearchBar → ResultsGrid
    → ChatPanel), `initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}`.
  - JobCard hover: `whileHover={{ y: -2, scale: 1.01 }} transition={{ duration: 0.2 }}`.
  - Chat text chunks: cada delta = nuevo `<motion.span>` con
    `initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.1 }}`.
  - Send button: `whileTap={{ scale: 0.97 }}`.
  - Empty state chips: `whileHover={{ scale: 1.02 }}`.
  - Onboarding overlay: `initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}`
    con `AnimatePresence`.
  - `useReducedMotion()` global: cuando `true`, todas las animaciones
    se vuelven `duration: 0` (CSS transitions), preservando solo los
    state changes.

## Open questions

No bloquean el tasks phase. El user puede ajustar durante review del
design sin reabrir el spec. Las defaults listadas abajo son las que
usaría el apply phase si el user no objeta.

- **Accent color**: lavanda `#A78BFA` (alt: peach `#FDA4AF`).
- **Bone white**: `#FAFAF9` (alt: `#F5F5F4`).
- **Default search on mount**: `keywords="Software Engineer"`,
  `location="Madrid"`, `limit=20` (confirmado por el spec).
- **Empty chips (search)**: "Senior Python en Madrid", "Junior Frontend
  en Barcelona", "Data Engineer, remoto".
- **Empty chips (chat)**: "Solo puestos junior", "En remoto",
  "Mencionan RSU o equity".
- **Onboarding copy**: "Busca en 3 fuentes a la vez. Refina con chat."
- **shadcn components en v1**: 14 (button, input, card, badge, skeleton,
  empty, field, input-group, scroll-area, separator, tooltip, sonner,
  spinner, dialog). El spec lista 20; defer el resto on-demand
  (`npx shadcn add <name>` cuando se necesiten).
- **"Copy job link" en JobCard**: defer (+30 LOC scope creep).
- **`use_fallback` query param**: forwarda as-is al backend (actualmente
  lo ignora; reservado para futuro).

## Deviations from the proposal / spec

Estas son las decisiones del design que difieren del spec de
`frontend-scaffold/spec.md` o del launch prompt original. Cada
desviación está justificada con evidencia del backend canónico.

1. **`url` field, not `link`.** El spec del frontend (REQ-SEARCH-001 +
   REQ-API-001) describe el campo como `link`. El backend canónico
   (`JobResponse.url`, `AggregatedJobResponse.url` en
   `backend/src/jobs_finder/presentation/schemas.py`) usa `url`. La
   spec archivada `chat-streaming` también lo confirma (el `done`
   event lleva `JobResponse` objects). El design usa `url` para
   evitar una traducción redundante en cada `JobCard`.
2. **`sources: string[]`, not `string`.** El spec del frontend
   (REQ-SEARCH-001) menciona "Badge con el source (LinkedIn / Indeed /
   InfoJobs) color-coded" como un único source, pero el backend
   aggregator (`AggregatedJobResponse.sources: list[_SourceName]`)
   retorna un array — un job puede aparecer en N sources. El JobCard
   renderiza un Badge por cada source (max 3, wrap en flex).
3. **`/jobs` body has no `total` or `cache_status` fields.** El launch
   prompt del orchestrator y un primer borrador del spec asumían
   `JobListResponse { jobs, total, request_id, cache_status }`. El
   backend canónico (`aggregator.py` + `schemas.py`) emite SOLO
   `{ jobs: [...] }` en el body; `total` y `cache_status` viven en
   los headers (`X-Cache`, `X-Aggregator-Sources`). El design
   refleja esto: el body type es `AggregatedJobsResponse { jobs }`,
   y los headers se exponen en `apiFetch`'s return type.
4. **`done` event shape: `jobs: AggregatedJob[]`, not
   `matching_ids: string[]`.** El launch prompt describía el done
   como `{matching_ids, explanation, request_id, cache_status}`. El
   spec archivado `chat-streaming` REQ-SSE-001 3er scenario +
   REQ-PARSE-001 confirman el shape canónico: `{jobs, explanation,
   total_considered, total_matched, used_fallback, request_id}`.
   El `done` event lleva el array completo de jobs (no IDs), así
   que el frontend reemplaza el grid directamente. Esta desviación
   está explícitamente flagged en el spec del frontend como
   "discrepancia menor en el launch prompt" — el design resuelve
   alineando con el backend canónico.
5. **`description: string | null`, not `string`.** El spec del
   frontend omite `description`. El backend canónico
   (`JobResponse.description: str | None`) lo incluye. El design
   lo agrega al type (REQ-API-001) y NO lo renderiza en el card en
   v1 (sería scope creep mostrar descripción completa en el card).
   Reservado para un follow-up "Job detail view".
6. **`posted_at` is `string | null`, not required `string`.** El
   domain object `Job.posted_at` es required `datetime`, pero el
   Pydantic schema `JobResponse.posted_at: datetime | None` lo
   permite null. El frontend lo trata como nullable.
7. **HTTP 404 from `/api/chat/stream` becomes 200 with
   `{available:false}`.** El spec (REQ-FALLBACK-001 5to scenario)
   lo pide explícitamente: "el Route Handler MUST traducir el 404
   del backend a una respuesta estructurada (ej. `200 { available:
   false, reason: "llm_disabled" }`)". El design implementa
   exactamente esto en `/api/chat/stream/route.ts`.
8. **Onboarding = single screen, not 2 steps.** El spec dice
   "1-2 pantallas, dismissible" pero también "no hay step 2
   obligatorio en v1; el overlay es una sola pantalla". El design
   shippea single screen (más simple, suficiente para v1).
9. **`EventSource` is NOT used.** El spec no lo nombra, pero el
   launch prompt mencionó EventSource como opción. EventSource
   soporta solo GET (sin body), pero el endpoint del backend es
   `POST /jobs/chat/stream {message}`. El design usa `fetch +
   ReadableStream` + AbortController para poder hacer POST. Esta
   decisión está implícita en el data flow.
10. **No MSW / Playwright / vitest-browser en v1.** El spec
    (`REQ-TEST-001`) lo confirma: cobertura completa es
    follow-up `frontend-test-coverage`. El design agrega SOLO los
    3 unit tests listed en la test strategy.
11. **shadcn components reducidos de 20 a 14.** El spec (REQ-SHADCN-001)
    lista 20 componentes. El design shippea los 14 usados
    activamente en v1; el resto se agrega on-demand con
    `npx shadcn add <name>` cuando se necesiten en un follow-up.
    Justificación: menos surface area para mantener, menos bytes en
    `node_modules`/`src/components/ui/`, y shadcn's whole point es
    "add when needed, not upfront".

---

**Next step**: ready for `sdd-tasks` (10 tasks suggested: T-001 scaffold
+ types+utils, T-002 shadcn init, T-003 aesthetic tokens, T-004 lib
files, T-005 Route Handlers, T-006 layout, T-007 search components,
T-008 chat components, T-009 unit tests, T-010 README + AGENTS.md).
