import "server-only";

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { countCvAdaptedThisMonth, enforceCvQuota } from "@/lib/billing/quota";
import { PLANS } from "@/lib/billing/plans";
import { planCacheGet } from "@/lib/billing/plan-cache";
import type { CvQuotaResponse } from "@/types/billing";

const DEFAULT_FREE_SUBSCRIPTION = {
  plan: "free" as const,
  status: "active",
  currentPeriodEnd: null,
  trialEnd: null,
  cancelAtPeriodEnd: false,
  stripeCustomerId: null,
};

export async function GET() {
  const billingEnabled = process.env.NEXT_PUBLIC_BILLING_ENABLED;
  if (billingEnabled !== "true") {
    return NextResponse.json(
      { error: "Billing is not enabled" },
      { status: 503 },
    );
  }

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = session.user.id;

  // Use cached plan if available, otherwise default to free.
  const cached = planCacheGet(userId);
  const plan = cached?.plan ?? DEFAULT_FREE_SUBSCRIPTION.plan;
  const config = PLANS[plan];

  const used = await countCvAdaptedThisMonth(userId, supabase);
  const { allowed: _allowed, remaining, limit } = enforceCvQuota(plan, used);

  const response: CvQuotaResponse = {
    used,
    limit,
    plan,
  };

  return NextResponse.json(response);
}
