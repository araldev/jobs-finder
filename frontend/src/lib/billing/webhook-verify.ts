import "server-only";

import { getStripe } from "@/lib/billing/stripe-server";

export class WebhookSignatureError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WebhookSignatureError";
  }
}

export function verifyWebhookSignature(
  rawBody: string,
  signature: string,
): import("stripe").Stripe.Event {
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!webhookSecret) {
    throw new Error(
      "STRIPE_WEBHOOK_SECRET is not set. " +
        "Set it in frontend/.env.local to enable webhook verification.",
    );
  }

  try {
    const stripe = getStripe();
    return stripe.webhooks.constructEvent(rawBody, signature, webhookSecret);
  } catch (err) {
    if (err instanceof Error) {
      throw new WebhookSignatureError(
        `Webhook signature verification failed: ${err.message}`,
      );
    }
    throw new WebhookSignatureError("Webhook signature verification failed");
  }
}
