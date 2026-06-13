# Design: Frontend Dashboard UX Overhaul

## Technical Approach

Client-only architectural changes to the Next.js frontend. No backend changes. Four work areas: (1) localStorage favorites via a standalone hook, (2) compact card variant, (3) markdown description rendering, (4) dashboard + /jobs page restructuring.

## Architecture Decisions

| Decision | Option | Tradeoff | Chosen |
|----------|--------|----------|--------|
| CompactJobCard | `compact` prop on JobCard vs separate component | Prop adds conditionals in layout, animation, and structure. Separate component duplicates animation boilerplate but keeps each variant clean. | **Separate component** — the layout diff (p-3 vs p-4, no border-t, no Calendar icon, inline date, ExternalLink button) is deep enough that conditionals would hurt readability. |
| Favorites state | React context vs hook reading localStorage directly | Context adds provider wrapping + boilerplate. Hook is simpler but doesn't sync across tabs automatically. | **Standalone hook** — adding a provider just for favorites is over-engineering. The `storage` event listener handles cross-tab sync. |
| Markdown styling | Tailwind Typography (`@tailwindcss/typography`) vs custom classes | Typography plugin is convenient but generates hardcoded color values, not CSS var tokens. Custom classes respect dark/light tokens. | **Custom prose classes** — the design system uses CSS variables for all colors; the plugin can't use them. |
| StatsCardsRow | Keep 4 cards vs drop "Jobs Today" | Jobs Today is redundant with per-source breakdown. Drops to 3 cards (grid-cols-3). | **Drop to 3 cards** — `total_jobs`, `active_platforms`, `last_sync`. |
| Favorites page search | Keep SearchBar on /jobs for filtering | Search within favorites lets users find saved jobs quickly. Tradeoff: one extra dependency on client-side filtering. | **Keep SearchBar** — filters the in-memory favorites array by title/company. |

## Data Flow

```ascii
localStorage "jobs-finder-favorites"
        ↕ (getItem/setItem + JSON.parse/stringify)
  useFavorites() hook  ── used by ──→ FavoriteButton
        ↕                              (in JobCard / CompactJobCard)
  toggleFavorite(job) → update state → setItem → sonner toast

Dashboard page (/):
  useStats() → StatsCardsRow (3 cards) + JobSourceBreakdown (3 platform cards)
  useJobsInfinite() → SearchBar → CompactJobCard[] grid → ExternalLink → new tab

Favorites page (/jobs):
  useFavorites() → SearchBar (client-filter) → CompactJobCard[] grid → EmptyState

Job detail (/jobs/[id]):
  useJobDetail(id) → JobDetailContent → react-markdown → rendered HTML
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `package.json` | Modify | Pin `react-markdown@10.1.1` + `remark-gfm@4.0.1` |
| `src/hooks/useFavorites.ts` | Create | localStorage hook: `favorites`, `isFavorite`, `toggleFavorite`, `removeFavorite` |
| `src/components/jobs/FavoriteButton.tsx` | Create | Heart icon (lucide Heart/HeartOff), tooltip, sonner toast |
| `src/components/jobs/CompactJobCard.tsx` | Create | p-3, single-line title, no divider, inline date, ExternalLink (lucide ExternalLink), FavoriteButton |
| `src/components/dashboard/JobSourceBreakdown.tsx` | Create | 3 stat cards using `useStats() → platform_distribution` |
| `src/components/jobs/JobCard.tsx` | Modify | Add `FavoriteButton` inside the Link wrapper (stopPropagation on click) |
| `src/components/jobs/JobDetailContent.tsx` | Modify | Replace `<p whitespace-pre-line>` with `<ReactMarkdown>` + custom prose classes |
| `src/app/page.tsx` | Modify | Add JobSourceBreakdown, replace JobList with CompactJobCard grid, remove RightSidebar dependency gap |
| `src/app/jobs/page.tsx` | Modify | Rewrite as Favorites page using useFavorites + client-filtered CompactJobCard grid |
| `src/components/dashboard/StatsCardsRow.tsx` | Modify | Remove "Jobs Today" card, `lg:grid-cols-4` → `lg:grid-cols-3` |

## Interfaces / Contracts

```typescript
// src/hooks/useFavorites.ts
interface UseFavoritesReturn {
  favorites: Job[];
  isFavorite: (id: string) => boolean;
  toggleFavorite: (job: Job) => void;
  removeFavorite: (id: string) => void;
}

// src/components/jobs/FavoriteButton.tsx
interface FavoriteButtonProps {
  job: Job;
  /** Override size. Default: sm (h-8 w-8). */
  size?: "sm" | "md";
  /** Override className for positioning */
  className?: string;
}
```

## State Machines

**useFavorites**: `ready`. On init, `try { JSON.parse(localStorage.getItem(...)) } catch { [] }`. On `toggleFavorite`, mutate local state + `setItem`. Listens to `window "storage"` for cross-tab sync.

**FavoriteButton**: `idle → hovered (tooltip: "Save/Remove") → clicked (toggle + toast) → idle`. Visual: `Heart` (filled) / `Heart` (outline with `fill="none"`).

**CompactJobCard**: Same spring animation as JobCard (`bounce: 0.1`, `delay: index * 0.06`, `layout`) but `p-3`, title `text-sm line-clamp-1`, no `border-t`, date inline with company row.

## Markdown Prose Classes

```css
/* globals.css — added alongside existing tokens */
.markdown-prose h1 { @apply font-display text-lg font-bold mb-2; }
.markdown-prose h2 { @apply font-display text-base font-semibold mb-2; }
.markdown-prose h3 { @apply font-display text-sm font-semibold mb-1; }
.markdown-prose p  { @apply text-sm leading-relaxed text-muted-foreground mb-3; }
.markdown-prose ul { @apply list-disc pl-5 mb-3 space-y-1; }
.markdown-prose ol { @apply list-decimal pl-5 mb-3 space-y-1; }
.markdown-prose li { @apply text-sm text-muted-foreground; }
.markdown-prose a  { @apply text-primary underline underline-offset-2 hover:text-primary/80; }
.markdown-prose code { @apply rounded bg-muted px-1.5 py-0.5 text-xs font-mono; }
.markdown-prose pre { @apply rounded-xl bg-muted p-4 mb-3 overflow-x-auto; }
```

All tokens resolve through CSS variables — no hardcoded colors.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `useFavorites` | Mock `localStorage.getItem/setItem`. Test add, remove, corrupted JSON, cross-tab storage event. |
| Unit | `FavoriteButton` | `@testing-library/react`. Render favorited/unfavorited, click toggles state, toast fires. |
| Unit | `CompactJobCard` | Render with mock Job, verify compact layout (p-3, line-clamp-1, no Calendar icon, ExternalLink present). |
| Unit | `JobSourceBreakdown` | Render with mock `platform_distribution`, error state with refetch. |
| Component | Markdown rendering | Render `JobDetailContent` with markdown string, verify headings/lists/links render. Null description omits section. |
| Integration | Dashboard page | Render with mock data, verify 3-column grid on wide viewport. |
| Integration | Favorites page | Render with mock favorites, verify grid + empty state. |

## Migration / Rollout

No migration required. Favorites data is purely client-side (localStorage). Markdown rendering is a visual-only change — existing descriptions render identically (they're plain text, which is valid markdown). Old "Jobs Today" stat card is removed.

## Open Questions

- None resolved. The spec covers all edge cases.
