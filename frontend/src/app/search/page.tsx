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

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<FilterValues>({
    sources: [],
  });
  const { enabledSources, allEnabled } = usePlatformConfig();

  const debouncedQuery = useDebounce(query, 400);

  const effectiveSources =
    filters.sources.length > 0
      ? filters.sources.join(",")
      : allEnabled
        ? undefined
        : enabledSources.join(",");

  const { data, isLoading } = useJobs({
    q: debouncedQuery || undefined,
    limit: 100,
    sources: effectiveSources,
    location: filters.location || undefined,
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
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {filteredJobs.map((job, i) => (
            <JobCard key={job.id} job={job} index={i} />
          ))}
        </div>
      ) : (
        <EmptyState
          variant="no-results"
          title="No matching jobs"
          description={query ? `No results for "${query}"` : "No jobs match your filters"}
        />
      )}
    </PageTransition>
  );
}
