import { LoadingHint } from "@/components/shared/LoadingHint";

/**
 * DashboardSkeleton — REQ-PDPRSC-002.
 *
 * Suspense fallback for the dashboard route's jobs-grid island.
 * BYTE-IDENTICAL to the legacy `isLoading` skeleton that lived
 * at `dashboard/page.tsx` (pre-commit-6):
 *
 *   - 6 skeleton items (matches `useJobsInfinite` default
 *     `pageSize: 20` × visible grid of 3 cols × 2 rows).
 *   - Responsive grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`.
 *   - Each item: `h-[120px] rounded-xl skeleton-shimmer`.
 *   - `<LoadingHint />` rendered below the grid.
 *
 * Why byte-identical matters (design #618 R-NEW-2):
 * the page's CLS budget is 0.002. If the Suspense fallback's
 * row height drifted from the post-load content's row height,
 * the swap from skeleton → real cards would shift the layout
 * and CLS would spike. sdd-verify gates on CLS<0.1; staying at
 * 0.002 requires the fallback dimensions to match exactly.
 *
 * This component is a Server Component (no `"use client"`) so
 * it streams in the initial HTML payload alongside the rest of
 * the RSC tree.
 */
export function DashboardSkeleton() {
  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="skeleton-shimmer h-[120px] rounded-xl"
          />
        ))}
      </div>
      <LoadingHint />
    </>
  );
}