# Design: Frontend Read-Only Dashboard

## Technical Approach

Delete `frontend/` (keep `.gitignore`, `.env.example`) and rebuild with Next.js 15 App Router, Tailwind CSS 3.4 + shadcn/ui (slate/default), React Query 5 for all GET requests proxied through Next.js Route Handlers. Five client-rendered pages inside an AppShell layout. Zero chat, SSE, or scraping code.

## Architecture Decisions

| Decision | Options | Tradeoffs | Chosen |
|----------|---------|-----------|--------|
| Tailwind version | v4 (current) vs v3.4 | v4 is installed but spec requires shadcn/ui "slate" which needs TW v3 plugin system (`tailwindcss-animate`, `postcss` config). v4 is faster but shadcn/slate not fully compatible. | TW 3.4 — downgrade: replace `@tailwindcss/postcss` with `tailwindcss`, `postcss`, `autoprefixer`, `tailwindcss-animate` |
| shadcn style | nova (current) vs slate/default | Nova uses base-ui; slate uses Radix. Spec mandates Radix + CSS variables + `cn()`. | Slate/default — aligns with spec, Radix ecosystem |
| Animation lib | `motion` (exists) vs `framer-motion` 11 | `motion` is the v12 successor exporting the same API. No benefit to downgrade. | Keep `motion` — same API surface, newer package |
| Job detail data | New backend endpoint vs proxy filter | Backend has no `GET /jobs/{id}`. Adding one is out-of-scope. | Route Handler fetches from `/jobs/history?limit=1&offset=N` and filters by ID. Document as backend gap. |
| Salary data | Omit vs placeholder | Backend schema has no salary field. Spec mentions salary badges. | Omit entirely when null — same treatment as REQ-DASH-005/SC-013. Type includes `salary?: string \| null` for future data. |
| Pagination model | Backend `offset`/`limit` vs frontend `page`/`limit` | React Query `useInfiniteQuery` works naturally with page numbers. | Route Handler translates `page → offset = (page-1) * limit` |

## Data Flow

```
Browser ──fetch(/api/*)──→ Next.js Route Handler ──fetch(BACKEND_URL/*)──→ Backend FastAPI
                                          │
                                    React Query cache
                                  staleTime: 5 min
                                  refetchOnWindowFocus
```

### Route Handler mapping

| Frontend Route | Backend Target | Translation |
|---|---|---|
| `GET /api/jobs?page=1&limit=20` | `GET /jobs/history?limit=20&offset=0` | `offset = (page-1) * limit` |
| `GET /api/jobs?q=&source=&contract_type=&salary_min=&salary_max=` | `GET /jobs/history?keywords=&sources=&limit=20` | Pass through known params, omit unsupported |
| `GET /api/jobs/[id]` | `GET /jobs/history?limit=1` + filter | Fetch first page, find by ID |
| `GET /api/stats` | `GET /scheduler/status` | Read `total_in_db`, `per_source`, `last_run_end` |
| `GET /api/sources` | `GET /scheduler/status` | Return `per_source` keys as active platforms |
| `GET /api/health` | `GET /health` | Pass through |

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `frontend/` (except `.gitignore`, `.env.example`) | Delete | Complete teardown — all existing chat/scaffold code |
| `frontend/package.json` | Replace | Deps: next, react, motion, @tanstack/react-query, shadcn/ui deps, sonner, next-themes, lucide-react, date-fns, cva, clsx, tailwind-merge, tailwindcss 3.4, postcss, autoprefixer, tailwindcss-animate, vitest, @testing-library/react, jsdom |
| `frontend/postcss.config.mjs` | Replace | TW v3 postcss config with `tailwindcss` + `autoprefixer` plugins |
| `frontend/next.config.ts` | Modify | Add `images.remotePatterns` if needed, keep minimal |
| `frontend/tsconfig.json` | Keep | Already strict + `noUncheckedIndexedAccess` + `@/*` path alias |
| `frontend/vitest.config.ts` | Keep | Already correct |
| `frontend/src/` | Create all | Full tree per spec |
| `openspec/specs/frontend-scaffold/` | Archive | Superceded by frontend-dashboard |
| `AGENTS.md` | Modify | Update frontend stack: Tailwind 3.4, shadcn/ui (slate), radix deps |

