# Tasks: Frontend Read-Only Dashboard

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

| Field | Value |
|-------|-------|
| Estimated changed lines | 4,000–6,000 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (user to choose) |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Scaffold + Config + Deps | PR 1 | Delete old, create-next-app, TW 3.4, shadcn init, providers, AGENTS.md |
| 2 | AppShell + Route Handlers + API Layer | PR 2 | Sidebar, Header, ThemeToggle, types, api-client, route handlers, hooks |
| 3 | Dashboard + Job Detail pages | PR 3 | StatsCards, JobList, JobCard, JobDetail, skeletons, empty states |
| 4 | Search + Settings + Polish | PR 4 | FilterPanel, Search page, Settings page, AnimatePresence, animations |
| 5 | Testing + E2E + Cleanup | PR 5 | Vitest setup, unit/hook/component tests, Playwright config, archive old spec |

## Phase 1: Scaffold & Infrastructure

- [ ] 1.1 Delete `frontend/` keeping `.gitignore` and `.env.example`
- [ ] 1.2 Create `package.json` with all deps (next, react, motion, react-query, shadcn/ui deps, TW 3.4, postcss, autoprefixer, tailwindcss-animate, vitest)
- [ ] 1.3 Create `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `vitest.config.ts`, `vitest.setup.ts`
- [ ] 1.4 Initialize shadcn/ui with slate base + default style; add button, card, input, badge, switch, select, skeleton, alert, sheet components
- [ ] 1.5 Create `src/app/globals.css` with TW directives, CSS variables (light/dark), fonts (Inter, DM Sans, JetBrains Mono), skeleton shimmer, selection styles
- [ ] 1.6 Create `src/lib/utils.ts` with `cn()` helper (clsx + tailwind-merge)
- [ ] 1.7 Create root `src/app/layout.tsx` with ThemeProvider > QueryProvider > Toaster + `suppressHydrationWarning`
- [ ] 1.8 Update `AGENTS.md` — stack: TW 3.4, shadcn/ui (slate), Radix deps; archive frontend-scaffold spec

## Phase 2: AppShell + Providers

- [ ] 2.1 Create `src/app/(dashboard)/layout.tsx` with AppShell wrapper
- [ ] 2.2 Create `src/components/layout/Sidebar.tsx` — w-64, bg-card, border-r, Logo, NavLinks (usePathname), version footer
- [ ] 2.3 Create `src/components/layout/Header.tsx` — h-14, border-b, px-6, breadcrumb + ThemeToggle
- [ ] 2.4 Create `src/components/layout/ThemeToggle.tsx` — next-themes light/dark/system toggle
- [ ] 2.5 Create `src/components/layout/AppShell.tsx` — flex h-screen overflow-hidden, compose Sidebar + Header + main
- [ ] 2.6 Create `src/app/providers.tsx` — ThemeProvider + QueryProvider composition

## Phase 3: Types + API Layer + Route Handlers

- [ ] 3.1 Create `src/types/job.ts` — Job interface per design
- [ ] 3.2 Create `src/types/stats.ts` — DashboardStats, perSource types
- [ ] 3.3 Create `src/types/settings.ts` — Platform, SourceStatus
- [ ] 3.4 Create `src/lib/api-client.ts` — typed fetch wrapper with functions for each endpoint
- [ ] 3.5 Create `src/lib/formatters.ts` — date-fns relative time, number formatting, platform colors/badges
- [ ] 3.6 Create `src/app/api/jobs/route.ts` — GET proxy: page/limit → offset/limit translation, search params pass-through
- [ ] 3.7 Create `src/app/api/jobs/[id]/route.ts` — GET proxy: fetch history + filter by ID
- [ ] 3.8 Create `src/app/api/stats/route.ts` — GET proxy: read scheduler/status → DashboardStats
- [ ] 3.9 Create `src/app/api/health/route.ts` — GET proxy: pass-through to backend /health
- [ ] 3.10 Create `src/hooks/useJobs.ts`, `useJobDetail.ts`, `useStats.ts`, `useDebounce.ts`

## Phase 4: Dashboard Page (/)

- [ ] 4.1 Create `src/app/(dashboard)/page.tsx` — compose StatsCardsRow + SearchBar + JobList + RightSidebar
- [ ] 4.2 Create `src/components/dashboard/StatCard.tsx` — animated card (spring 0.3s, stagger 0.1s), icon, label, value
- [ ] 4.3 Create `src/components/dashboard/StatsCardsRow.tsx` — 4 StatCards: Total Jobs, Jobs Today, Active Platforms, Last Sync
- [ ] 4.4 Create `src/components/dashboard/JobCard.tsx` — title, company, location, posted_at (relative), source badge, salary, hover lift animation
- [ ] 4.5 Create `src/components/dashboard/JobList.tsx` — useInfiniteQuery, IntersectionObserver trigger, "No more jobs" state
- [ ] 4.6 Create `src/components/dashboard/SearchBar.tsx` — debounced 400ms input + Export CSV button
- [ ] 4.7 Create `src/components/dashboard/RightSidebar.tsx` — RecentActivity + PlatformDistribution (hidden < lg)
- [ ] 4.8 Create `src/components/dashboard/EmptyState.tsx` — "No results" with icon + CTA
- [ ] 4.9 Create skeleton variants for StatCard, JobCard, EmptyState

## Phase 5: Job Detail Page (/jobs/[id])

- [ ] 5.1 Create `src/app/(dashboard)/jobs/[id]/page.tsx` — 2-col layout with BackButton
- [ ] 5.2 Create `src/components/jobs/JobDetailContent.tsx` — title, company, skills/tags, salary, full description
- [ ] 5.3 Create `src/components/jobs/JobDetailAside.tsx` — source badge, posted date, location, external link (noopener)
- [ ] 5.4 Create `src/components/jobs/JobNotFound.tsx` — Alert with "Job not found" + "Back to Dashboard" button
- [ ] 5.5 Create skeleton matching 2-column detail layout (SC-026)

## Phase 6: Search Page (/search)

- [ ] 6.1 Create `src/app/(dashboard)/search/page.tsx` — sticky SearchBar + FilterPanel + results grid
- [ ] 6.2 Create `src/components/search/FilterPanel.tsx` — platform multi-select, contract dropdown, salary range min/max
- [ ] 6.3 Create `src/components/search/EmptyState.tsx` — "No jobs match your filters" + "Clear all filters" button
- [ ] 6.4 Create skeleton grid (6 cards) for loading state (SC-017)

## Phase 7: Settings Page (/settings)

- [ ] 7.1 Create `src/app/(dashboard)/settings/page.tsx` — PlatformConfigCard + AlertPreferences sections
- [ ] 7.2 Create `src/components/settings/PlatformConfigCard.tsx` — toggle each platform on/off (local state, SC-018/SC-019)
- [ ] 7.3 Create `src/components/settings/AlertPreferences.tsx` — checkboxes for notification types (local state, v1)

## Phase 8: Animations + Polish

- [ ] 8.1 Wrap page content in AnimatePresence mode="wait" keyed by pathname
- [ ] 8.2 Add framer-motion `motion.div` entrance animations to StatCards, JobCards, page transitions
- [ ] 8.3 Verify dark mode (next-themes) — all CSS variables render correctly
- [ ] 8.4 Verify responsive: sidebar collapse on mobile, grid adaptation, no overflow
- [ ] 8.5 Verify all skeleton loading states match component layout (no layout shift)
- [ ] 8.6 Run `npm run build` + `npm run typecheck` — fix all strict TS errors

## Phase 9: Testing

- [ ] 9.1 Write unit tests: `cn()` utility, `formatters.ts` (relative time, number format, platform colors)
- [ ] 9.2 Write unit tests: `api-client.ts` — typed fetch wrapper edge cases
- [ ] 9.3 Write hook tests: `useStats`, `useJobs`, `useDebounce` via renderHook
- [ ] 9.4 Write component tests: `StatCard`, `JobCard`, `EmptyState` — render with props, assert output
- [ ] 9.5 Run `npm run test` — all tests green

## Phase 10: E2E + Cleanup

- [ ] 10.1 Create `playwright.config.ts` — project placeholder, no test files
- [ ] 10.2 Update `package.json` scripts: `test:e2e` placeholder
- [ ] 10.3 Final `npm run build` + `npm run typecheck` + `npm run test` — all pass
