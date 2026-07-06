"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { SearchBar } from "@/components/search/SearchBar";
import { LocationBar } from "@/components/search/LocationBar";
import { CompactJobCard } from "@/components/jobs/CompactJobCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { useJobsInfinite } from "@/hooks/useJobsInfinite";
import { usePlatformConfig } from "@/hooks/usePlatformConfig";
import { useDebounce } from "@/hooks/useDebounce";
import { useOpenedJobs } from "@/lib/chat-storage";
import { FAVORITES_QUERY_KEY } from "@/hooks/useFavorites";

/**
 * JobsGrid — REQ-PDPRSC-002.
 *
 * Client island that owns the dashboard's search + infinite-scroll
 * jobs grid. Wraps the entire interactive surface (search inputs,
 * debounced queries, IntersectionObserver sentinel, `CompactJobCard`
 * loop) so the rest of the page can render as a Server Component
 * and stream in the initial HTML payload.
 *
 * The seed data for the first page comes from the parent RSC
 * (`dashboard/page.tsx`) via `<HydrationBoundary state={...}>` —
 * `useJobsInfinite` finds the page-0 entry already in the cache
 * and skips its initial fetch. Subsequent pages (1, 2, …) trigger
 * the same `/api/jobs` endpoint the legacy code did.
 */
export function JobsGrid() {
  const [searchQuery, setSearchQuery] = useState("");
  const [locationQuery, setLocationQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 400);
  const debouncedLocation = useDebounce(locationQuery, 400);
  const { enabledSources, allEnabled } = usePlatformConfig();
  const openedJobIds = useOpenedJobs();
  const queryClient = useQueryClient();

  // Sync the client cache with the server on every mount of this
  // page-level component. The server always renders an empty
  // favorites list (it has no localStorage), but the client's
  // React Query cache PERSISTS across navigations, so any
  // favorites the user toggled before navigating here would be in
  // the cache by the time this component first renders — causing
  // a hydration mismatch on the FavoriteButton's aria-label.
  // Clearing the cache here once per navigation guarantees the
  // first render on both sides matches. The queryFn re-fetches
  // and refills the cache before the user can interact.
  useEffect(() => {
    queryClient.removeQueries({ queryKey: FAVORITES_QUERY_KEY });
  }, [queryClient]);

  const sourcesParam = allEnabled ? undefined : enabledSources.join(",");

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useJobsInfinite({
    q: debouncedQuery || undefined,
    location: debouncedLocation || undefined,
    sources: sourcesParam,
    pageSize: 20,
  });

  const allJobs = data?.pages.flatMap((page) => page.items) ?? [];

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const handleIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry?.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage],
  );

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(handleIntersect, {
      rootMargin: "200px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [handleIntersect]);

  return (
    <div>
      {/* Search + Location filter (side by side) */}
      <div className="flex max-w-2xl flex-col gap-2 sm:flex-row">
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search jobs..."
        />
        <LocationBar
          value={locationQuery}
          onChange={setLocationQuery}
          placeholder="Location (e.g. malaga)"
        />
      </div>

      {/* Compact job cards grid with infinite scroll */}
      <div className="mt-4">
        {isLoading ? (
          // The Suspense fallback (DashboardSkeleton) renders the
          // skeleton during the initial server render. This branch
          // only fires on client-side re-fetches (filter changes)
          // AFTER hydration. We keep a minimal spinner here so the
          // grid doesn't pop empty during refetch.
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="skeleton-shimmer h-[120px] rounded-xl"
              />
            ))}
          </div>
        ) : isError ? (
          <EmptyState variant="error" />
        ) : allJobs.length === 0 ? (
          <EmptyState
            variant={debouncedQuery || debouncedLocation ? "no-results" : "no-jobs"}
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {allJobs.map((job, i) => (
                <CompactJobCard
                  key={job.id}
                  job={job}
                  index={i}
                  openedJobIds={openedJobIds}
                />
              ))}
            </div>

            {/* Loading more skeletons */}
            {isFetchingNextPage && (
              <>
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div
                      key={`loading-${i}`}
                      className="skeleton-shimmer h-[140px] rounded-xl"
                    />
                  ))}
                </div>
                <div className="py-3 text-center text-xs text-muted-foreground">
                  Loading more jobs…
                </div>
              </>
            )}

            {/* Sentinel for infinite scroll — always present when more pages */}
            {hasNextPage && (
              <div ref={sentinelRef} className="h-8" aria-hidden />
            )}

            {/* End-of-list message */}
            {!hasNextPage && allJobs.length > 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                No more jobs to load
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}