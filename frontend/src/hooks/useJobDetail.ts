"use client";

import { useQuery } from "@tanstack/react-query";
import type { Job } from "@/types/job";

export function useJobDetail(id: string) {
  return useQuery<Job>({
    queryKey: ["jobs", id],
    queryFn: async () => {
      const res = await fetch(`/api/jobs/${id}`);
      if (!res.ok) throw new Error(`Failed to fetch job: ${res.status}`);
      return res.json();
    },
    enabled: !!id,
  });
}
