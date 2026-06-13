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
