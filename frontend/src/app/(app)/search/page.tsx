"use client";

import { useState } from "react";
import { PageTransition } from "@/components/layout/PageTransition";
import { SearchBar } from "@/components/search/SearchBar";
import { FilterPanel, type FilterValues } from "@/components/search/FilterPanel";
import { JobCard } from "@/components/jobs/JobCard";
import { useJobs } from "@/hooks/useJobs";
import { usePlatformConfig } from "@/hooks/usePlatformConfig";
import { useDebounce } from "@/hooks/useDebounce";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useOpenedJobs } from "@/lib/chat-storage";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<FilterValues>({
    sources: [],
  });
  const { enabledSources, allEnabled } = usePlatformConfig();

  // Debounce ALL search params together so that location changes
  // do NOT reset the keyword debounce timer. This fixes the race
  // where typing a keyword then immediately selecting a location
  // would fire two separate requests: (q=old, location=new) and
  // (q=new, location=new) — the first one could overwrite results
  // briefly before the second one completes.
  const debouncedSearch = useDebounce(
    { q: query, location: filters.location },
    400,
  );
  const openedJobIds = useOpenedJobs();

  const effectiveSources =
    filters.sources.length > 0
      ? filters.sources.join(",")
      : allEnabled
        ? undefined
        : enabledSources.join(",");

  const { data, isLoading } = useJobs({
    q: debouncedSearch.q || undefined,
    limit: 100,
    sources: effectiveSources,
    location: debouncedSearch.location || undefined,
  });

  const filteredJobs = data?.items ?? [];

  return (
    <PageTransition>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold tracking-tight">Search Jobs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Find the perfect position
        </p>
      </div>

      {/* Search + Filters row */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex-1 max-w-md">
          <SearchBar
            value={query}
            onChange={setQuery}
            placeholder="Search by title, company..."
          />
        </div>
        <FilterPanel values={filters} onChange={setFilters} />
      </div>

      {/* Results grid */}
      {isLoading ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-[180px] rounded-xl" />
          ))}
        </div>
      ) : filteredJobs.length > 0 ? (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            {filteredJobs.length} jobs found
          </p>
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {filteredJobs.map((job, i) => (
              <JobCard
                key={job.id}
                job={job}
                index={i}
                openedJobIds={openedJobIds}
              />
            ))}
          </div>
        </>
      ) : query ? (
        <EmptyState
          variant="no-results"
          title="No matching jobs"
          description={`No results for "${query}"`}
        />
      ) : (
        <EmptyState
          variant="no-jobs"
          title="No jobs yet"
          description="Try adjusting your search"
        />
      )}
    </PageTransition>
  );
}
