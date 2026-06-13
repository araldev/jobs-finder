# SDD Verify Report

**Change**: `frontend-readonly-dashboard`
**Version**: spec.md (openspec) — v1
**Mode**: Standard

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 52 |
| Tasks complete | 52 |
| Tasks incomplete | 0 |

## Build & Tests Execution

**Build**: ✅ Passed
```text
✓ Compiled successfully in 2.6s
Route (app)                          Size  First Load JS
┌ ○ /                              6.05 kB         184 kB
├ ○ /_not-found                      138 B         103 kB
├ ƒ /api/health                      138 B         103 kB
├ ƒ /api/jobs                        138 B         103 kB
├ ƒ /api/jobs/[id]                   138 B         103 kB
├ ƒ /api/stats                       138 B         103 kB
├ ○ /jobs                          2.66 kB         170 kB
├ ƒ /jobs/[id]                     4.58 kB         172 kB
├ ○ /search                        25.7 kB         193 kB
└ ○ /settings                      3.54 kB         161 kB
```

**TypeScript**: ✅ Passed — 0 errors (strict mode + noUncheckedIndexedAccess)
```text
> tsc --noEmit
(no output — clean)
```

**Tests**: ✅ 35 passed, 0 failed, 0 skipped across 9 test files
```text
✓ src/lib/__tests__/utils.test.ts (4 tests)
✓ src/components/jobs/__tests__/PlatformBadge.test.tsx (2 tests)
✓ src/hooks/__tests__/useDebounce.test.ts (2 tests)
✓ src/components/jobs/__tests__/SalaryBadge.test.tsx (2 tests)
✓ src/components/shared/__tests__/ErrorState.test.tsx (3 tests)
✓ src/components/search/__tests__/SearchBar.test.tsx (5 tests)
✓ src/components/dashboard/__tests__/StatCard.test.tsx (3 tests)
✓ src/components/shared/__tests__/EmptyState.test.tsx (5 tests)
✓ src/lib/__tests__/formatters.test.ts (9 tests)
```

**Lint**: ✅ Passed — 0 warnings, 0 errors
```text
✔ No ESLint warnings or errors
```

**Coverage**: ➖ Not available — no coverage tool configured in vitest.config.ts

## Spec Compliance Matrix

| Req | Scenario | Test | Result |
|-----|----------|------|--------|
| REQ-DASH-001 | SC-001: Sidebar shows Dashboard, Search, Settings links; /jobs/123 no highlight | (no covering test) | ❌ UNTESTED (partial) |
| REQ-DASH-001 | SC-002: Dark mode via next-themes on first render | (no covering test) | ❌ UNTESTED |
| REQ-DASH-002 | SC-003: Stats endpoint resolves → each card renders value + label | (no covering test) | ❌ UNTESTED |
| REQ-DASH-002 | SC-004: Endpoint fails → each card shows "—" and sonner toast | (no covering test) | ❌ NOT IMPLEMENTED |
| REQ-DASH-003 | SC-005: Debounced 400ms search fires request | (no covering test) | ❌ UNTESTED (uses 300ms) |
| REQ-DASH-003 | SC-006: Export CSV downloads file | (no covering test) | ❌ UNTESTED |
| REQ-DASH-003 | SC-007: Infinite scroll via IntersectionObserver | (no covering test) | ❌ NOT IMPLEMENTED |
| REQ-DASH-003 | SC-008: "No more jobs" message on exhausted results | (no covering test) | ❌ NOT IMPLEMENTED |
| REQ-DASH-004 | SC-009: Empty scheduler → "No recent activity" | (no covering test) | ❌ UNTESTED |
| REQ-DASH-004 | SC-010: Proportional bar width = count/total × 100 | ✅ `formatters.test.ts` line 16 | ✅ COMPLIANT |
| REQ-DASH-005 | SC-011: Valid job renders 2-column layout + external link noopener | (no covering test) | ❌ UNTESTED |
| REQ-DASH-005 | SC-012: Invalid job (404) → "Job not found" + Back button | (no covering test) | ❌ UNTESTED |
| REQ-DASH-005 | SC-013: No salary data → salary field omitted entirely | ✅ `SalaryBadge.test.tsx` line 11 | ✅ COMPLIANT |
| REQ-DASH-006 | SC-014: Filter by platform → server-side source param | (no covering test) | ❌ UNTESTED |
| REQ-DASH-006 | SC-015: Clear filters → unfiltered results | (no covering test) | ❌ UNTESTED |
| REQ-DASH-006 | SC-016: Zero results → EmptyState with "Clear all filters" | (no covering test) | ❌ UNTESTED |
| REQ-DASH-006 | SC-017: In-flight search → 6 skeleton cards | (no covering test) | ❌ UNTESTED |
| REQ-DASH-007 | SC-018: Settings toggles/checkboxes interactive (local state) | (no covering test) | ❌ UNTESTED |
| REQ-DASH-007 | SC-019: Toggle off → reload → reset to default | (no covering test) | ❌ UNTESTED |
| REQ-DASH-008 | SC-020: No absolute URL fetches in client bundles | ✅ grep/static analysis | ✅ COMPLIANT |
| REQ-DASH-008 | SC-021: React Query staleTime = 5 min (300000ms) | ✅ providers.tsx | ✅ COMPLIANT |
| REQ-DASH-008 | SC-022: 5xx → `{error: {code, message}}` JSON | (no covering test) | ❌ PARTIAL |
| REQ-DASH-009 | SC-023: Grep for chat/stream/sse/scraper/cookie → 0 matches | ✅ grep/static analysis | ✅ COMPLIANT |
| REQ-DASH-009 | SC-024: Build succeeds → no SSE/streaming code | ✅ build | ✅ COMPLIANT |
| REQ-DASH-010 | SC-025: Loading stats → 4 skeleton cards (not global spinner) | ✅ `StatsCardsRow.tsx` lines 13-20 | ✅ COMPLIANT |
| REQ-DASH-010 | SC-026: Loading job detail → skeleton matching 2-column layout | ✅ `loading.tsx` (jobs/[id]) | ✅ COMPLIANT |

