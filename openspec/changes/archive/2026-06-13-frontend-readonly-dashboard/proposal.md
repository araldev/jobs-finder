# Proposal: Frontend Read-Only Dashboard

## Intent

Replace the existing Next.js frontend with a read-only dashboard displaying persisted jobs from the backend DB. Zero scraping or import — only GET endpoints. Stateless monitoring UI replacing the chat-companion paradigm.

## Scope

### In Scope
- Delete `frontend/`, rebuild from scratch
- 5 pages: Dashboard `/`, Jobs `/jobs`, Detail `/jobs/[id]`, Search `/search`, Settings `/settings`
- AppShell (sidebar w-64 + header h-14 + main)
- @tanstack/react-query (all GET, staleTime 5min)
- Tailwind 3.4 + shadcn/ui (slate) + framer-motion 11
- next-themes, sonner, lucide-react, date-fns
- Vitest + @testing-library/react + jsdom; Playwright E2E
- Typography: Inter, DM Sans, JetBrains Mono via Google Fonts

### Out of Scope
- Chat streaming / SSE consumption
- Any POST/PUT/DELETE on jobs
- Auth, PWA, i18n, analytics
- Backend API changes (consumed as-is)

## Capabilities

### New Capabilities
- `frontend-dashboard`: Read-only dashboard UI replacing `frontend-scaffold`.

### Modified Capabilities
- None. Backend capabilities (scrapers, repository, scheduler) unchanged.

## Approach

1. Delete `frontend/` → `create-next-app` with App Router + TS strict
2. Install TW 3.4 + shadcn/ui (slate) + deps
3. Build AppShell, then 5 pages as client components
4. React Query hooks in `hooks/`, typed client in `lib/`
5. Backend via Next.js Route Handlers (server proxy, no CORS)
6. framer-motion `AnimatePresence` for page transitions
7. Per-component skeletons — NO global spinner

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/` | Removed → New | Entire dir deleted, rebuilt |
| `openspec/specs/frontend-scaffold` | Archived | Replaced by `frontend-dashboard` |
| `AGENTS.md` | Modified | Update frontend workspace section |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| TW v3 vs v4 confusion | Med | Pin TW 3.4; ban v4 tokens |
| ~100+ new files | High | Chained PRs: scaffold → pages → polish |
| Backend contract drift | Low | GET endpoints are stable, read-only |
| shadcn style mismatch | Med | Explicit `slate` base + `default` style |

## Rollback Plan

- `git checkout HEAD -- frontend/` — no DB or backend impact
- Revert `AGENTS.md`
- Zero-service rollback (no schema changes)

## Dependencies

- `GET /jobs` — aggregated search
- `GET /jobs/history` — paginated DB results
- `GET /health` — health check
- `GET /scheduler/status` — scheduler status
- `GET /jobs/{id}` — single job detail (verify or create Route Handler)

## Success Criteria

- [ ] `npm run build` + `npm run typecheck` pass (strict)
- [ ] Dashboard shows 4 stat cards from history endpoint
- [ ] Job list paginates, detail renders single job
- [ ] Search filters by platform/contract/salary
- [ ] Zero SSE, chat, or scraping code in `frontend/src/`
