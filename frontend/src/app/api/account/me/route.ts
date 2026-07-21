import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/billing/stripe-server";
import { planCacheInvalidate } from "@/lib/billing/plan-cache";

export async function DELETE(_request: NextRequest) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = session.user.id;

  // Best-effort Stripe cancellation — log and continue on failure.
  // Stripe's `subscriptions.cancel()` requires the SUBSCRIPTION ID
  // (sub_xxx), NOT the customer ID. Selecting stripe_customer_id
  // here would always fail at the Stripe boundary.
  try {
    const { data: subscription } = await supabase
      .from("subscriptions")
      .select("stripe_subscription_id")
      .eq("user_id", userId)
      .maybeSingle();

    if (subscription?.stripe_subscription_id) {
      const stripe = getStripe();
      const canceled = await stripe.subscriptions.cancel(
        subscription.stripe_subscription_id,
      );
      console.info(
        "[account/me] Stripe subscription canceled",
        canceled.id,
        "for user",
        userId,
      );
    }
  } catch (err) {
    // Log but do not block — the deletion must proceed.
    console.warn(
      "[account/me] Stripe cancellation failed, proceeding with deletion",
      err,
    );
  }

  // Call the existing RPC (hard-delete user).
  const { error: rpcError } = await supabase.rpc("delete_current_user");

  if (rpcError) {
    console.error("[account/me] RPC deletion failed", rpcError);
    return NextResponse.json(
      { error: "Account deletion failed" },
      { status: 500 },
    );
  }

  // Clear the user's plan cache.
  planCacheInvalidate(userId);

  return new NextResponse(null, { status: 204 });
}
