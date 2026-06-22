"use client";

import { useTranslations } from "next-intl";

/**
 * Latency hint shown beneath skeleton grids.
 *
 * Small Client Component (REQ-CACHEUX-007) that calls
 * `useTranslations` to render the localized hint copy. Lives in
 * `components/shared/` so both the dashboard skeleton and the root
 * loading boundary can embed it without each one becoming a Client
 * Component (the parent stays RSC).
 *
 * @param ns Translation namespace. `"Dashboard"` for the dashboard
 *           skeleton (dashboard-specific copy). `"Common"` for the
 *           root loading boundary (generic copy reusable elsewhere).
 */
export function LoadingHint({
  ns = "Dashboard",
}: {
  ns?: "Dashboard" | "Common";
} = {}) {
  const t = useTranslations(ns);
  return (
    <p className="mt-3 text-center text-xs text-muted-foreground">
      {t("loadingHint")}
    </p>
  );
}
