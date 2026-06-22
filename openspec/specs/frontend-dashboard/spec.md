# frontend-dashboard Specification

**Change**: `frontend-readonly-dashboard` • **Type**: NEW (replaces `frontend-scaffold`)

## Purpose

Read-only dashboard UI for viewing persisted jobs from the backend database. No scraping, importing, chat, or SSE. Four client-rendered pages consume GET-only data through Next.js Route Handlers proxied to the backend.

## Requirements

### REQ-DASH-001: AppShell layout

The shell MUST have a fixed left sidebar (w-64) with nav links, a top header (h-14), and a `<main>` content area. Sidebar MUST highlight the active route. Header MUST show the app title and a theme toggle (next-themes).

- **SC-001**: Given any route, the sidebar shows Dashboard, Search, and Settings links. When `/jobs/123` is active, no sidebar link is highlighted (detail is child of Dashboard).
- **SC-002**: Given dark mode enabled in OS prefs, the app respects it on first render via next-themes.

### REQ-DASH-002: Dashboard stats row

The Dashboard (`/`) MUST display 4 stat cards above the job list: **Total Jobs**, **Jobs Today**, **Active Platforms**, and **Last Sync**. Each card shows a label, value, and icon. Values MUST come from `GET /jobs/history?stats=1` or the first page response.

- **SC-003**: Given the stats endpoint resolves, each card renders its value and label. No card is empty.
- **SC-004**: Given the endpoint fails (4xx/5xx), each card shows `—` and a sonner toast with the error.

### REQ-DASH-003: Job list with search and export

Below the stats row MUST be a search bar (text input, debounced 400ms) and an "Export CSV" button. Below that, a scrollable list of job cards. Each card MUST show: title, company, location, posted_at (relative via date-fns), source badge, and salary range (if available). The list MUST paginate via infinite scroll using `GET /jobs/history?page=N&limit=20`.

- **SC-005**: Given the user types in the search bar, after 400ms of inactivity a request fires with the search term.
- **SC-006**: Given the user clicks "Export CSV", the browser downloads a CSV file with the current filtered results.
- **SC-007**: Given the user scrolls to the bottom, the next page loads automatically (infinite scroll via IntersectionObserver).
- **SC-008**: Given there are no more results, a "No more jobs" message appears instead of a loading indicator.

### REQ-DASH-004: Right sidebar — activity and platform distribution

On desktop (≥lg), a right sidebar MUST show:
- **Recent Activity**: last 5 `GET /scheduler/status` entries, each with timestamp and description.
- **Platform Distribution**: horizontal bars showing job count per platform (LinkedIn, Indeed, InfoJobs) with proportional widths and counts.

- **SC-009**: Given the scheduler status returns empty, the activity section shows "No recent activity".
- **SC-010**: Given platform data has 100 jobs across 3 platforms, each bar's width is proportional to `count / total * 100`.

### REQ-DASH-005: Job detail page

`/jobs/[id]` MUST render a 2-column layout: main column (title, company, skills as badges, salary range, full description) and aside column (metadata: source, posted date, location, link to original posting). A "Back to Dashboard" link MUST appear at the top.

- **SC-011**: Given a valid job ID, both columns render with all available fields. The external link opens in a new tab with `rel="noopener noreferrer"`.
- **SC-012**: Given an invalid job ID (404), an inline Alert shows "Job not found" with a "Back to Dashboard" button.
- **SC-013**: Given the job has no salary data, the salary field is omitted entirely (not shown as "N/A").

### REQ-DASH-006: Search page with filters

`/search` MUST have a sticky search bar at the top with filter controls: platform (multi-select: LinkedIn, Indeed, InfoJobs), contract type (dropdown), and salary range (min/max inputs). Results render in a responsive grid: 1 col on mobile, 2 on `lg`, 3 on `xl`. An empty state MUST appear when results are zero.

- **SC-014**: Given the user selects "LinkedIn" as the only platform, results are filtered server-side via `GET /jobs/search?source=linkedin`.
- **SC-015**: Given all filters are cleared, the search reverts to unfiltered results.
- **SC-016**: Given the search returns zero results, an Empty state shows "No jobs match your filters" with a "Clear all filters" button.
- **SC-017**: Given the search is in-flight, skeleton cards (6) replace the grid.

### REQ-DASH-007: Settings page

`/settings` MUST show two sections: **Platform Configuration** (toggle each platform active/inactive — visual only, no backend POST in v1) and **Alert Preferences** (checkboxes for notification types — visual only, no persistence in v1).

