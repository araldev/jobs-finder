import "server-only";

import Stripe from "stripe";

let _stripe: Stripe | null = null;

export function getStripe(): Stripe {
  if (_stripe) return _stripe;

  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) {
    throw new Error(
      "STRIPE_SECRET_KEY is not set. " +
        "Set STRIPE_SECRET_KEY in frontend/.env.local to enable billing.",
    );
  }

  // Lazy singleton: the Stripe SDK is heavy and only constructed on
  // first use. The instance is memoized for the lifetime of the
  // process so subsequent calls (e.g. per webhook event) skip the
  // SDK init cost.
  _stripe = new Stripe(key, {
    apiVersion: "2025-05-28.basil",
  });

  return _stripe;
}
