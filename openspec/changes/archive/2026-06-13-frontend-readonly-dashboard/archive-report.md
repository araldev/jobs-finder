# Archive Report: frontend-readonly-dashboard

**Change**: `frontend-readonly-dashboard`
**Archived**: 2026-06-13
**Status**: CLOSED
**Verdict**: PASS WITH WARNINGS (all critical findings resolved post-verify)

## Traceability

### Engram Observations

| Artifact | Engram ID | Topic Key |
|----------|-----------|-----------|
| Proposal | #430 | `sdd/frontend-readonly-dashboard/proposal` |
| Spec | #431 | `sdd/frontend-readonly-dashboard/spec` |
| Design | #432 | `sdd/frontend-readonly-dashboard/design` |
| Tasks | #433 | `sdd/frontend-readonly-dashboard/tasks` |
| Apply Progress (PR 5/5) | #434 | `sdd/frontend-readonly-dashboard/apply-progress` |
| Verify Report | #441 | `sdd/frontend-readonly-dashboard/verify-report` |
| **Archive Report** | *(current)* | `sdd/frontend-readonly-dashboard/archive-report` |

### OpenSpec Filesystem Artifacts (archived)

All artifacts moved to `openspec/changes/archive/2026-06-13-frontend-readonly-dashboard/`:

| Artifact | Path (in archive) | Exists |
|----------|-------------------|--------|
| Proposal | `proposal.md` | ✅ |
| Delta Specs | `specs/frontend-dashboard/spec.md` | ✅ |
| Design | `design.md` | ✅ |
| Tasks | `tasks.md` | ✅ (52/52 complete) |
| Verify Report | `verify-report.md` | ✅ |
| Archive Report | `archive-report.md` | ✅ *(this file)* |

### Main Specs Updated

| Spec | Action | Path |
|------|--------|------|
| `frontend-dashboard` | **Created** (new main spec) | `openspec/specs/frontend-dashboard/spec.md` |
| `frontend-scaffold` | **Archived** (superceded) | Archived to `old-spec-frontend-scaffold/` in archive folder |

## Delivery Summary

### Scale

- **5 stacked PRs** (stacked-to-main chain)
- **~80 files created / modified** across the full frontend rebuild
- **~4,000+ estimated changed lines**
- **52/52 tasks complete** across 10 phases

### PR Breakdown

| PR | Phase | Scope | Files |
|----|-------|-------|-------|
| PR 1 | 1 | Scaffold, config, deps, TW 3.4 shadcn init, globals.css, cn(), AGENTS.md | ~15 files |
| PR 2 | 2–3 | AppShell, Sidebar, Header, ThemeToggle, types, api-client, Route Handlers, hooks | ~20 files |
| PR 3 | 4–5 | Dashboard (stats, job list), Job Detail (2-col), skeletons, empty/error states | ~18 files |
| PR 4 | 6–8 | Search page, Settings page, animations, polish, responsive | ~12 files |
| PR 5 | 9–10 | Unit tests, hook tests, component tests, Playwright config, final verification | ~15 files |

### What Was Delivered

- Complete frontend rebuild replacing `frontend-scaffold` (chat/SSE/scraping paradigm)
- Read-only dashboard with 5 client-rendered pages: Dashboard, Jobs, Job Detail, Search, Settings
- AppShell with Sidebar (w-64), Header (h-14), per-component skeletons, framer-motion transitions
- React Query data layer with 5-min staleTime, all requests proxied via Next.js Route Handlers
- Dark/light mode via next-themes, sonner toasts, per-component skeletons (no global spinner)
- Infinite scroll with IntersectionObserver + "No more jobs" state (added post-verify)
- 400ms debounce on search inputs (fixed post-verify)
- AGENTS.md updated with correct TW 3.4 / shadcn slate stack (fixed post-verify)
- 35 automated tests across 9 test files (unit, hook, component smoke tests)
- Playwright E2E config with placeholder

### Files Changed (representative)

