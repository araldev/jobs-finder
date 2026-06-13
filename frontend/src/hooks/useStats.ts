"use client";

import { useQuery } from "@tanstack/react-query";
import type { DashboardStats } from "@/types/stats";

export function useStats() {
  return useQuery<DashboardStats>({
    queryKey: ["stats"],
    queryFn: async () => {
      const res = await fetch("/api/stats");
      if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`);
      return res.json();
    },
  });
}
