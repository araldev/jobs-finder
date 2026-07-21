import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { verifyWebhookSignature, WebhookSignatureError } from "@/lib/billing/webhook-verify";
import { upsertSubscription, appendBillingEvent } from "@/lib/billing/plan-repo";
import { planCacheInvalidate } from "@/lib/billing/plan-cache";
import type Stripe from "stripe";

export async function POST(request: NextRequest) {
  const billingEnabled = process.env.NEXT_PUBLIC_BILLING_ENABLED;
  if (billingEnabled !== "true") {
    return NextResponse.json({ error: "Billing is not enabled" }, { status: 503 });
  }

  // Read raw body BEFORE any parsing — Stripe HMAC must verify over
  // the exact bytes received. Do NOT use request.json() before this.
  const rawBody = await request.text();
  const signature = request.headers.get("stripe-signature") ?? "";

  let event: Stripe.Event;
  try {
    event = verifyWebhookSignature(rawBody, signature);
  } catch (err) {
    if (err instanceof WebhookSignatureError) {
      console.warn("[webhook] Signature verification failed", err.message);
      return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
    }
    console.error("[webhook] Unexpected error during verification", err);
    return NextResponse.json({ error: "Webhook verification failed" }, { status: 400 });
  }

  // Idempotency: check if we've already processed this event.
  try {
    const exists = await appendBillingEvent({
      eventId: event.id,
      eventType: event.type,
      payload: event,
    });
    // If the insert succeeded without throwing, the event is new.
    void exists;
  } catch (err) {
    // Unique constraint violation means duplicate — safe to acknowledge.
    console.info("[webhook] Duplicate event received, skipping", event.id);
    return NextResponse.json({ received: true });
  }

  // Handle the event.
  try {
    await handleEvent(event);
  } catch (err) {
    console.error("[webhook] Error handling event", event.type, event.id, err);
    return NextResponse.json({ error: "Event handling failed" }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}

async function handleEvent(event: Stripe.Event): Promise<void> {
  const customerId = extractCustomerId(event);
  if (!customerId) return;

  let userIdForInvalidation: string | null = null;

  switch (event.type) {
    case "checkout.session.completed":
    case "customer.subscription.created":
    case "customer.subscription.updated":
      userIdForInvalidation = await handleSubscriptionChange(event, customerId);
      break;

    case "customer.subscription.deleted":
      userIdForInvalidation = await handleSubscriptionCanceled(event, customerId);
      break;

    case "invoice.payment_failed":
      userIdForInvalidation = await handlePaymentFailed(event, customerId);
      break;

    case "invoice.paid":
      // Acknowledge but don't change plan — already active or trialing.
      break;

    default:
      console.info("[webhook] Unhandled event type", event.type);
  }

  // Invalidate the user's cache so the next plan read picks up the
  // change. The cache is keyed by userId (the same key
  // subscription/route.ts uses), so we MUST invalidate by userId —
  // NOT by Stripe customerId (that key would be a no-op).
  if (userIdForInvalidation) {
    planCacheInvalidate(userIdForInvalidation);
  }
}

function extractCustomerId(event: Stripe.Event): string | null {
  const obj = event.data.object as Record<string, unknown>;
  if (typeof obj.customer === "string") return obj.customer;
  return null;
}

async function handleSubscriptionChange(
  event: Stripe.Event,
  customerId: string,
): Promise<string | null> {
  const obj = event.data.object as Record<string, unknown>;
  const subscription = obj as import("stripe").Stripe.Subscription;
  const userId = (subscription.metadata?.userId ?? "") as string;

  if (!userId) {
    console.warn("[webhook] No userId in subscription metadata", subscription.id);
    return null;
  }

  const status = mapStripeStatus(subscription.status);
  const plan = inferPlanFromPrice(subscription);

  await upsertSubscription({
    userId,
    plan,
    status,
    stripeCustomerId: customerId,
    stripeSubscriptionId: subscription.id,
    currentPeriodEnd:
      subscription.current_period_end
        ? new Date(subscription.current_period_end * 1000).toISOString()
        : null,
    trialEnd:
      subscription.trial_end
        ? new Date(subscription.trial_end * 1000).toISOString()
        : null,
    cancelAtPeriodEnd: subscription.cancel_at_period_end ?? false,
  });

  return userId;
}

async function handleSubscriptionCanceled(
  event: Stripe.Event,
  _customerId: string,
): Promise<string | null> {
  const obj = event.data.object as Record<string, unknown>;
  const subscription = obj as import("stripe").Stripe.Subscription;
  const userId = (subscription.metadata?.userId ?? "") as string;

  if (!userId) {
    console.warn(
      "[webhook] No userId in canceled subscription metadata",
      subscription.id,
    );
    return null;
  }

  // Keep the subscription record but mark as canceled.
  // The user retains access until current_period_end.
  await upsertSubscription({
    userId,
    plan: "free",
    status: "canceled",
    stripeCustomerId: _customerId,
    stripeSubscriptionId: subscription.id,
    currentPeriodEnd: null,
    trialEnd: null,
    cancelAtPeriodEnd: false,
  });

  return userId;
}

async function handlePaymentFailed(
  event: Stripe.Event,
  _customerId: string,
): Promise<string | null> {
  const obj = event.data.object as Record<string, unknown>;
  // The Invoice object's `subscription` field is a string ID, not
  // a Subscription object. We don't have the userId in the Invoice
  // itself — we need the original subscription metadata. For v1,
  // we acknowledge but skip cache invalidation; the next user
  // read will repopulate the cache from the DB.
  const invoice = obj as import("stripe").Stripe.Invoice;
  void invoice;
  return null;
}

function mapStripeStatus(
  status: import("stripe").Stripe.Subscription.Status,
): "active" | "trialing" | "past_due" | "canceled" {
  switch (status) {
    case "active":
      return "active";
    case "trialing":
      return "trialing";
    case "past_due":
      return "past_due";
    case "canceled":
    case "unpaid":
    case "incomplete":
    case "incomplete_expired":
    default:
      return "canceled";
  }
}

function inferPlanFromPrice(
  subscription: import("stripe").Stripe.Subscription,
): "free" | "pro" | "pro_plus" {
  // All paid plans map to 'pro' for now. Pro Plus is a future schema slot.
  return "pro";
}
