"use client";

import { useQuery } from "@tanstack/react-query";
import type { HistoryResponse } from "@/types/job";

interface UseJobsArgs {
  q?: string;
  location?: string;
  limit?: number;
  sources?: string;
  enabled?: boolean;
}

export function useJobs(args: UseJobsArgs = {}) {
  const params = new URLSearchParams();
  if (args.q) params.set("q", args.q);
  if (args.location) params.set("location", args.location);
  if (args.limit) params.set("limit", String(args.limit));
  if (args.sources) params.set("sources", args.sources);
  const qs = params.toString();

  return useQuery<HistoryResponse>({
    queryKey: ["jobs", args.q, args.location, args.limit, args.sources],
    queryFn: async () => {
      const res = await fetch(`/api/jobs${qs ? `?${qs}` : ""}`);
      if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status}`);
      return res.json();
    },
    enabled: args.enabled ?? true,
  });
}
