import "server-only";

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/billing/stripe-server";

export async function POST() {
  const billingEnabled = process.env.NEXT_PUBLIC_BILLING_ENABLED;
  if (billingEnabled !== "true") {
    return NextResponse.json({ error: "Billing is not enabled" }, { status: 503 });
  }

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = session.user.id;

  // Get the Stripe customer ID from the user's subscription.
  const { data: subscription, error: subError } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("user_id", userId)
    .maybeSingle();

  if (subError || !subscription?.stripe_customer_id) {
    console.error("[portal] No Stripe customer for user", userId, subError);
    return NextResponse.json(
      { error: "No billing account found" },
      { status: 400 },
    );
  }

  const stripe = getStripe();
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";

  try {
    const portalSession = await stripe.billingPortal.sessions.create({
      customer: subscription.stripe_customer_id,
      return_url: `${baseUrl}/settings/billing`,
    });

    return NextResponse.redirect(portalSession.url, 302);
  } catch (err) {
    console.error("[portal] POST: Stripe error", err);
    return NextResponse.json(
      { error: "Failed to create portal session" },
      { status: 500 },
    );
  }
}
