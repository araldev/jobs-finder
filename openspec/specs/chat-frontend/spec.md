# Chat Frontend Specification

**Change**: `frontend-chat-ui` • **Mode**: `hybrid` • **Type**: New capability

> No existing spec at `openspec/specs/chat-frontend/spec.md`. This is a NEW full
> spec for the floating chat widget frontend. On archive it will be promoted to
> `openspec/specs/chat-frontend/spec.md`.

## Purpose

The chat-frontend capability adds a floating chat widget that lets users describe
job requirements in natural language and receive matching jobs via SSE streaming
from the backend `POST /jobs/chat/stream` endpoint.

## Requirements

### REQ-FAB-001: FAB Presence and Dialog

The system MUST render a floating action button (FAB) fixed at the bottom-right
(bottom-6 right-6) of every authenticated page. The FAB MUST use z-50 stacking
context. Clicking the FAB MUST open a shadcn Dialog containing the chat panel.

#### Scenario: Open chat from FAB

- GIVEN the user is on any page
- WHEN the user clicks the FAB
- THEN a shadcn Dialog opens with the chat panel visible

#### Scenario: FAB stacking context

- GIVEN a page with overlapping content
- WHEN the FAB renders
- THEN it is positioned bottom-6 right-6 with z-50

### REQ-SSE-PROXY-001: SSE Proxy Route Handler

The system SHALL provide a Next.js Route Handler at `POST /api/jobs/chat/stream`
that proxies to `POST {BACKEND_URL}/jobs/chat/stream`. The handler MUST forward
SSE response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, `X-Accel-Buffering: no`. The SSE parser MUST skip
keepalive comment lines starting with `: `.

#### Scenario: Successful SSE proxy

- GIVEN the backend is available
- WHEN a POST request arrives at `/api/jobs/chat/stream`
- THEN the handler proxies transparently with the same request body
- AND the response forwards the four SSE headers

#### Scenario: Backend error passthrough

- GIVEN the backend returns non-2xx
- WHEN the proxy receives the error
- THEN the same status code is returned to the client

#### Scenario: Skip keepalive comments

- GIVEN the SSE stream contains `: ` lines
- WHEN the parser reads them
- THEN those lines are silently skipped

### REQ-CHAT-ISO-001: Per-Tab Chat Isolation

The system MUST use local React state (useState, useRef) for chat state. It MUST
NOT use React Query caching, localStorage, cookies, or global stores. Each mount
SHALL produce a fresh session with no persisted state.

#### Scenario: Fresh session on mount

- GIVEN the user opens the chat dialog
- WHEN the panel mounts
- THEN the message list is empty
- AND no state from previous sessions is loaded

#### Scenario: Tab isolation

- GIVEN two browser tabs with the chat open
- WHEN the user sends a message in tab A
- THEN tab B's chat state is unaffected

### REQ-STREAM-UI-001: Streaming Message Display

The system MUST render assistant responses token-by-token as SSE `text` events
arrive. It SHALL handle three SSE event types: `meta` (show intent briefly),
`text` (append token to assistant message), `done` (show job results). A typing
indicator MUST be visible during streaming and hidden on completion or error.

#### Scenario: Full streaming flow

- GIVEN the user sends a valid query
- WHEN SSE events arrive
- THEN a `meta` event briefly shows the search intent
- AND each `text` event appends a token to the assistant bubble
- AND the typing indicator is visible during streaming
- AND the `done` event shows job results and hides the indicator

#### Scenario: Zero results

- GIVEN the `done` event carries no job results
- WHEN the stream completes
- THEN the assistant displays a message indicating no matches

### REQ-INPUT-001: Chat Input Behavior

The system MUST provide a text input and send button. Both MUST be disabled
during streaming. Submitting via Enter or button click SHALL send the message.
Empty submissions MUST be prevented.

#### Scenario: Send message

- GIVEN a non-empty query is typed
- WHEN the user presses Enter or clicks send
- THEN the message appears as a user bubble
- AND the input is cleared and disabled during streaming

