# Proposal: Frontend Chat UI

## Intent

Users can't filter jobs in natural language. The backend already has LLM-powered chat endpoints (`POST /jobs/chat/stream` + `POST /jobs/chat`). The frontend needs a lightweight chat widget so users describe what they want and see matching jobs — without navigating away from their current page.

## Scope

### In Scope
- Floating Action Button (FAB) available on all pages, opens shadcn Dialog with chat panel
- SSE streaming proxy Route Handler (`/api/jobs/chat/stream`)
- Per-tab chat state (useState + useRef, no global store)
- Typewriter token animation in message bubbles
- Error handling: SSE parse errors, network failures, LLM error codes from backend

### Out of Scope
- Full conversation history / dedicated `/chat` page
- Multi-turn refinement or follow-up queries
- Saved chats, localStorage persistence
- Cross-tab sync

## Capabilities

### New Capabilities
- `chat-frontend`: Browser-based chat widget that connects to the existing backend SSE streaming API. Message input, typewriter token reveal, final job results display. Per-tab isolated, no global state.

### Modified Capabilities
None — the backend `chat-streaming` capability is unchanged. This change adds a frontend consumer only.

## Approach

FAB fixed `bottom-6 right-6` (`z-50`) → onClick opens shadcn `Dialog` → `ChatPanel` renders `ChatMessages` (scrollable via `ScrollArea`) + `ChatInput`. SSE proxied through a Next.js Route Handler (`/api/jobs/chat/stream`) using `fetch` + `ReadableStream` reader. The `useChat` hook manages: messages array, connection state, AbortController for cancellation. Typewriter reveal via incremental text state on each `text` event. Error events surface as inline error bubbles in the message list.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/app/api/jobs/chat/stream/route.ts` | New | Route Handler SSE proxy |
| `frontend/src/types/chat.ts` | New | Chat types |
| `frontend/src/hooks/useChat.ts` | New | SSE streaming hook |
| `frontend/src/components/chat/ChatPanel.tsx` | New | Main container |
| `frontend/src/components/chat/ChatMessages.tsx` | New | Message list |
| `frontend/src/components/chat/ChatInput.tsx` | New | Input bar |
| `frontend/src/components/layout/AppShell.tsx` | Modified | Mount FAB + Dialog |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Next.js buffers SSE response | Medium | Passthrough `X-Accel-Buffering: no`; TransformStream fallback |
| Keepalive SSE comments confuse parser | Low | Parser skips lines starting with `: ` |
| FAB overlaps page content | Low | `z-50`, dialog overlay blocks interaction while open |

## Rollback Plan

Revert `AppShell.tsx` to remove FAB mount. Delete `frontend/src/app/api/jobs/chat/stream/route.ts`, `frontend/src/types/chat.ts`, `frontend/src/hooks/useChat.ts`, and `frontend/src/components/chat/`. No DB or config schema changes — pure frontend addition.

## Dependencies

- Backend `POST /jobs/chat/stream` enabled (`LLM_FILTER_ENABLED=true` in `backend/.env`)

## Success Criteria

- [ ] FAB visible on all pages, opens chat dialog on click
- [ ] User sends query → SSE stream shows typewriter tokens → final job results render
- [ ] Each browser tab has independent chat state
- [ ] `npm run typecheck` passes
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] `npm run test` passes (existing 56+ tests)
