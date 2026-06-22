"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { PageTransition } from "@/components/layout/PageTransition";
import { StatsCardsRow } from "@/components/dashboard/StatsCardsRow";
import { RightSidebar } from "@/components/dashboard/RightSidebar";
import { SearchBar } from "@/components/search/SearchBar";
import { LocationBar } from "@/components/search/LocationBar";
import { CompactJobCard } from "@/components/jobs/CompactJobCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { useJobsInfinite } from "@/hooks/useJobsInfinite";
import { usePlatformConfig } from "@/hooks/usePlatformConfig";
import { useDebounce } from "@/hooks/useDebounce";
import { useOpenedJobs } from "@/lib/chat-storage";

export default function DashboardPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [locationQuery, setLocationQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 400);
  const debouncedLocation = useDebounce(locationQuery, 400);
  const { enabledSources, allEnabled } = usePlatformConfig();
  const openedJobIds = useOpenedJobs();

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
    <PageTransition>

      {/* Stats row */}
      <StatsCardsRow />

      {/* Main content: two columns */}
      <div className="mt-6 flex gap-6">
        {/* Left column: search + jobs */}
        <div className="flex-1 min-w-0">
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
                    <CompactJobCard key={job.id} job={job} index={i} openedJobIds={openedJobIds} />
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

        {/* Right sidebar */}
        <RightSidebar />
      </div>
    </PageTransition>
  );
}