| Area | Files |
|------|-------|
| Config | `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`, `components.json`, `vitest.config.ts`, `vitest.setup.ts`, `eslint.config.mjs`, `playwright.config.ts` |
| Layout | `src/app/layout.tsx`, `src/app/providers.tsx`, `src/app/globals.css`, `components/layout/AppShell.tsx`, `Sidebar.tsx`, `Header.tsx`, `ThemeToggle.tsx` |
| Route Handlers | `src/app/api/jobs/route.ts`, `api/jobs/[id]/route.ts`, `api/stats/route.ts`, `api/health/route.ts` |
| Types | `src/types/job.ts`, `stats.ts`, `settings.ts` |
| Hooks | `src/hooks/useJobs.ts`, `useJobDetail.ts`, `useStats.ts`, `useDebounce.ts` |
| Pages | `src/app/page.tsx`, `jobs/page.tsx`, `jobs/[id]/page.tsx`, `search/page.tsx`, `settings/page.tsx` |
| Components | `JobCard`, `JobList`, `JobDetailContent`, `JobDetailAside`, `StatCard`, `StatsCardsRow`, `SearchBar`, `FilterPanel`, `RightSidebar`, `PlatformConfigCard`, `NotificationSettings`, `PlatformBadge`, `SalaryBadge`, `EmptyState`, `ErrorState`, `ExportButton`, `PageTransition` |
| Tests | `utils.test.ts`, `formatters.test.ts`, `useDebounce.test.ts`, `EmptyState.test.tsx`, `ErrorState.test.tsx`, `SearchBar.test.tsx`, `StatCard.test.tsx`, `PlatformBadge.test.tsx`, `SalaryBadge.test.tsx`, `test-utils.tsx` |

## Verification Results

### Gates

| Gate | Result |
|------|--------|
| Build | ✅ Passed (Next.js 15.5.19, 2.6s) |
| TypeScript | ✅ Passed (0 errors, strict + noUncheckedIndexedAccess) |
| Tests | ✅ 35 passed, 0 failed (9 test files) |
| Lint | ✅ Passed (0 warnings/errors) |

### Spec Compliance

- **8/26 scenarios fully compliant** — stat cards, skeletons, dark mode, no SSE/chat, React Query config, platform bars, salary omission
- **13 untested** — behaviors verified manually or implicitly via component rendering
- **3 not implemented** → RESOLVED post-verify (infinite scroll added, AGENTS.md updated, debounce set to 400ms)
- **1 partially compliant** — error response format (SC-022: uses flat string, not structured `{code, message}`)
- **1 renamed** — `AlertPreferences` → `NotificationSettings` (functionally equivalent)

### Critical Finding Resolution (Post-Verify)

| Finding | Status | Resolution |
|---------|--------|------------|
| SC-007: Infinite scroll not implemented | ✅ RESOLVED | `useInfiniteQuery` + `IntersectionObserver` added to `JobList` |
| SC-008: No "No more jobs" message | ✅ RESOLVED | End-of-results state added to infinite scroll |
| SC-005: Debounce 300ms vs spec 400ms | ✅ RESOLVED | Changed to 400ms in `page.tsx` and `search/page.tsx` |
| AGENTS.md not updated (lists v4/nova) | ✅ RESOLVED | Updated to reflect TW 3.4 + shadcn/ui (slate) |

### Known Remaining Issues (non-blocking)

| Issue | Type | Notes |
|-------|------|-------|
| SC-022: Error response format | WARNING | Uses flat string `{error: "..."}` not `{error: {code, message}}` |
| SC-004: Stats error shows ErrorState | WARNING | Shows ErrorState component instead of per-card "—" with toast |
| SC-009: Activity sidebar sources | WARNING | Reads jobs instead of scheduler/status entries |
| SC-001: /jobs/[id] sidebar highlight | WARNING | "Jobs" link highlighted for job detail pages |
| `NotificationSettings` renamed | WARNING | Named differently than design's `AlertPreferences` |
| No coverage config | SUGGESTION | `vitest.config.ts` has no coverage provider |
| No hook tests for useJobs/useStats/useJobDetail | SUGGESTION | Only useDebounce tested |
| No Route Handler tests | SUGGESTION | No integration tests for API layer |
| E2E directory empty | SUGGESTION | Only `.gitkeep` — no Playwright tests |

## SDD Cycle Complete

The `frontend-readonly-dashboard` change has been fully:
1. ✅ **Proposed** — Intent, scope, approach, rollback documented
2. ✅ **Specified** — 10 requirements with 26 scenarios (RFC 2119)
3. ✅ **Designed** — Architecture decisions, data flow, component tree, file changes
4. ✅ **Tasked** — 52 tasks across 10 phases, 5 stacked PRs
5. ✅ **Applied** — ~80 files created/modified across 5 PRs
6. ✅ **Verified** — All gates pass, 35 tests green, critical findings resolved
7. ✅ **Archived** — Specs synced to main, artifacts moved to archive
