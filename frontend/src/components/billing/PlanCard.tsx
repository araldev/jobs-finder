"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PLANS } from "@/lib/billing/plans";
import { CancellationBanner } from "@/components/billing/CancellationBanner";
import type { PlanName, SubscriptionStatus } from "@/types/billing";

interface PlanCardProps {
  plan: PlanName;
  isAuthenticated: boolean;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  status: SubscriptionStatus;
}

export function PlanCard({
  plan,
  isAuthenticated,
  currentPeriodEnd,
  cancelAtPeriodEnd,
  status,
}: PlanCardProps) {
  const t = useTranslations("Billing");
  const config = PLANS[plan];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="font-display text-lg">
            {t("labels.currentPlan")}
          </CardTitle>
          <span className="font-display text-base font-semibold">
            {plan === "pro_plus" ? t("plans.proPlus") : t(`plans.${plan}`)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <CancellationBanner
          status={status}
          cancelAtPeriodEnd={cancelAtPeriodEnd}
          currentPeriodEnd={currentPeriodEnd}
        />
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <div className="flex flex-col rounded-md border bg-muted/30 p-3">
            <dt className="text-xs text-muted-foreground">
              {t("labels.cvLimit")}
            </dt>
            <dd className="font-mono text-base font-semibold">
              {config.cvLimitPerMonth === "unlimited"
                ? t("values.unlimited")
                : config.cvLimitPerMonth}
            </dd>
          </div>
          <div className="flex flex-col rounded-md border bg-muted/30 p-3">
            <dt className="text-xs text-muted-foreground">
              {t("labels.savedLimit")}
            </dt>
            <dd className="font-mono text-base font-semibold">
              {config.savedSearchLimit === "unlimited"
                ? t("values.unlimited")
                : config.savedSearchLimit}
            </dd>
          </div>
          <div className="flex flex-col rounded-md border bg-muted/30 p-3">
            <dt className="text-xs text-muted-foreground">
              {t("labels.notifications")}
            </dt>
            <dd className="font-mono text-base font-semibold">
              {config.notificationsEnabled
                ? t("values.enabled")
                : t("values.disabled")}
            </dd>
          </div>
        </dl>
        <div className="flex justify-end">
          {!isAuthenticated ? (
            <Button asChild variant="outline">
              <Link href="/login">{t("cta.signInToUpgrade")}</Link>
            </Button>
          ) : plan === "free" ? (
            <Button asChild>
              <Link href="/api/billing/checkout?interval=monthly">
                {t("cta.upgrade")}
              </Link>
            </Button>
          ) : (
            <Button asChild variant="outline">
              <Link href="/api/billing/portal">
                {t("cta.manageSubscription")}
              </Link>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}