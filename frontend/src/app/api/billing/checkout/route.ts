import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/billing/stripe-server";

export async function POST(request: NextRequest) {
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
  const userEmail = session.user.email;

  let priceInterval: "monthly" | "annual";
  try {
    const body = await request.json();
    priceInterval = body.priceInterval === "annual" ? "annual" : "monthly";
  } catch {
    priceInterval = "monthly";
  }

  const priceId =
    priceInterval === "monthly"
      ? process.env.STRIPE_PRICE_ID_PRO_MONTHLY
      : process.env.STRIPE_PRICE_ID_PRO_ANNUAL;

  if (!priceId) {
    console.error(
      "[checkout] Missing price ID for interval:",
      priceInterval,
    );
    return NextResponse.json(
      { error: "Stripe price not configured" },
      { status: 500 },
    );
  }

  const stripe = getStripe();
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";

  // Idempotency key: per-user, per-interval. Re-clicking Checkout
  // returns the existing session, preventing duplicate subscriptions.
  const idempotencyKey = `checkout-${userId}-${priceInterval}`;

  try {
    const params: import("stripe").Stripe.Checkout.SessionCreateParams = {
      mode: "subscription",
      payment_method_types: ["card"],
      line_items: [{ price: priceId, quantity: 1 }],
      customer_email: userEmail ?? undefined,
      metadata: { userId },
      subscription_data: {
        trial_period_days: 7,
        metadata: { userId },
      },
      success_url: `${baseUrl}/settings/billing?upgraded=1&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${baseUrl}/settings/billing?canceled=1`,
    };

    const checkoutSession = await stripe.checkout.sessions.create(params, {
      idempotencyKey,
    });

    return NextResponse.redirect(checkoutSession.url!, 302);
  } catch (err) {
    console.error("[checkout] POST: Stripe error", err);
    return NextResponse.json(
      { error: "Failed to create checkout session" },
      { status: 500 },
    );
  }
}
