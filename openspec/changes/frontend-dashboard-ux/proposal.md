# Proposal: Frontend Dashboard UX

## Intent

The dashboard shows raw data but lacks useful UX: job descriptions are plain text, there's no way to bookmark jobs, dashboard cards take too much space, and the `/jobs` page duplicates the dashboard. Users need a polished reading experience, a favorites system, and a dashboard that surfaces genuinely useful information.

## Scope

### In Scope
- Markdown rendering of job descriptions in `JobDetailContent`
- localStorage-based favorites system with heart toggle on JobCard
- Compact dashboard job cards in a 3-column grid (`lg:grid-cols-3`) with external link
- Replace "Jobs Today" stat card with per-source job counts
- `/jobs` page becomes Favorites-only view (from localStorage)
- Keep `/jobs/[id]` detail page unchanged structurally
- Install `react-markdown` + `remark-gfm` + `rehype-sanitize`

### Out of Scope
- Search page (`/search`) — untouched
- Settings page — untouched
- Backend changes (no new endpoints, no schema changes)
- AppShell/Sidebar/Header layout changes
- JobDetailAside or JobDetailContent fundamental structure
- Sync favorites across devices (no backend sync — localStorage only)

## Capabilities

> Researching `openspec/specs/` — `frontend-dashboard/spec.md` found.

### New Capabilities
- `favorites`: Local-only bookmarking of jobs via localStorage.

### Modified Capabilities
- `frontend-dashboard`: Requirements for dashboard UX, compact cards, markdown descriptions, favorites UI, and Favorites page.

## Approach

1. **Markdown**: Add `react-markdown`, `remark-gfm`, `rehype-sanitize`. Replace `whitespace-pre-line` in `JobDetailContent` with `<ReactMarkdown remarkPlugins={[gfm]} rehypePlugins={[rehypeSanitize]}>`. Linkify bare URLs automatically.
2. **Favorites**: Create `useFavorites` hook (React Query-like API, reads/writes `localStorage`). Add `FavoriteButton` (heart icon, lucide-react) to `JobCard`. Store full job objects keyed by ID.
3. **Compact cards**: New `compact` variant on `JobCard` — smaller padding, single-line company, external link button (`ExternalLink` icon → `job.url`). Dashboard uses this variant in a `<div className="grid gap-3 lg:grid-cols-3">`.
4. **Dashboard info**: Replace "Jobs Today" StatCard with a "Jobs per Source" card showing LinkedIn/Indeed/InfoJobs counts from `platform_distribution`. New `JobSourceBreakdown` component with per-source badges and counts.
5. **Favorites page**: Rewrite `/jobs/page.tsx` to read from `useFavorites`. Show compact grid of favorited jobs. Empty state with message. Remove search bar and backend fetch.
6. **Job detail**: Keep `/jobs/[id]` as-is. `JobDetailContent` renders markdown descriptions. No structural changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/package.json` | Modified | Add `react-markdown`, `remark-gfm`, `rehype-sanitize` |
| `src/components/jobs/JobDetailContent.tsx` | Modified | Markdown rendering instead of pre-line |
| `src/components/jobs/JobCard.tsx` | Modified | Add compact variant, external link, favorite button |
| `src/components/jobs/JobList.tsx` | Modified | Support compact grid mode |
| `src/hooks/useFavorites.ts` | **New** | localStorage favorites hook |
| `src/components/jobs/FavoriteButton.tsx` | **New** | Heart toggle button |
| `src/components/dashboard/JobSourceBreakdown.tsx` | **New** | Per-source count display |
| `src/components/dashboard/StatsCardsRow.tsx` | Modified | Replace "Jobs Today" with source breakdown |
| `src/app/page.tsx` | Modified | Grid layout for compact cards |
| `src/app/jobs/page.tsx` | Modified | Favorites-only page |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `react-markdown` XSS via description text | Low | `rehype-sanitize` blocks all raw HTML; description field is internal |
| localStorage quota exceeded | Low | Store only essential fields; cap at 200 jobs |
| Back button UX with favorites | Low | Keep URL-driven navigation; favorites are client-only state |
| Regression in existing pages | Medium | Do NOT touch Search or Settings; `npm run typecheck` + `npm test` gate |

## Rollback Plan

- `git checkout HEAD -- frontend/src/` reverts all component changes
- `git checkout HEAD -- frontend/package.json` reverts dependency changes
- `rm -rf frontend/node_modules && npm install` reinstalls without new deps
- Favorites are in localStorage — clear via DevTools, no persistence impact

## Dependencies

- `react-markdown` (^10) — Markdown rendering
- `remark-gfm` — GFM tables/strikethrough
- `rehype-sanitize` — HTML sanitization

## Success Criteria

- [ ] `npm run build` + `npm run typecheck` pass with strict TS
- [ ] Job descriptions render bold, lists, paragraphs, sections from markdown
- [ ] Favorite toggle appears on JobCard, persists across reloads (localStorage)
- [ ] Dashboard cards show in 3-column grid, each has external link to real job URL
- [ ] "Jobs per Source" replaces "Jobs Today" in stat row
- [ ] `/jobs` shows only favorited jobs, has empty state when none saved
- [ ] Search page unchanged (no favorites, no markdown, original layout)
