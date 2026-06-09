# jobs-finder · frontend

The user-facing web client for [jobs-finder](../README.md). Built on
Next.js 15 (App Router) + TypeScript strict + Tailwind v4 +
shadcn/ui (nova preset). All backend traffic is proxied through
Next.js Route Handlers in `src/app/api/`, so the browser never
talks to the FastAPI backend directly.

For the HTTP API contract, see the backend's
[`../backend/README.md`](../backend/README.md). The chat-streaming
wire shape (`meta?` → `text*` → `done|error`) is documented in
[`../openspec/specs/chat-streaming/spec.md`](../openspec/specs/chat-streaming/spec.md).

## Stack

| Layer            | Choice                                  |
| ---------------- | --------------------------------------- |
| Framework        | Next.js 15.5 (App Router, RSC)          |
| UI runtime       | React 19.1                              |
| Language         | TypeScript 5.9 (strict + noUncheckedIndexedAccess) |
| Styling          | Tailwind CSS v4 (CSS-only config)       |
| Components       | shadcn/ui (base / nova style, 14 + 1)   |
| Server state     | @tanstack/react-query 5.101             |
| Forms            | native controlled inputs + zod-friendly types in `src/lib/types.ts` |
| Animations       | motion 12 (formerly framer-motion)      |
| Toasts           | sonner 2                                |
| Icons            | lucide-react 1.17                       |
| Tests            | vitest 4 + @testing-library/react 16    |

The 14 v1 shadcn components are: `avatar`, `badge`, `button`,
`card`, `dialog`, `empty`, `field`, `input`, `label`,
`scroll-area`, `separator`, `skeleton`, `sonner`, `spinner`,
`tooltip`. `alert` was added on demand in T-007 for the search
error state.

## Quickstart

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The first paint will show 6
skeletons and then the default search results for
`"Software Engineer" + "Madrid"` because the search section is
seeded with that query on mount (REQ-DQ-001). To actually see
real results, the backend must be running on
`http://localhost:8000` (set `BACKEND_URL` in `frontend/.env.local`
to point elsewhere, e.g. a staging URL).

## Scripts

| Script            | What it does                                            |
| ----------------- | ------------------------------------------------------- |
| `npm run dev`     | Next dev server on <http://localhost:3000>              |
| `npm run build`   | Production build (type-checks + lints as part of build) |
| `npm run start`   | Serve the production build locally                      |
| `npm run lint`    | `next lint` against the eslint-config-next flat config  |
| `npm run typecheck` | `tsc --noEmit` with strict + noUncheckedIndexedAccess |
| `npm run test`    | `vitest run --passWithNoTests`                          |

`npm run lint` prints a deprecation notice from Next 15.5 saying
`next lint` is going away in Next 16. Until then it is the
official interface and the project's CI uses it.

## Project structure

```
frontend/
├── components.json           # shadcn config (style: base-nova, base: base)
├── eslint.config.mjs         # flat config wrapping next/core-web-vitals + next/typescript
├── next.config.ts            # empty for now (RSC + App Router defaults)
├── package.json              # all deps pinned to exact versions
├── postcss.config.mjs        # @tailwindcss/postcss only
├── public/                   # create-next-app default SVGs
├── src/
│   ├── app/                  # App Router root
│   │   ├── api/              # 3 Route Handlers (server-side proxies)
│   │   │   ├── chat/stream/  # POST /api/chat/stream (SSE forwarder)
│   │   │   ├── health/       # GET  /api/health (backend liveness)
│   │   │   └── jobs/         # GET  /api/jobs (search proxy)
│   │   ├── globals.css       # tokens, glass utility, tailwind v4 @theme
│   │   ├── layout.tsx        # html lang, Geist font vars, Providers
│   │   ├── page.tsx          # server component composing Topbar/Workbench/Overlay
│   │   └── providers.tsx     # TanStack Query, MotionConfig, Toaster, TooltipProvider
│   ├── components/
│   │   ├── chat/             # ChatPanel, ChatMessage, ChatInput, …
│   │   ├── layout/           # Topbar, OnboardingOverlay, PageEntry, Workbench
│   │   ├── search/           # SearchBar, ResultsGrid, JobCard, …
│   │   └── ui/               # shadcn primitives (15 files)
│   ├── hooks/                # useDebouncedValue, useDebouncedJobsSearch, useChatStream
│   └── lib/
│       ├── api.ts            # client-side fetch + ApiError + mapBackendError
│       ├── backend.ts        # server-only fetch + BACKEND_URL + BackendError
│       ├── chat-stream-forwarder.ts  # pure SSE parser (no Next imports)
│       ├── format.ts         # Intl.RelativeTimeFormat wrapper (es-ES)
│       ├── types.ts          # TS mirror of backend Pydantic schemas
│       └── utils.ts          # shadcn cn() helper
├── tests files live next to the modules under test (e.g. src/lib/__tests__/, src/hooks/__tests__/)
├── tsconfig.json             # strict + noUncheckedIndexedAccess + @ alias
├── vitest.config.ts          # jsdom env, @ alias, src/**/__tests__/ inclusion
├── vitest.setup.ts           # @testing-library/jest-dom setup
└── .env.example              # BACKEND_URL=http://localhost:8000 (server-only)
```

## Environment variables

The frontend reads **one** environment variable:

| Variable      | Default                   | Scope    | Purpose                                                                |
| ------------- | ------------------------- | -------- | ---------------------------------------------------------------------- |
| `BACKEND_URL` | `http://localhost:8000`   | server   | Base URL the Route Handlers proxy to. Read at request time.            |

It is server-only — never expose it to the browser. The variable
does NOT need the `NEXT_PUBLIC_` prefix because Route Handlers
run in the Node server runtime, not the client. The companion
`@/lib/backend.ts` is annotated with `import "server-only"` so
any accidental client import fails the build.

