"use client";

import { useQuery } from "@tanstack/react-query";
import type { CvQuotaResponse } from "@/types/billing";

async function fetchCvQuota(): Promise<CvQuotaResponse> {
  const res = await fetch("/api/billing/cv-quota");
  if (!res.ok) {
    return { used: 0, limit: 3, plan: "free" };
  }
  return res.json() as Promise<CvQuotaResponse>;
}

export function useCvQuota() {
  return useQuery({
    queryKey: ["cv-quota"],
    queryFn: fetchCvQuota,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}
