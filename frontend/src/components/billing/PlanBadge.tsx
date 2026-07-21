"use client";

import { Badge } from "@/components/ui/badge";
import { useTranslations } from "next-intl";
import type { PlanName } from "@/types/billing";

const PLAN_BADGE_VARIANT: Record<PlanName, "default" | "secondary" | "outline"> = {
  free: "outline",
  pro: "default",
  pro_plus: "secondary",
};

interface PlanBadgeProps {
  plan: PlanName;
  className?: string;
}

export function PlanBadge({ plan, className }: PlanBadgeProps) {
  const t = useTranslations("Billing");

  return (
    <Badge variant={PLAN_BADGE_VARIANT[plan]} className={className}>
      {plan === "pro_plus" ? t("plans.proPlus") : t(`plans.${plan}`)}
    </Badge>
  );
}
