import { createClient } from "@/lib/supabase/server";
import { PLANS } from "@/lib/billing/plans";
import type { PlanName } from "@/types/billing";

export function monthStartUtc(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
}

export async function countCvAdaptedThisMonth(
  userId: string,
  supabase?: Awaited<ReturnType<typeof createClient>>,
): Promise<number> {
  const client = supabase ?? (await createClient());
  const start = monthStartUtc();

  const { count, error } = await client
    .from("user_engagement")
    .select("id", { count: "exact", head: true })
    .eq("user_id", userId)
    .eq("event_type", "cv_adapted")
    .gte("created_at", start);

  if (error) {
    console.error("[quota] countCvAdaptedThisMonth error", error);
    return 0;
  }

  return count ?? 0;
}

export function enforceCvQuota(plan: PlanName, used: number): {
  allowed: boolean;
  remaining: number | "unlimited";
  limit: number | "unlimited";
} {
  const config = PLANS[plan];
  const limit = config.cvLimitPerMonth;

  if (limit === "unlimited") {
    return { allowed: true, remaining: "unlimited", limit };
  }

  const remaining = Math.max(0, limit - used);
  return { allowed: remaining > 0, remaining, limit };
}
