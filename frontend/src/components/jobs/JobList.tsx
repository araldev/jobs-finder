"use client";

import { useRef, useEffect, useCallback, type ReactNode } from "react";
import type { Job } from "@/types/job";
import { JobCard } from "./JobCard";
import { EmptyState } from "@/components/shared/EmptyState";

interface JobListProps {
  jobs: readonly Job[];
  loading?: boolean;
  /** Enable infinite-scroll mode. Requires fetchNextPage + hasNextPage. */
  fetchNextPage?: () => void;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
  /** Custom empty-state variant when there are no jobs. */
  emptyVariant?: "no-jobs" | "no-results" | "error";
  /** End-of-list content — shown when hasNextPage is false and jobs exist. */
  endMessage?: ReactNode;
}

export function JobList({
  jobs,
  loading,
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  emptyVariant = "no-jobs",
  endMessage,
}: JobListProps) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const handleIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry?.isIntersecting && hasNextPage && !isFetchingNextPage && fetchNextPage) {
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

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="skeleton-shimmer h-[140px] rounded-xl"
          />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) {
    return <EmptyState variant={emptyVariant} />;
  }

  return (
    <div className="space-y-3">
      {jobs.map((job, i) => (
        <JobCard key={job.id} job={job} index={i} />
      ))}

      {/* Loading more skeletons */}
      {isFetchingNextPage && (
        <div className="space-y-3 pt-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div
              key={`loading-${i}`}
              className="skeleton-shimmer h-[140px] rounded-xl"
            />
          ))}
        </div>
      )}

      {/* Sentinel element for IntersectionObserver */}
      {hasNextPage && (
        <div ref={sentinelRef} className="h-4" aria-hidden />
      )}

      {/* End-of-list message */}
      {!hasNextPage && !loading && endMessage && (
        <div className="py-6 text-center text-sm text-muted-foreground">
          {endMessage}
        </div>
      )}
    </div>
  );
}
