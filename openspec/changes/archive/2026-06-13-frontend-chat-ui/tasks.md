# Tasks: Frontend Chat UI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~800 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-always |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

## Phase 1: Foundation

- [x] 1.1 Create `frontend/src/types/chat.ts` — ChatMessage union, SSEEvent types, error mapping table
- [x] 1.2 Create `frontend/src/app/api/jobs/chat/stream/route.ts` — SSE proxy forwarding POST body + Content-Type, raw Response.body passthrough, X-Accel-Buffering: no
- [x] 1.3 Create `frontend/src/hooks/useChat.ts` — SSE parser (skip `: ` keepalive), AbortController, typewriter token state, error recovery

## Phase 2: UI Components

- [x] 2.1 Create `frontend/src/components/chat/ChatDialog.tsx` — FAB (bottom-6 right-6 z-50) + shadcn Dialog (sm:max-w-[500px] h-[600px])
- [x] 2.2 Create `frontend/src/components/chat/ChatPanel.tsx` — ScrollArea + status bar + wiring between Messages, Input, and useChat
- [x] 2.3 Create `frontend/src/components/chat/ChatMessages.tsx` — message list with user/assistant bubbles, typing indicator during streaming
- [x] 2.4 Create `frontend/src/components/chat/AssistantMessage.tsx` — typewriter token reveal + job results as /jobs/{id} links
- [x] 2.5 Create `frontend/src/components/chat/ChatInput.tsx` — textarea + send button, disabled during streaming, Enter to submit

## Phase 3: Integration

- [x] 3.1 Modify `frontend/src/components/layout/AppShell.tsx` — import and render `<ChatDialog />` before closing div

## Phase 4: Tests

- [x] 4.1 Write SSE parser unit tests: keepalive skip, event extraction, error parsing
- [x] 4.2 Write useChat hook tests: send message, stream tokens, abort mid-stream, error recovery
- [x] 4.3 Write error mapping table tests: all 6 backend error codes
- [x] 4.4 Write Route Handler proxy test: mock backend, verify passthrough headers and status

## Phase 5: Verification

- [x] 5.1 Run `npm run typecheck` and fix type errors
- [x] 5.2 Run `npm run lint` and fix lint violations
- [x] 5.3 Run `npm run test` (existing baseline + new tests)
- [x] 5.4 Run `npm run build` for production build
