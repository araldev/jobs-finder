"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState, useDeferredValue, useMemo } from "react";
import { fetchJobs } from "@/lib/api";
import type { SearchResult } from "@/lib/types";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

/** Default search applied on first mount (REQ-DQ-001). */
export const DEFAULT_KEYWORDS = "Software Engineer";
export const DEFAULT_LOCATION = "Madrid";
export const DEFAULT_LIMIT = 20;
export const DEBOUNCE_MS = 400;
export const STALE_TIME_MS = 60_000;

export interface UseDebouncedJobsSearchArgs {
  readonly initialKeywords?: string;
  readonly initialLocation?: string;
  readonly limit?: number;
}

export interface UseDebouncedJobsSearchResult {
  readonly keywords: string;
  readonly location: string;
  readonly setKeywords: (value: string) => void;
  readonly setLocation: (value: string) => void;
  readonly resetToDefault: () => void;
  readonly data: SearchResult | undefined;
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly refetch: () => void;
}

/**
 * Drives the search input → debounce → fetch pipeline. Owns the
 * raw `keywords` and `location` strings (controlled inputs in
 * SearchBar), the debounced variants, and the React Query
 * subscription to /api/jobs. The debounce + useDeferredValue
 * double-buffer keeps the input snappy on slow networks.
 */
export function useDebouncedJobsSearch(
  args: UseDebouncedJobsSearchArgs = {},
): UseDebouncedJobsSearchResult {
  const initialKeywords = args.initialKeywords ?? DEFAULT_KEYWORDS;
  const initialLocation = args.initialLocation ?? DEFAULT_LOCATION;
  const limit = args.limit ?? DEFAULT_LIMIT;

  const [keywords, setKeywords] = useState(initialKeywords);
  const [location, setLocation] = useState(initialLocation);

  const debouncedKeywords = useDebouncedValue(keywords, DEBOUNCE_MS);
  const debouncedLocation = useDebouncedValue(location, DEBOUNCE_MS);

  // useDeferredValue lets React prioritize the typing state over
  // the network round-trip without blocking paint.
  const deferredKeywords = useDeferredValue(debouncedKeywords);
  const deferredLocation = useDeferredValue(debouncedLocation);

  const queryKey = useMemo(
    () => ["jobs", deferredKeywords, deferredLocation, limit] as const,
    [deferredKeywords, deferredLocation, limit],
  );

  const query = useQuery<SearchResult>({
    queryKey,
    queryFn: () =>
      fetchJobs({
        keywords: deferredKeywords,
        location: deferredLocation,
        limit,
      }),
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
  });

  return {
    keywords,
    location,
    setKeywords,
    setLocation,
    resetToDefault: () => {
      setKeywords(initialKeywords);
      setLocation(initialLocation);
    },
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
