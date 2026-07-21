export type PlanName = "free" | "pro" | "pro_plus";

export type SubscriptionStatus =
  | "active"
  | "trialing"
  | "past_due"
  | "canceled";

export interface Subscription {
  plan: PlanName;
  status: SubscriptionStatus;
  currentPeriodEnd: string | null;
  trialEnd: string | null;
  cancelAtPeriodEnd: boolean;
  stripeCustomerId: string | null;
}

export interface Quota {
  plan: PlanName;
  cvUsed: number;
  cvLimit: number | "unlimited";
  cvRemaining: number | "unlimited";
  savedSearchesUsed: number;
  savedSearchesLimit: number | "unlimited";
  notificationsEnabled: boolean;
}

export interface CheckoutRequestBody {
  priceInterval: "monthly" | "annual";
}

export interface SubscriptionResponse {
  subscription: Subscription;
}

export interface CvQuotaResponse {
  used: number;
  limit: number | "unlimited";
  plan: PlanName;
}
