import { Suspense } from "react";
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";

import { PageTransition } from "@/components/layout/PageTransition";
import { StatsCardsRow } from "@/components/dashboard/StatsCardsRow";
import { RightSidebar } from "@/components/dashboard/RightSidebar";
import { JobsGrid } from "@/components/dashboard/JobsGrid";
import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { fetchJobsHistory } from "@/lib/api-client";
import type { Locale } from "@/i18n/routing";

/**
 * DashboardPage — REQ-PDPRSC-002.
 *
 * Pure async React Server Component. Three architectural
 * properties:
 *
 *   1. **LCP date in server HTML.** `StatsCardsRow` awaits
 *      `fetchDashboardStats()` server-side, so the
 *      "15 de Jun de 2026" date inside the lastSync StatCard
 *      arrives in the initial HTML payload — no client JS
 *      required for first paint. Pre-commit-6 the LCP element
 *      was the LAST thing to paint, after `main-app.js`
 *      finished executing.
 *
 *   2. **`<HydrationBoundary>` for the jobs grid.** The page
 *      pre-fetches page 0 via `fetchJobsHistory({ limit: 20,
 *      offset: 0 })`, hydrates the React Query cache via
 *      `dehydrate(queryClient)`, and wraps `<JobsGrid />` in
 *      `<HydrationBoundary>`. The client's `useJobsInfinite`
 *      starts with page 0 already in the cache — no double
 *      fetch, no flash from empty → loaded.
 *
 *   3. **`<Suspense fallback={<DashboardSkeleton />}>`** wraps
 *      the HydrationBoundary. If the jobs fetch is slow, the
 *      user sees the skeleton (byte-identical to the legacy
 *      `isLoading` block, design R-NEW-2) instead of a blank
 *      grid — CLS stays at 0.002.
 *
 * `StatsCardsRow` + `RightSidebar` are NOT inside the Suspense
 * boundary: they're already in the server HTML payload and
 * don't need to suspend.
 *
 * **QueryClient scope** (design R-NEW-3): the QueryClient is
 * constructed INSIDE `DashboardPage`, NOT at module scope.
 * Module-scope state in RSC would leak between concurrent
 * requests — different users would share one React Query cache
 * for the duration of a single render pass.
 *
 * **Locale**: the `[locale]` dynamic route segment provides
 * `params.locale`, which is forwarded to `RightSidebar` as a prop
 * so date formatting respects the user's language. Since
 * `localePrefix: 'never'`, the locale is resolved by next-intl
 * middleware (cookie or Accept-Language header).
 */
export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}) {
  const { locale } = await params;
  // Per-request QueryClient. NEVER hoist to module scope.
  const queryClient = new QueryClient();

  // Pre-fetch page 0 so useJobsInfinite starts with cache populated.
  // The Next.js Data Cache (revalidate:60 in api-client.ts) absorbs
  // repeat hits at the L2 layer; the React.cache() wrapper in
  // api-client.ts dedupes within this single request scope.
  const firstPage = await fetchJobsHistory({ limit: 20, offset: 0 });
  queryClient.setQueryData(
    [
      "jobs",
      "list",
      JSON.stringify({ q: null, location: null, sources: null }),
      "infinite",
      20,
    ],
    {
      pages: [firstPage],
      pageParams: [0],
    },
  );

  return (
    <PageTransition>
      {/* Stats row — async RSC, server-fetched, LCP date in HTML */}
      <StatsCardsRow />

      {/* Main content: two columns */}
      <div className="mt-6 flex gap-6">
        {/* Left column: search + jobs (client island wrapped in Suspense) */}
        <div className="flex-1 min-w-0">
          <Suspense fallback={<DashboardSkeleton />}>
            <HydrationBoundary state={dehydrate(queryClient)}>
              <JobsGrid />
            </HydrationBoundary>
          </Suspense>
        </div>

        {/* Right sidebar — async RSC, server-fetched, locale-aware dates */}
        <RightSidebar locale={locale} />
      </div>
    </PageTransition>
  );
}