- **SC-018**: Given the Settings page renders, all toggles and checkboxes are interactive (local state only).
- **SC-019**: Given the user toggles a platform off and reloads, the toggle resets to default (no persistence).

### REQ-DASH-008: Data layer — React Query with Route Handler proxy

All data fetching MUST use `@tanstack/react-query` v5 with `staleTime: 300000` (5 min). Every request MUST go through a Next.js Route Handler at `src/app/api/*` — the browser NEVER calls `BACKEND_URL` directly. Types MUST be defined in `src/lib/types.ts` mirroring backend responses.

- **SC-020**: Given the app renders, no `fetch()` call in client components targets an absolute URL (no `BACKEND_URL` string in client bundles).
- **SC-021**: Given a successful query resolves, React Query caches it for 5 minutes before re-fetching on mount.
- **SC-022**: Given the backend returns a 5xx error, the Route Handler propagates a structured `{error: {code, message}}` JSON response (not raw HTML).

### REQ-DASH-009: No chat, SSE, or scraping code

The `frontend/src/` directory MUST contain zero references to chat, SSE, streaming, scraping, crawling, or import functionality.

- **SC-023**: Given a grep for `chat|stream|sse|scraper|import_url|li_at|cookie` in `frontend/src/`, no matches are found.
- **SC-024**: Given `npm run build` succeeds, the production bundle contains no SSE or streaming-related code.

### REQ-DASH-010: Per-component skeletons

Every data-driven component MUST show a skeleton during loading — NO global spinner or full-page loader.

- **SC-025**: Given the Dashboard is loading stats, 4 skeleton stat cards render (not a single global spinner).
- **SC-026**: Given the job detail is loading, a skeleton matching the 2-column layout renders.

## Out of scope

Auth, PWA, i18n, analytics, backend API changes, chat/streaming, import/crawl, POST/PUT/DELETE on jobs.

## Acceptance criteria (sdd-verify)

- [ ] `npm run build` + `npm run typecheck` pass with strict TS
- [ ] Dashboard shows 4 stat cards from history endpoint
- [ ] Job list paginates (infinite scroll), detail renders single job
- [ ] Search filters by platform/contract/salary
- [ ] Zero SSE, chat, or scraping code in `frontend/src/`
- [ ] All data fetching goes through `/api/*` Route Handlers, no direct backend calls

## Frontend i18n dependency (added in `feat-frontend-i18n`, applied 2026-06-22)

This capability was originally declared i18n-out-of-scope. After the v1 i18n cycle shipped, every dashboard component was migrated to `useTranslations('Dashboard.*')` (and the relevant sub-namespaces). Concretely:

- **Dashboard stats row** (REQ-DASH-002) labels and aria attributes now consume `Dashboard.stats.*` keys (`totalJobs`, `jobsToday`, `activePlatforms`, `lastSync`) with ICU MessageFormat pluralization for counts.
- **Dashboard error toasts** (REQ-DASH-002 SC-004) use `JobsErrors.*` keys for the error title and the retry prompt.
- **EmptyState component** (used by dashboard, search, favorites) consumes translated `title`/`description` props via `useTranslations('Jobs.emptyState.*')`.
- **`formatRelativeTime`** (date-fns wrapper in `lib/formatters.ts`) is locale-aware — the dashboard receives `locale: 'es' | 'en'` from `useLocale()` and passes it through.
- **RightSidebar nav labels** and **StatsCardsRow card titles** use `useTranslations` (no more hardcoded ES/EN mix).
- **`JobSourceBreakdown`** uses ICU pluralization for `count` (e.g. "1 trabajo / 2 trabajos / 0 trabajos").

The full translation contract (namespaces, ICU plurals, RTL exclusion, locale precedence URL > cookie > Accept-Language > default) lives in **`openspec/specs/frontend-i18n/spec.md`**. All REQs from this capability now implicitly depend on the i18n contract being honored — a missing translation key surfaces as a `"Namespace.path"` literal (per next-intl 4.x `useTranslations` convention) or a thrown `MISSING_MESSAGE` (for `getTranslations`), which the CI grep audit (`pnpm run lint:i18n`) flags.

No new REQs added to this capability — the i18n translation work is enforced by the existing REQs (which mandate correct UI rendering) rather than new i18n-specific REQs. The "Frontend i18n dependency" section serves as the cross-reference anchor so a future reader of this spec sees the dependency without having to discover it via grep.