## Interfaces / Contracts

```typescript
// src/types/job.ts
export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  description: string | null;
  posted_at: string | null;
  source: string | null;          // from history endpoint
  first_seen_at: string | null;
  last_seen_at: string | null;
  salary: string | null;          // future-proof, always null today
}

// src/types/stats.ts
export interface DashboardStats {
  totalJobs: number;              // total_in_db
  jobsToday: number;              // computed from last_run_end
  activePlatforms: number;        // Object.keys(per_source).length
  lastSync: string | null;        // last_run_end
  perSource: Record<string, number>;
}

// src/types/settings.ts
export type Platform = "linkedin" | "indeed" | "infojobs";
export interface SourceStatus {
  source: Platform;
  active: boolean;
}
```

## Component Tree

```
<AppShell>
  <Sidebar fixed w-64>
    <Logo />
    <NavLinks />                  // Dashboard, Search, Settings — usePathname()
    <VersionFooter />
  </Sidebar>
  <RightColumn flex-1>
    <Header h-14>
      <Breadcrumb />
      <ThemeToggle />
    </Header>
    <main flex-1 overflow-y-auto p-6>
      <AnimatePresence mode="wait">
        {page content keyed by pathname}
      </AnimatePresence>
    </main>
  </RightColumn>
</AppShell>

Dashboard /:
  <StatsCardsRow>
    <StatCard icon, label, value /> × 4     // spring 0.3s, stagger 0.1s
  </StatsCardsRow>
  <SearchBar debounced 400ms /> + <ExportButton />
  <JobList>                                   // useInfiniteQuery
    <JobCard /> × N                           // spring bounce:0.1, stagger 0.06s
    <InfiniteScrollTrigger />
    "No more jobs" / <EmptyState />
  </JobList>
  <RightSidebar hidden < lg>
    <RecentActivity />                        // last 5 scheduler entries
    <PlatformDistribution />                  // horizontal bars proportional
  </RightSidebar>

/jobs/[id]:
  <BackButton />
  <div grid-cols-2>
    <JobDetailContent title, company, skills, salary, description />
    <JobDetailAside source, posted, location, external link />
  </div>
  <JobNotFound />                             // on 404

/search:
  <SearchBar sticky />
  <FilterPanel platform multi-select, contract dropdown, salary range />
  <div grid-cols-1 lg:2 xl:3>
    <JobCard /> × N
  </div>
  <EmptyState "No jobs match your filters" />

/settings:
  <PlatformConfigCard toggles />              // local state only
  <AlertPreferences checkboxes />             // local state only
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `cn()`, `api-client.ts`, `formatters.ts` | Pure function tests |
| Hook | `useStats`, `useJobs`, `useDebounce` | `renderHook` + MSW/mocked fetch |
| Component | `JobCard`, `StatCard`, `EmptyState` | Render with props, assert output |
| Route Handler | `/api/jobs`, `/api/stats` | Vitest with `NextRequest` mock |

## Migration / Rollout

1. **Scaffold**: delete `frontend/`, rebuild package.json, configs, shadcn init
2. **Shell**: AppShell + Sidebar + Header + ThemeToggle + providers
3. **Pages**: Dashboard (stats + job list) → Job detail → Search → Settings
4. **Polish**: Animations, skeletons, empty/error states
5. **No migration required** — backend unchanged, DB untouched

Rollback: `git checkout HEAD -- frontend/` + revert AGENTS.md.

## Open Questions

- [ ] Backend has no `GET /jobs/{id}` — Route Handler fetches from history and filters by ID. Acceptable for v1?
- [ ] Salary data is absent from backend schema. Omit from UI until backend adds it. Confirm this matches stakeholder expectations.
