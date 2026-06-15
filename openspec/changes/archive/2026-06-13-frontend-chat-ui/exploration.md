## Exploration: Frontend Chat UI

### Current State

#### Backend — Fully ready
- **`POST /jobs/chat/stream`** (SSE) streams 3 event types: `meta` (2-stage intent), `text` × N (LLM tokens), `done` (final job results + explanation).
- **`POST /jobs/chat`** (v1 request/response) available as non-streaming fallback.
- **`FilterJobsByIntentUseCase`** with `execute()` and `stream_execute()`.
- **`MiniMaxLLMClient`** (OpenAI-compatible), `ChatRateLimitMiddleware`, conditional activation via `LLM_FILTER_ENABLED=true`.
- **Request/response schemas**: `ChatRequest{message}`, `ChatResponse{jobs, explanation, total_considered, total_matched, used_fallback}`.
- **SSE error mapping**: 6 machine codes (`llm_unavailable`, `llm_stream`, `llm_parse`, `llm_timeout`, `internal`, `stage1_parse`).

#### Frontend — No chat infra at all
- **Architecture pattern**: `Browser → Route Handler → Backend` is MANDATORY. The browser never calls `BACKEND_URL` directly.
- **Route Handlers**: `/api/jobs/route.ts` (GET proxy), `/api/jobs/[id]/route.ts` (GET by ID), `/api/health/route.ts` (GET). All server-only via `import "server-only"` in `api-client.ts`.
- **Data fetching**: React Query hooks (`useJobs`, `useJobsInfinite`, `useJobDetail`). Each hook calls `fetch(/api/…)` on the client. Server-side proxying via `lib/api-client.ts` using `BACKEND_URL` env var.
- **Component patterns**: Loading → `skeleton-shimmer` CSS class, Empty → `EmptyState` (4 variants: `no-results`, `no-jobs`, `error`, `empty`), Error → `ErrorState` with optional retry. Framer Motion spring animations (bounce: 0.1, duration: 0.4).
- **UI components** (shadcn): `dialog`, `scroll-area`, `button`, `input`, `badge`, `card`, `skeleton`, `separator`, `tooltip`, `avatar`.
- **Layout**: `AppShell` (Sidebar + Header + main) wraps all pages via `RootLayout`. Sidebar has 4 nav items: Dashboard, Jobs, Search, Settings.
- **Types**: `job.ts` (Job, HistoryResponse), `settings.ts` (PlatformConfig), `stats.ts` (DashboardStats). No chat types exist.
- **No React Query for streaming** — all existing hooks use `useQuery`/`useInfiniteQuery` for request/response. SSE streaming doesn't fit React Query's fetch-on-mount pattern (chat is event-driven, user-initiated).

### Affected Areas

| File | Action | Why |
|---|---|---|
| `frontend/src/app/api/jobs/chat/stream/route.ts` | **CREATE** | New Route Handler to proxy SSE POST to backend |
| `frontend/src/types/chat.ts` | **CREATE** | Chat message types, SSE event types, stream state |
| `frontend/src/hooks/useChat.ts` | **CREATE** | SSE streaming hook: connect, parse events, manage state |
| `frontend/src/components/chat/ChatPanel.tsx` | **CREATE** | Main chat container: message list + input |
| `frontend/src/components/chat/ChatMessages.tsx` | **CREATE** | Message bubbles with typewriter animation |
| `frontend/src/components/chat/ChatInput.tsx` | **CREATE** | Text input + send button, disabled during streaming |
| `frontend/src/components/chat/ChatToggle.tsx` | **CREATE** | Floating toggle button (FAB) OR sidebar nav item |
| `frontend/src/components/layout/Sidebar.tsx` | **MODIFY** | Add chat nav item (if dedicated page) |
| `frontend/src/components/layout/AppShell.tsx` | **MODIFY** | Add floating chat button (if widget approach) |
| `frontend/src/lib/formatters.ts` | **MODIFY** | Minor: no changes needed |
| `frontend/src/lib/api-client.ts` | **NO CHANGE** | SSE proxying happens in Route Handler, no new client-side lib needed |
| `openspec/changes/frontend-chat-ui/` | persists | All SDD artifacts |