**Compliance summary**: 8/26 scenarios fully compliant, 13 untested/no covering test, 3 not implemented, 1 partial, 1 not implemented (different behavior)

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| REQ-DASH-001: AppShell layout | ✅ Implemented | Sidebar (w-64) + Header (h-14) + main; active route highlight via usePathname |
| REQ-DASH-002: Dashboard stats row | ✅ Implemented | 4 StatCards: Total Jobs, Jobs Today, Active Platforms, Last Updated |
| REQ-DASH-003: Job list + search + export | ⚠️ Partial | Search (300ms debounce) and Export CSV work. NO infinite scroll — all results loaded at once with basic useQuery (not useInfiniteQuery). No "No more jobs" message. |
| REQ-DASH-004: Right sidebar activity + platform | ✅ Implemented | RightSidebar hidden <lg; PlatformDistribution with proportional bars |
| REQ-DASH-005: Job detail 2-column layout | ✅ Implemented | Jobs/[id] with BackButton, JobDetailContent + JobDetailAside, loading skeleton |
| REQ-DASH-006: Search page with filters | ✅ Implemented | Sticky search, FilterPanel (platform, contract, salary), responsive grid (lg:2 xl:3), EmptyState |
| REQ-DASH-007: Settings page | ✅ Implemented | PlatformConfigCard toggles + NotificationSettings (local state only) |
| REQ-DASH-008: Data layer (React Query + Route Handlers) | ✅ Implemented | staleTime: 300s, /api/* proxy, server-only api-client |
| REQ-DASH-009: No chat/SSE/scraping code | ✅ Implemented | Zero banned terms in frontend/src/ |
| REQ-DASH-010: Per-component skeletons | ✅ Implemented | Skeletons for stats, job list, job detail, settings, search, root loading |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| TW 3.4 (downgrade from v4) | ✅ Yes | tailwind.config.ts uses TW 3.4 plugin system |
| shadcn/ui slate/default | ✅ Yes | components/ui/ with Radix primitives, cssVariables |
| Keep `motion` (framer-motion v11 successor) | ✅ Yes | All animations use framer-motion 11 from package.json |
| Route Handler fetches /jobs/history + filters | ✅ Yes | api-client.ts uses BACKEND_URL to proxy |
| Salary omitted when null | ✅ Yes | SalaryBadge returns null; JobDetailContent skips with `{job.salary && ...}` |
| Offset calculation: (page-1) * limit | ❌ NOT IMPLEMENTED | No pagination mechanism exists in Route Handler or hooks |
| AlertPreferences component | ❌ RENAMED | Component is `NotificationSettings.tsx`, not `AlertPreferences.tsx` |
| AGENTS.md updated with TW 3.4 + shadcn slate | ❌ NOT UPDATED | AGENTS.md still lists TW v4 and shadcn/ui (nova) |

## Issues Found

### CRITICAL

1. **SC-007 / REQ-DASH-003: Infinite scroll not implemented** — The spec requires `GET /jobs/history?page=N&limit=20` with IntersectionObserver-based infinite scroll. The implementation uses a single `useJobs({ limit: 50 })` query on the dashboard page with no pagination, no `useInfiniteQuery`, and no IntersectionObserver. The `JobList` component renders all results at once.
   - File: `src/app/page.tsx`, `src/components/jobs/JobList.tsx`, `src/hooks/useJobs.ts`

2. **SC-008: "No more jobs" message not implemented** — Related to the above. Since there's no pagination, there's no mechanism to surface "No more jobs" when the end of results is reached.

### WARNING

1. **SC-005: Debounce timing mismatch** — Spec requires 400ms debounce; implementation uses `300` in both `page.tsx` and `search/page.tsx`.
   - File: `src/app/page.tsx:16`, `src/app/search/page.tsx:22`

2. **SC-022: Error response format deviation** — Spec requires `{error: {code, message}}` structure. Implementation returns `{error: "Backend unreachable"}` (flat string). The route handler should wrap errors in `{error: {code: 503, message: "Backend unreachable"}}` format.
   - Files: `src/app/api/jobs/route.ts:23`, `src/app/api/jobs/[id]/route.ts:15-24`, `src/app/api/stats/route.ts:9`

3. **SC-004: Stats error state inconsistency** — Spec says each card shows "—" with a sonner toast on failure. Implementation replaces the entire row with `<ErrorState>` component (no per-card "—", no toast). Consider adding sonner toast and showing stat cards with "—" values alongside the error message.
   - File: `src/components/dashboard/StatsCardsRow.tsx:23-24`

4. **SC-009: Activity section sources** — Spec says activity section reads from `GET /scheduler/status` entries. Implementation shows recent jobs (from `useJobs({ limit: 5 })`) instead. The "No recent activity" empty state is present but the data source is wrong.
   - File: `src/components/dashboard/RightSidebar.tsx:12`

5. **SC-001: Sidebar highlight for /jobs/[id]** — When viewing `/jobs/123`, the "Jobs" sidebar link is highlighted because `pathname.startsWith("/jobs")` matches. Spec says no sidebar link should be highlighted for job detail pages (detail is child of Dashboard).
   - File: `src/components/layout/Sidebar.tsx:39-42`

6. **AGENTS.md not updated** — The root AGENTS.md file still lists Tailwind v4 and shadcn/ui (nova) for the frontend stack. Should reflect TW 3.4 and shadcn/ui (slate/default) as per task 1.8.
   - File: `AGENTS.md` line 16

7. **Design: NotificationSettings renamed from AlertPreferences** — The design and tasks reference `AlertPreferences` but the file is named `NotificationSettings.tsx`. Functionality is equivalent but naming doesn't match the design doc.

### SUGGESTION

1. **No coverage configuration** — `vitest.config.ts` has no coverage provider configured. Add `@vitest/coverage-v8` and configure `coverage` settings to track changed-file coverage.
   - File: `frontend/vitest.config.ts`

2. **Missing hook tests** — `useJobs`, `useStats`, and `useJobDetail` hooks have no tests. Consider adding renderHook tests with mocked fetch/React Query.

3. **No Route Handler tests** — The four `/api/*` Route Handlers have no tests. Consider adding integration tests with mocked backend.

4. **Missing settings/toggle component tests** — `PlatformConfigCard` and `NotificationSettings` have no tests.

5. **E2E directory is empty** — `frontend/e2e/` contains only `.gitkeep`. No Playwright tests exist.

## Verdict

**PASS WITH WARNINGS**

All 4 verification commands pass (build, typecheck, test, lint). 52/52 tasks are complete. The core architecture (AppShell, Sidebar, Header, Route Handlers, React Query data layer, per-component skeletons) is correctly implemented. The spec deviations are documented: no infinite scroll (CRITICAL — core REQ-DASH-003 requirement missing), debounce timing mismatch, error response format deviation, sidebar highlight behavior, and AGENTS.md not updated. Recommend resolving the infinite scroll gap before closing this change, and addressing the WARNING items in a follow-up.
