"use client";

import { useMemo } from "react";
import { useDebouncedJobsSearch } from "@/hooks/useDebouncedJobsSearch";
import { SearchBar } from "./SearchBar";
import { ResultsGrid } from "./ResultsGrid";
import { SearchSkeletons } from "./Skeletons";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { useJobsOverride } from "@/components/layout/JobsOverrideContext";
import { Button } from "@/components/ui/button";
import { XIcon } from "lucide-react";

/**
 * Top-level search section. Owns the form, the React Query
 * subscription, and the rendering of the four states (loading,
 * success, empty, error). When the chat overrides the results
 * via JobsOverrideContext, the override replaces the query
 * result and a "Clear filter" button appears next to the bar.
 */
export function SearchSection(): React.ReactElement {
  const search = useDebouncedJobsSearch();
  const { override, clearOverride } = useJobsOverride();

  const jobs = useMemo(() => {
    if (override !== null) return override;
    return search.data?.jobs ?? [];
  }, [override, search.data]);

  const hasOverride = override !== null;

  return (
    <section className="flex flex-col gap-5" aria-label="Resultados de búsqueda">
      <div className="flex flex-col gap-3">
        <SearchBar
          keywords={search.keywords}
          location={search.location}
          onKeywordsChange={search.setKeywords}
          onLocationChange={search.setLocation}
          isLoading={search.isLoading}
        />
        {hasOverride ? (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-xs text-accent-foreground">
            <span>
              Mostrando los resultados filtrados por el chat. Los demás
              puestos no aparecen.
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearOverride}
              className="h-7 gap-1 px-2 text-accent"
            >
              <XIcon aria-hidden className="size-3.5" />
              Limpiar filtro
            </Button>
          </div>
        ) : null}
      </div>

      <ResultsOrFallback
        isLoading={search.isLoading && search.data === undefined}
        isError={search.isError}
        error={search.error}
        jobs={jobs}
        hasQuery={search.keywords.trim().length > 0 || search.location.trim().length > 0}
        onPickPrompt={(keywords, location) => {
          search.setKeywords(keywords);
          search.setLocation(location);
          clearOverride();
        }}
        onRetry={() => {
          void search.refetch();
        }}
      />
    </section>
  );
}

interface ResultsOrFallbackProps {
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly jobs: readonly import("@/lib/types").Job[];
  readonly hasQuery: boolean;
  readonly onPickPrompt: (keywords: string, location: string) => void;
  readonly onRetry: () => void;
}

function ResultsOrFallback({
  isLoading,
  isError,
  error,
  jobs,
  hasQuery,
  onPickPrompt,
  onRetry,
}: ResultsOrFallbackProps): React.ReactElement {
  if (isLoading) {
    return <SearchSkeletons />;
  }
  if (isError) {
    return <ErrorState error={error} onRetry={onRetry} />;
  }
  if (jobs.length === 0) {
    return (
      <EmptyState
        keywords={hasQuery ? "" : ""}
        onPickPrompt={onPickPrompt}
      />
    );
  }
  return <ResultsGrid jobs={jobs} />;
}