#### Scenario: Prevent empty submission

- GIVEN the input is empty
- WHEN the user presses Enter or clicks send
- THEN no message is sent

#### Scenario: Disabled during streaming

- GIVEN a stream is in progress
- WHEN the user tries to type or send
- THEN the input and send button are disabled

### REQ-ERROR-001: Error States

The system MUST display inline error messages for backend unavailability, network
failures, and stream errors. After an error, the input SHALL be re-enabled so the
user can retry.

#### Scenario: Backend unavailable

- GIVEN the backend is unreachable or returns 503
- WHEN the stream fails
- THEN an error bubble appears in the message list
- AND the input is re-enabled for retry

#### Scenario: Stream interrupted mid-response

- GIVEN the SSE stream encounters an error after partial text
- WHEN the error is detected
- THEN the partial assistant response is preserved
- AND an error bubble indicates the interruption

### REQ-MATCHES-001: Match Results Display

The `done` event MAY carry job matches. When present, the system MUST display
them as a compact inline list with clickable links to `/jobs/{id}`.

#### Scenario: Display job matches

- GIVEN the `done` event carries job matches
- WHEN results render
- THEN each match shows the job title linked to `/jobs/{id}`

#### Scenario: No matches message

- GIVEN the `done` event carries zero matches
- WHEN results render
- THEN a message shows "No matching jobs found"

## Out of scope

- Full conversation history or dedicated `/chat` page
- Multi-turn refinement or follow-up queries
- Saved chats or localStorage persistence
- Cross-tab sync

## Acceptance criteria

- [ ] FAB renders on all pages, opens shadcn Dialog on click
- [ ] SSE proxy forwards stream headers and body correctly
- [ ] Each browser tab has independent chat state
- [ ] Tokens render incrementally during SSE streaming
- [ ] Typing indicator shows during stream, hides on completion
- [ ] Backend error displays inline error with retry capability
- [ ] Job matches display as compact inline list with /jobs/{id} links
- [ ] `npm run typecheck` passes
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] `npm run test` passes (existing test baseline)

## Frontend i18n dependency (added in `feat-frontend-i18n`, applied 2026-06-22)

This capability was originally declared i18n-out-of-scope. After the v1 i18n cycle shipped (and v3 cleaned up `authCopy.ts`), every chat component was migrated to `useTranslations('Chat.*')` and `useTranslations('Jobs.*')`. Concretely:

- **ChatFAB button label** consumes `Chat.fab.label` ("Open chat assistant").
- **ChatDialog title** consumes `Chat.dialog.title` ("Chat with Jobs Finder").
- **ChatPanel header** consumes `Chat.panel.header` ("AI Job Assistant").
- **ChatMessages** empty-state placeholder and status labels consume `Chat.messages.emptyStatePlaceholder` and `Chat.status.{analyzing,searching}` (added in `fix-i18n-f8-f7-cleanups`).
- **ChatInput placeholder** consumes `Chat.input.placeholder` ("Ask about jobs, e.g. 'remote React roles in Madrid'").
- **AssistantMessage** translates server error codes via `Chat.errors.{streamFailed,connectionFailed,generic,rateLimit}`. When the code is unknown, it falls back to the raw server message (see D1 in cycle 2 archive).
- **useChat hook** (3 originally-hardcoded English error literals replaced in cycle 2) emits stable error codes; the component layer translates by code so server-side Spanish messages still flow through without regression.
- **sonner toasts** in the chat flow use `useTranslations`; no hardcoded English error strings remain.

The full translation contract lives in **`openspec/specs/frontend-i18n/spec.md`**. All REQs from this capability now implicitly depend on the i18n contract being honored — a missing translation key surfaces as a `"Namespace.path"` literal (per next-intl 4.x `useTranslations` convention) which the CI grep audit (`pnpm run lint:i18n`) flags.

No new REQs added to this capability — the i18n translation work is enforced by the existing REQs (which mandate correct UI rendering) rather than new i18n-specific REQs.
