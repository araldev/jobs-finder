import "server-only";

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getSubscriptionForUser } from "@/lib/billing/plan-repo";
import { planCacheGet, planCacheSet } from "@/lib/billing/plan-cache";
import { DEFAULT_FREE_SUBSCRIPTION } from "@/lib/billing/plans";
import type { Subscription } from "@/types/billing";

const DEFAULT_FREE_SUBSCRIPTION: Subscription = {
  plan: "free",
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
    return NextResponse.json({ subscription: DEFAULT_FREE_SUBSCRIPTION });
  }

  const userId = session.user.id;

  // Cache hit.
  const cached = planCacheGet(userId);
  if (cached) {
    return NextResponse.json({ subscription: cached });
  }

  // Cache miss — read from DB via service-role.
  try {
    const subscription =
      (await getSubscriptionForUser(userId)) ?? DEFAULT_FREE_SUBSCRIPTION;

    planCacheSet(userId, subscription);

    return NextResponse.json({ subscription });
  } catch (err) {
    console.error("[subscription] GET: failed to fetch subscription", err);
    return NextResponse.json({ subscription: DEFAULT_FREE_SUBSCRIPTION });
  }
}
