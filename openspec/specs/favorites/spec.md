# favorites Specification

**Change**: `frontend-dashboard-ux` • **Type**: NEW

## Purpose

Client-only job bookmarking via `localStorage`. No backend persistence.

## Requirements

### REQ-FAV-001: localStorage favorites hook

The system MUST expose a `useFavorites` hook that reads/writes `jobs-finder-favorites` in `localStorage`. The hook MUST store full `Job` objects keyed by ID and expose: `favorites`, `isFavorite(id)`, `toggleFavorite(job)`, `removeFavorite(id)`.

- **SC-FAV-001**: Given `toggleFavorite(job)` is called, the job is added to the favorites array and persisted to `localStorage`.
- **SC-FAV-002**: Given `toggleFavorite(job)` is called on an already-favorited job, the job is removed from the array.
- **SC-FAV-003**: Given `localStorage` is empty or corrupted on mount, the hook returns an empty array gracefully.

### REQ-FAV-002: FavoriteButton UI

`FavoriteButton` MUST render a heart icon (lucide `Heart`), filled when favorited and outlined when not. Clicking MUST fire a sonner toast (`richColors`): "Added to favorites" / "Removed from favorites".

- **SC-FAV-004**: Given the user hovers the button, a tooltip shows "Save to favorites" or "Remove from favorites".
- **SC-FAV-005**: Given the user clicks an unfavorited job, the icon fills solid and a success toast appears.

### REQ-FAV-003: Favorites page at `/jobs`

`/jobs` MUST display favorited jobs in a responsive compact grid (1/2/3 cols). Header MUST show "Favorite Jobs" with count. When empty, an `EmptyState` with "No favorites yet" MUST render.

- **SC-FAV-006**: Given the user has 3 favorited jobs, the grid shows 3 compact cards with source badges.
- **SC-FAV-007**: Given no jobs are favorited, an empty state with illustration and "No favorites yet" renders.

## Frontend i18n dependency (added in `feat-frontend-i18n`, applied 2026-06-22)

This capability was originally declared i18n-out-of-scope. After the v1 i18n cycle shipped, every favorites component was migrated to `useTranslations('Favorites.*')` and `useTranslations('Jobs.*')`. Concretely:

- **`FavoriteButton`** (REQ-FAV-002) consumes `Jobs.favorite.{add,remove}` keys and emits translated sonner toasts (verified bilingual via the `en-locale` parity test added in cycle 2).
- **Favorites page header** (REQ-FAV-003) consumes `Favorites.header.title` and `Favorites.header.count` with ICU pluralization for the job count.
- **Favorites empty state** (REQ-FAV-003 SC-FAV-007) consumes `Favorites.emptyState.{title,description}`.
- **`useFavorites` hook** (REQ-FAV-001) is locale-agnostic — it stores Job IDs and reads them back unchanged; UI strings live in the consuming components.

The full translation contract lives in **`openspec/specs/frontend-i18n/spec.md`**. All REQs from this capability now implicitly depend on the i18n contract being honored — a missing translation key surfaces as a `"Namespace.path"` literal (per next-intl 4.x `useTranslations` convention) which the CI grep audit (`pnpm run lint:i18n`) flags.

No new REQs added to this capability — the i18n translation work is enforced by the existing REQs (which mandate correct UI rendering) rather than new i18n-specific REQs.