### Approaches

#### Approach A: Floating Chat Widget (FAB + Dialog/Sheet)
A floating action button in the bottom-right corner (like Intercom). Clicking it opens a dialog/sheet that contains the chat panel. Rendered once in `AppShell` so it's available on every page.

- **Pros**:
  - Always accessible from any page — search jobs, then chat to filter without navigating
  - Per-tab by default (React state inside the dialog component, fresh on mount)
  - Does NOT require a new sidebar nav item
  - Lightweight integration — AppShell is the only cross-cutting change
  - Dialog uses existing shadcn `Dialog` component
- **Cons**:
  - Chat history disappears when dialog closes (unless preserved in component state — but AppShell keeps it mounted, just hidden)
  - Less screen real estate (dialog is ~600px wide by default)
  - Could overlap page content (mitigated by closing on interaction outside)
- **Effort**: Low (4 new components + 1 hook + 1 route handler + 1 type file)

#### Approach B: Dedicated Chat Page (`/chat`)
A full-page chat experience at `/chat`, accessible from the sidebar navigation.

- **Pros**:
  - Maximum screen space for chat + results
  - Natural fit for the sidebar navigation pattern (add one more nav item)
  - Chat stays visible as long as user stays on the page
  - Can show matched job results inline next to chat
- **Cons**:
  - Requires navigation away from current context (can't chat while browsing jobs)
  - Requires modifying `Sidebar.tsx` to add nav item
  - Full page reload means losing chat state on navigation (acceptable — per-tab)
  - Over-engineered for what is essentially a job filter tool
- **Effort**: Medium (same as A + new route page + Sidebar modification)

#### Approach C: Hybrid — Floating Widget on Dashboard, Dedicated Page for Full Chat
Both: a floating widget for quick queries from anywhere AND a `/chat` page for the full experience.

- **Pros**:
  - Best of both worlds
  - Natural onboarding: widget introduces the feature, page power-users it
- **Cons**:
  - Two implementations to maintain
  - Chat state isn't shared between them (per-tab means each mount is independent anyway)
  - Confusing UX (which one to use?)
  - Unnecessary complexity
- **Effort**: High

#### SSE vs Request/Response

| Criterion | SSE Streaming | Request/Response (v1) |
|---|---|---|
| **Typewriter effect** | ✅ Built-in (`text` events) | ❌ No streaming, 5-8s blank screen |
| **Backend state** | ✅ Already implemented | ✅ Already implemented |
| **Route Handler complexity** | Medium (proxies ReadableStream) | Low (JSON body, JSON response) |
| **Client complexity** | Low (ReadableStream + SSE parser) | Trivial (single fetch + await) |
| **Error handling** | 6 machine codes via SSE events | HTTP status codes + JSON body |
| **Abort on escape** | ✅ `AbortController` works | ✅ `AbortController` works |
| **Recommendation** | ✅ **PREFERRED** | Fallback for edge cases only |

#### Component Architecture

**Panel architecture**:
```
ChatPanel (container)
├── ChatMessages (scrollable message list)
│   └── ChatMessage (per-message bubble)
│       └── TypewriterText (animated token reveal)
└── ChatInput (textarea + send button + status indicator)
```

**State management** (no React Query — per-tab isolation):
```typescript
// In useChat hook:
- messages: ChatMessage[]    — local useState
- status: "idle" | "streaming" | "done" | "error"
- abortController: AbortController | null
- streamEvents: ReadableStream<Uint8Array> parsing via async iterator
```

**SSE Parsing strategy**: Use `fetch` + `response.body.getReader()` to read the stream as UTF-8 chunks, parse `event:` / `data:` lines manually (no EventSource — POST-only). A lightweight `parseSSEChunk(text)` utility handles the line-based protocol.

### Recommendation

**Approach A (Floating Chat Widget) + SSE streaming** is the recommended approach. Here's why:

1. **The chat feature is fundamentally a JOB FILTER TOOL**, not a standalone communication app. Users should be able to search jobs, see results, and then say "find me remote React jobs" without navigating to a different page.
2. **Per-tab isolation is FREE** with in-component React state. No global state, no localStorage, no React Query cache — just `useState` + `useRef` inside the panel component.
3. **Lowest effort** — 1 Route Handler, 1 hook, 4 components, 1 type file, 1 modification to AppShell. No new page, no sidebar changes.
4. **FSM pattern for state**: idle → streaming → done or error. Simple, testable, debuggable.
5. **The dialog approach** uses the existing shadcn `Dialog` component (already in the project). The FAB uses a `button` with `fixed bottom-6 right-6` positioning.
6. **Chat messages persist while dialog is open** (React Query not involved — pure local state). Closing and reopening gives a fresh session (per-tab ✅).

The only modification to existing code is adding the FAB + Dialog to `AppShell.tsx`. Everything else is new files.

### Key Design Decisions

1. **Route Handler returns SSE directly** — `new Response(backendResponse.body, { headers: SSE_HEADERS })`. The Route Handler is a transparent TCP proxy for the SSE stream. This avoids buffering the entire response in memory.
2. **No React Query for chat** — React Query is optimized for request/response caching. Chat is a user-initiated, event-driven stream. Using raw `fetch` + ReadableStream is simpler and guarantees per-tab isolation.
3. **SSE parsing is manual** — `EventSource` only works with GET requests. Since we POST to `/api/jobs/chat/stream`, we use `fetch` POST + `response.body.getReader()` + a simple line-based SSE parser.
4. **AbortController for cancellation** — If the user presses Escape or sends a new message while streaming, we abort the previous request via `AbortController`. The backend handles the disconnect gracefully.
5. **Matched jobs flow** — The `done` event carries the full job list. The chat panel shows a "Show matched jobs" button that navigates to `/jobs` with the matched job IDs, OR we could show a compact job list inline below the chat. The latter is more user-friendly.

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **SSE proxying breaks in Next.js** (Route Handler may buffer or transform the stream) | Medium | Test with real backend. If `Response(backend.body)` doesn't work, use a `TransformStream` with `pipeline`. Fallback: use `WebStreamsPolyfill`. |
| **Keepalive comments confuse SSE parser** | Low | The parser must handle lines starting with `: ` (SSE comments) by skipping them. Covered in spec REQ-SSE-002. |
| **Large job results in `done` event cause message parsing delay** | Low | The `done` event is terminal — parsing happens once. The delay is O(n) on job count and imperceptible. |
| **Memory leak from AbortController** | Low | Use `useEffect` cleanup to abort on unmount. Standard React pattern. |
| **Client disconnect doesn't cancel backend LLM** | Very Low | Already accepted by backend spec: "cost is negligible; complexity not worth it." |
| **FAB overlaps page content** | Low | Use `z-50` (dialog overlay level) and `bottom-6 right-6`. The dialog's overlay prevents interaction with page content while open. |
| **Message exceeds backend char limit** | Low | Show inline validation error before sending. Backend returns 400 with descriptive `detail`. |

### Ready for Proposal
**Yes** — the exploration is complete. The orchestrator should propose **Approach A** (Floating Chat Widget with SSE streaming). The implementation effort is **Low-Medium** (~6 new files + 1 modification).

Key points for the proposal:
- 1 new Route Handler: `frontend/src/app/api/jobs/chat/stream/route.ts`
- 1 new hook: `frontend/src/hooks/useChat.ts`
- 4 new components: `ChatPanel`, `ChatMessages`, `ChatInput`, `ChatToggle` under `frontend/src/components/chat/`
- 1 new type file: `frontend/src/types/chat.ts`
- Modify `AppShell.tsx` to include the FAB + Dialog
- SSE streaming from the start (typewriter effect)
- No React Query — pure React state for per-tab isolation
- Matched jobs shown inline in the chat dialog with "View details" links
