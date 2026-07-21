import type { PlanName } from "@/types/billing";

export interface PlanConfig {
  name: PlanName;
  displayName: string;
  cvLimitPerMonth: number | "unlimited";
  savedSearchLimit: number | "unlimited";
  notificationsEnabled: boolean;
  enabled: boolean;
}

export const PLANS: Record<PlanName, PlanConfig> = {
  free: {
    name: "free",
    displayName: "Free",
    cvLimitPerMonth: 3,
    savedSearchLimit: 3,
    notificationsEnabled: false,
    enabled: true,
  },
  pro: {
    name: "pro",
    displayName: "Pro",
    cvLimitPerMonth: "unlimited",
    savedSearchLimit: 20,
    notificationsEnabled: true,
    enabled: true,
  },
  pro_plus: {
    name: "pro_plus",
    displayName: "Pro Plus",
    cvLimitPerMonth: "unlimited",
    savedSearchLimit: "unlimited",
    notificationsEnabled: true,
    enabled: false,
  },
};

export function getPlanConfig(plan: PlanName): PlanConfig {
  return PLANS[plan];
}
