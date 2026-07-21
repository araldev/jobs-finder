"use client";

import { useQuery } from "@tanstack/react-query";
import type { Subscription, SubscriptionResponse } from "@/types/billing";

async function fetchSubscription(): Promise<Subscription> {
  const res = await fetch("/api/billing/subscription");
  if (!res.ok) {
    // Return a default free subscription on error so the UI doesn't break.
    return {
      plan: "free",
      status: "active",
      currentPeriodEnd: null,
      trialEnd: null,
      cancelAtPeriodEnd: false,
      stripeCustomerId: null,
    };
  }
  const data: SubscriptionResponse = await res.json();
  return data.subscription;
}

export function useUserPlan() {
  return useQuery({
    queryKey: ["plan"],
    queryFn: fetchSubscription,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}
