"use client";

import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import type { HistoryResponse } from "@/types/job";
import { sharedJobsArgs } from "./_queryKeys";

interface UseJobsInfiniteArgs {
  q?: string;
  location?: string;
  sources?: string;
  pageSize?: number;
  enabled?: boolean;
}

export function useJobsInfinite(args: UseJobsInfiniteArgs = {}) {
  const { q, location, sources, pageSize = 20, enabled = true } = args;

  return useInfiniteQuery<HistoryResponse>({
    queryKey: [
      "jobs",
      "list",
      sharedJobsArgs({ q, location, sources }),
      "infinite",
      pageSize,
    ],
    placeholderData: keepPreviousData,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (location) params.set("location", location);
      if (sources) params.set("sources", sources);
      params.set("limit", String(pageSize));
      params.set("page", String(pageParam));
      const qs = params.toString();

      const res = await fetch(`/api/jobs${qs ? `?${qs}` : ""}`);
      if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status}`);
      return res.json();
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage?.items?.length) return undefined;
      const totalFetched = allPages.reduce((sum, p) => sum + (p.items?.length ?? 0), 0);
      if (totalFetched >= lastPage.total) return undefined;
      return allPages.length;
    },
    enabled,
  });
}
