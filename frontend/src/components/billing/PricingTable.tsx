"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PLANS } from "@/lib/billing/plans";
import { cn } from "@/lib/utils";
import type { PlanName } from "@/types/billing";

interface PricingTableProps {
  currentPlan: PlanName;
  isAuthenticated: boolean;
}

const PLAN_ORDER: PlanName[] = ["free", "pro", "pro_plus"];

const FEATURE_KEYS: Record<PlanName, readonly string[]> = {
  free: ["cv", "saved", "notif"],
  pro: ["cv", "saved", "notif"],
  pro_plus: ["cv", "saved", "notif"],
};

export function PricingTable({ currentPlan, isAuthenticated }: PricingTableProps) {
  const t = useTranslations("Billing");

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {PLAN_ORDER.map((planName) => {
        const plan = PLANS[planName];
        const isCurrent = planName === currentPlan;
        const isLocked = !plan.enabled;

        return (
          <Card
            key={planName}
            className={cn(
              "flex flex-col",
              isCurrent && "ring-2 ring-primary",
              isLocked && "opacity-60",
            )}
            data-testid={`pricing-card-${planName}`}
          >
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="font-display text-xl">
                  {planName === "pro_plus"
                    ? t("plans.proPlus")
                    : t(`plans.${planName}`)}
                </CardTitle>
                {isCurrent && (
                  <span
                    className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                    data-testid={`current-plan-${planName}`}
                  >
                    {t("cta.currentPlan")}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col justify-between gap-4">
              <ul className="space-y-2 text-sm text-muted-foreground">
                {FEATURE_KEYS[planName].map((feat) => (
                  <li key={feat}>· {t(`features.${planName}.${feat}`)}</li>
                ))}
              </ul>
              <div className="pt-2">
                {isLocked ? (
                  <Button
                    variant="outline"
                    disabled
                    className="w-full"
                    data-testid={`cta-${planName}`}
                  >
                    {t("cta.proPlusSoon")}
                  </Button>
                ) : isCurrent ? (
                  planName === "free" ? (
                    isAuthenticated ? (
                      <Button
                        variant="outline"
                        disabled
                        className="w-full"
                        data-testid={`cta-${planName}`}
                      >
                        {t("cta.currentPlan")}
                      </Button>
                    ) : (
                      <Button asChild variant="outline" className="w-full">
                        <Link href="/login" data-testid={`cta-${planName}`}>
                          {t("cta.signInToUpgrade")}
                        </Link>
                      </Button>
                    )
                  ) : (
                    <Button asChild className="w-full">
                      <Link
                        href="/api/billing/portal"
                        data-testid={`cta-${planName}`}
                      >
                        {t("cta.manageSubscription")}
                      </Link>
                    </Button>
                  )
                ) : planName === "pro" ? (
                  isAuthenticated ? (
                    <Button asChild className="w-full">
                      <Link
                        href="/api/billing/checkout?interval=monthly"
                        data-testid={`cta-${planName}`}
                      >
                        {t("cta.upgrade")}
                      </Link>
                    </Button>
                  ) : (
                    <Button asChild variant="outline" className="w-full">
                      <Link
                        href="/login"
                        data-testid={`cta-${planName}`}
                      >
                        {t("cta.signInToUpgrade")}
                      </Link>
                    </Button>
                  )
                ) : null}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}