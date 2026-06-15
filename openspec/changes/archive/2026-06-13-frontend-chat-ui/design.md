# Design: Frontend Chat UI

## Technical Approach

Add a FAB + shadcn Dialog chat widget to all pages. A `useChat` hook drives SSE streaming via a Next.js Route Handler proxy. Pure React state — no React Query, no global store, no localStorage. Each tab mount = fresh session, cleanup aborts the fetch.

## Architecture Decisions

### FAB in AppShell
| Option | Tradeoff | Decision |
|--------|----------|----------|
| Mount in layout.tsx | Burdens root, breaks clean separation | ❌ |
| Mount in AppShell | Single point, children unaffected | ✅ **fixed bottom-6 right-6 z-50** |
| Separate floating component | More indirection, same result | ❌ |

### Dialog wraps ChatPanel
`ChatDialog` (FAB + `Dialog` + `ChatPanel`) is the atomic unit. `DialogContent` gets `className="sm:max-w-[500px] h-[600px]"` — wide enough for job results.

### SSE Proxy via Route Handler
| Option | Tradeoff | Decision |
|--------|----------|----------|
| Direct browser-to-backend fetch | Exposes `BACKEND_URL`, CORS issues, violates existing CONVENTION-12 | ❌ |
| Route Handler passthrough | Follows existing `/api/jobs` pattern, zero CORS | ✅ **POST /api/jobs/chat/stream** |

The handler forwards `POST` body + `Content-Type` header, streams the backend response body through `new Response(backendRes.body, headers)`.

### SSE Client: fetch + ReadableStream, NOT EventSource
| Option | Tradeoff | Decision |
|--------|----------|----------|
| EventSource | GET-only, no request body | ❌ |
| fetch POST + ReadableStream reader | Works with POST, full control | ✅ |

Manual parser: read chunks, split on `\n\n`, parse `event:` and `data:` lines. Skip lines starting with `: ` (keepalive).

### State: Pure React, no React Query
| Option | Tradeoff | Decision |
|--------|----------|----------|
| React Query mutation | Overkill for streaming, abort pattern awkward | ❌ |
| useState + useRef | Simple, abort-friendly, per-tab isolated | ✅ |

## Data Flow

```
User types → ChatInput → useChat.sendMessage()
  → useState adds UserMessage
  → AbortController created, stored in ref
  → fetch(POST /api/jobs/chat/stream, { signal, body })
  → Route Handler proxies to POST /jobs/chat/stream
  → Backend emits SSE events
  → Route Handler streams raw bytes through Response.body
  → useChat reads ReadableStream
  → SSE parser yields events
  → meta → no UI change
  → text {delta} → appends to assistant message content (typewriter)
  → done {jobs, explanation} → sets final state, jobs array
  → error {code, message} → sets error state
  → stream ends → status = "done"
```

```
AppShell
 └── ChatDialog (state: open/close)
      ├── FAB button
      └── Dialog
           └── ChatPanel
                ├── ChatMessages
                │    ├── UserMessage   {role: "user", content}
                │    └── AssistantMessage {role: "assistant", content, jobs}
                ├── ChatInput
                └── ChatLoading (during "streaming")
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/app/api/jobs/chat/stream/route.ts` | Create | SSE proxy Route Handler |
| `frontend/src/types/chat.ts` | Create | UserMessage, AssistantMessage, SSEEvent types |
| `frontend/src/hooks/useChat.ts` | Create | SSE streaming hook (pure state) |
| `frontend/src/components/chat/ChatDialog.tsx` | Create | FAB + Dialog + ChatPanel wrapper |
| `frontend/src/components/chat/ChatPanel.tsx` | Create | Container: messages + input + status |
| `frontend/src/components/chat/ChatMessages.tsx` | Create | Message list with ScrollArea |
| `frontend/src/components/chat/ChatInput.tsx` | Create | Textarea + Send button |
| `frontend/src/components/chat/AssistantMessage.tsx` | Create | Typewriter text + job results inline |
| `frontend/src/components/layout/AppShell.tsx` | Modify | Add `<ChatDialog />` before closing `<div>` |

## Interfaces / Contracts

```typescript
// types/chat.ts
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  jobs?: Job[];
  explanation?: string;
  error?: { code: string; message: string };
}

export interface SSEEventMeta {
  stage: number;
  intent?: Record<string, unknown>;
}

export interface SSEEventText {
  delta: string;
}

export interface SSEEventDone {
  jobs: Job[];
  explanation: string;
  total_considered: number;
  total_matched: number;
  used_fallback: boolean;
}

export interface SSEEventError {
  code: string;
  message: string;
}

// useChat hook return
interface UseChatReturn {
  messages: ChatMessage[];
  status: "idle" | "connecting" | "streaming" | "done" | "error";
  sendMessage: (text: string) => void;
  reset: () => void;
}
```

### Error Mapping (backend machine code → user-facing message)

| Code | User Message |
|------|-------------|
| `llm_unavailable` | "The AI assistant is currently unavailable. Please try again later." |
| `llm_stream` | "Connection interrupted while processing your request." |
| `llm_parse` | "The AI response couldn't be interpreted. Please rephrase." |
| `llm_timeout` | "The request timed out. Try a simpler query." |
| `stage1_parse` | "Couldn't understand that. Try being more specific." |
| `internal` | "Something went wrong. Please try again." |

### Route Handler SSE passthrough

```typescript
// route.ts — core pattern
export async function POST(request: NextRequest) {
  const backendRes = await fetch(
    `${BACKEND_URL}/jobs/chat/stream`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: await request.text() },
  );
  return new Response(backendRes.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
  });
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | SSE parser (event extraction, keepalive skip, error parse) | vitest with mock ReadableStream |
| Unit | useChat hook (send, stream tokens, abort, error) | vitest + fake fetch + AbortController |
| Unit | Error mapping (all 6 codes) | vitest table test |
| Integration | Route Handler proxy (mock backend, verify passthrough headers) | vitest with mocked fetch |
| E2E | FAB open dialog → send message → see results | Playwright (future) |

## Migration / Rollout

No migration required. The FAB is gated by backend `LLM_FILTER_ENABLED=true` — the Route Handler will return 502 if the backend endpoint is unreachable, and the error is surfaced as an inline error bubble. No feature flags needed on the frontend.

## Open Questions

- [ ] Should we add a tooltip or pulse animation on first-visit to hint the FAB?
