"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useTranslations } from "next-intl";
import type { SubscriptionStatus } from "@/types/billing";

interface CancellationBannerProps {
  status: SubscriptionStatus;
  cancelAtPeriodEnd: boolean;
  currentPeriodEnd: string | null;
}

export function CancellationBanner({
  status,
  cancelAtPeriodEnd,
  currentPeriodEnd,
}: CancellationBannerProps) {
  const t = useTranslations("Billing");

  if (status === "canceled") {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("banners.canceled.title")}</AlertTitle>
        <AlertDescription>
          {t("banners.canceled.description")}
        </AlertDescription>
      </Alert>
    );
  }

  if (status === "trialing" && cancelAtPeriodEnd) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("banners.trialCanceling.title")}</AlertTitle>
        <AlertDescription>
          {t("banners.trialCanceling.description", {
            date: currentPeriodEnd
              ? new Date(currentPeriodEnd).toLocaleDateString()
              : "?",
          })}
        </AlertDescription>
      </Alert>
    );
  }

  if (cancelAtPeriodEnd && currentPeriodEnd) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("banners.canceling.title")}</AlertTitle>
        <AlertDescription>
          {t("banners.canceling.description", {
            date: new Date(currentPeriodEnd).toLocaleDateString(),
          })}
        </AlertDescription>
      </Alert>
    );
  }

  return null;
}
