import { getServiceRoleClient } from "@/lib/supabase/service-role";
import type { Subscription, SubscriptionStatus } from "@/types/billing";

interface DbSubscriptionRow {
  user_id: string;
  plan: string;
  status: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  current_period_end: string | null;
  trial_end: string | null;
  cancel_at_period_end: boolean;
  created_at: string;
  updated_at: string;
}

function rowToSubscription(row: DbSubscriptionRow): Subscription {
  return {
    plan: row.plan as Subscription["plan"],
    status: row.status as SubscriptionStatus,
    currentPeriodEnd: row.current_period_end,
    trialEnd: row.trial_end,
    cancelAtPeriodEnd: row.cancel_at_period_end,
    stripeCustomerId: row.stripe_customer_id,
  };
}

export async function getSubscriptionForUser(
  userId: string,
): Promise<Subscription | null> {
  const supabase = getServiceRoleClient();
  const { data, error } = await supabase
    .from("subscriptions")
    .select("*")
    .eq("user_id", userId)
    .maybeSingle();

  if (error) {
    console.error("[plan-repo] getSubscriptionForUser error", error);
    throw error;
  }

  if (!data) return null;
  return rowToSubscription(data as DbSubscriptionRow);
}

export async function upsertSubscription(params: {
  userId: string;
  plan: string;
  status: string;
  stripeCustomerId?: string | null;
  stripeSubscriptionId?: string | null;
  currentPeriodEnd?: string | null;
  trialEnd?: string | null;
  cancelAtPeriodEnd?: boolean;
}): Promise<void> {
  const supabase = getServiceRoleClient();
  const { error } = await supabase.from("subscriptions").upsert(
    {
      user_id: params.userId,
      plan: params.plan,
      status: params.status,
      stripe_customer_id: params.stripeCustomerId ?? null,
      stripe_subscription_id: params.stripeSubscriptionId ?? null,
      current_period_end: params.currentPeriodEnd ?? null,
      trial_end: params.trialEnd ?? null,
      cancel_at_period_end: params.cancelAtPeriodEnd ?? false,
      updated_at: new Date().toISOString(),
    },
    {
      onConflict: "user_id",
    },
  );

  if (error) {
    console.error("[plan-repo] upsertSubscription error", error);
    throw error;
  }
}

export async function appendBillingEvent(params: {
  eventId: string;
  eventType: string;
  payload: unknown;
}): Promise<void> {
  const supabase = getServiceRoleClient();
  const { error } = await supabase.from("billing_events").insert({
    event_id: params.eventId,
    event_type: params.eventType,
    payload: params.payload as Record<string, unknown>,
  });

  if (error) {
    console.error("[plan-repo] appendBillingEvent error", error);
    throw error;
  }
}

export async function billingEventExists(eventId: string): Promise<boolean> {
  const supabase = getServiceRoleClient();
  const { count, error } = await supabase
    .from("billing_events")
    .select("id", { count: "exact", head: true })
    .eq("event_id", eventId);

  if (error) {
    console.error("[plan-repo] billingEventExists error", error);
    return false;
  }

  // `head: true` makes `data` null and surfaces the row count via
  // `count`. The webhook handler treats count > 0 as "already
  // processed — safe to skip". A null count (no rows yet) maps to
  // `false` so the handler proceeds to INSERT.
  return (count ?? 0) > 0;
}
