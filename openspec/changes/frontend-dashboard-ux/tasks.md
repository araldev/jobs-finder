# Tasks: Frontend Dashboard UX Overhaul

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Foundation

- [ ] 1.1 Pin `react-markdown@10.1.1` + `remark-gfm@4.0.1` in `frontend/package.json`
- [ ] 1.2 Create `frontend/src/hooks/useFavorites.ts` — localStorage CRUD, storage event listener, full Job array

## Phase 2: New Components

- [ ] 2.1 Create `frontend/src/components/jobs/FavoriteButton.tsx` — Heart/HeartOff icon, tooltip, sonner toast, sm/md size
- [ ] 2.2 Create `frontend/src/components/jobs/CompactJobCard.tsx` — p-3, line-clamp-1, inline date, ExternalLink, spring animation
- [ ] 2.3 Create `frontend/src/components/dashboard/JobSourceBreakdown.tsx` — 3 platform stat cards from `useStats().platform_distribution`

## Phase 3: Modify Existing Components

- [ ] 3.1 Add `FavoriteButton` to `frontend/src/components/jobs/JobCard.tsx` with `stopPropagation` inside Link
- [ ] 3.2 Replace `<p whitespace-pre-line>` with `<ReactMarkdown remarkPlugins={[remarkGfm]}>` + `.markdown-prose` classes in `JobDetailContent.tsx`
- [ ] 3.3 Remove "Jobs Today" card, switch `lg:grid-cols-4` → `lg:grid-cols-3` in `StatsCardsRow.tsx`

## Phase 4: Page Wiring

- [ ] 4.1 Update `frontend/src/app/page.tsx` — insert `JobSourceBreakdown` above SearchBar, replace `JobList` with responsive `CompactJobCard` grid + `ExternalLink`
- [ ] 4.2 Rewrite `frontend/src/app/jobs/page.tsx` — `useFavorites` + client-side search filter + `CompactJobCard` grid + `EmptyState`

## Phase 5: Testing

- [ ] 5.1 Write unit tests for `useFavorites` — add, remove, corrupted JSON, cross-tab storage event, empty init
- [ ] 5.2 Write component tests for `FavoriteButton` — favorited/unfavorited render, click toggles, toast fires
- [ ] 5.3 Write component tests for `CompactJobCard` — compact layout, ExternalLink, skeleton, spring animation
- [ ] 5.4 Write component tests for `JobSourceBreakdown` — 3 platforms render, loading skeleton, error + refetch
- [ ] 5.5 Write component test for `JobDetailContent` — markdown headings/lists/links render, null description omits

## Phase 6: Verification

- [ ] 6.1 `npm run typecheck` — fix all TypeScript errors
- [ ] 6.2 `npm run lint` — fix all lint issues
- [ ] 6.3 `npm run test` — all 15+ tests pass
- [ ] 6.4 `npm run build` — production build succeeds