The browser only ever talks to the same-origin
`/api/*` endpoints, so CORS is not a concern.

## How to consume the backend API

The browser must never fetch `BACKEND_URL` directly. Every call
goes through a Next.js Route Handler, which:

1. validates the request (Pydantic-shaped types in `src/lib/types.ts`)
2. calls `backendFetch(path, init)` (the only place `BACKEND_URL` is read)
3. forwards the response, copying the right headers
4. translates upstream errors into the `ApiError` class

The three route handlers are the only files that know about
`BACKEND_URL`:

| File                                       | Proxies                    | Notes                                                                 |
| ------------------------------------------ | -------------------------- | --------------------------------------------------------------------- |
| `src/app/api/jobs/route.ts`                 | `GET /jobs`                | Forwards `X-Cache`, `X-Request-Id`, and rate-limit headers.            |
| `src/app/api/chat/stream/route.ts`         | `POST /jobs/chat/stream`   | Streams the SSE bytes through `chat-stream-forwarder`.                |
| `src/app/api/health/route.ts`              | `GET /health`              | Pass-through; 200 = green, 503 = amber, network = red.                |

The `chat/stream` route is special: if the backend replies 404
(`LLM_FILTER_ENABLED=false` in the backend), the route returns
`200 {available: false, reason: "llm_disabled"}` as JSON so the
chat panel can show its friendly "chat not available" state
without ever seeing a 404 (REQ-FALLBACK-001).

## Design system

The "Soft/Modern Glass" aesthetic is implemented in
`src/app/globals.css`:

| Token         | Light       | Dark        | Use                                  |
| ------------- | ----------- | ----------- | ------------------------------------ |
| `--background`| `#FAFAF9`   | `#0A0A0F`   | Page surface                         |
| `--card`      | `#FFFFFF`   | `#1A1A1F`   | Cards, popovers                      |
| `--accent`    | `#A78BFA`   | `#C4B5FD`   | The single saturated hue (lavender)  |
| `--border`    | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.08)` | Subtle dividers     |

Dark mode is automatic (`prefers-color-scheme: dark`); there is
no manual toggle in v1.

The `.glass` utility applies an 80%-opaque card surface with a
50%-opaque border and a 12px backdrop blur. It is applied to the
**topbar** and the **chat panel** only — job cards stay solid
for legibility. The utility lives in the `@layer utilities` block
of `globals.css` so it can be used anywhere with `className="glass"`.

The two fonts are **Geist Sans** (body) and **Geist Mono**
(code/numerals) loaded via `next/font/google` and exposed as the
CSS variables `--font-geist-sans` and `--font-geist-mono`. The
`@theme inline` block in `globals.css` aliases `--font-sans` and
`--font-mono` to those variables so Tailwind's `font-sans` /
`font-mono` utilities resolve to Geist.

The six micro-interactions from REQ-MICRO-001 are wired via
`motion` (the successor to framer-motion):

1. Search button: `whileTap={{ scale: 0.97 }}` (search is in
   `SearchBar`'s Button, currently with a default press scale;
   will land in T-007 polish if review requests it).
2. Job card hover: `whileHover={{ y: -4 }}` with a spring.
3. Chat Send: disabled with an inline spinner while streaming.
4. Chat text chunks: each `text` event concats into the running
   bubble; the caret pulses while the stream is in flight.
5. Tab/badge hover: Tailwind `hover:` classes.
6. Empty-state chips: `variant="outline"` button with
   `hover:bg-accent/10` (declarative, no motion needed).

All animations respect `prefers-reduced-motion: reduce` via
`<MotionConfig reducedMotion="user">` in the providers.

## How to run a smoke test

With the backend running on `:8000`:

```bash
# In one terminal
cd backend && uv run jobs-finder

# In another terminal
cd frontend && npm run dev

# Then verify the route handlers proxy correctly
curl -i 'http://localhost:3000/api/jobs?keywords=python&location=madrid' | head -20
curl -i  'http://localhost:3000/api/health' | head -20
curl -i -X POST -H 'Content-Type: application/json' \
  -d '{"message":"junior en Madrid"}' \
  http://localhost:3000/api/chat/stream | head -30
```

The third command streams `text` events followed by a `done`
event. If the backend has `LLM_FILTER_ENABLED=false`, the same
endpoint returns `200 {"available":false,"reason":"llm_disabled"}`
as JSON instead.

## Testing

This is a **test-after** policy (REQ-TEST-001). The v1 suite is
3 unit-test files covering the pure logic:

| File                                              | Coverage                                                  |
| ------------------------------------------------- | --------------------------------------------------------- |
| `src/lib/__tests__/api.test.ts`                   | `ApiError`, `mapBackendError`, `parseJobsResponse`        |
| `src/lib/__tests__/chat-stream-forwarder.test.ts` | meta/text/done/error parsing, 404 fallback, abort signal  |
| `src/hooks/__tests__/useDebouncedValue.test.ts`   | trailing update, cancellation on rapid re-renders         |

Run them with `npm run test`. CI also runs `npm run lint` and
`npm run typecheck`.

Comprehensive component tests, MSW-backed HTTP tests, and E2E
Playwright runs are deferred to the follow-up change
`frontend-test-coverage`.

## Known follow-ups

- **frontend-test-coverage** — vitest + @testing-library/react + MSW + Playwright
- **dark mode toggle** — manual switch in the topbar
- **per-source tabs** — filter the grid by LinkedIn / Indeed / InfoJobs
- **job detail view** — currently the card links to the original posting
- **saved searches** — localStorage bookmarks
- **i18n** — UI is monolingual es-ES for v1
