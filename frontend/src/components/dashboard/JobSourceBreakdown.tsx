"use client";

import { useStats } from "@/hooks/useStats";
import { useTranslations } from "next-intl";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { getPlatformColorClass } from "@/lib/formatters";
import { formatRelativeDate } from "@/lib/formatters";
import { useLocale } from "next-intl";
import type { Locale } from "@/i18n/routing";

const PLATFORM_ICONS: Record<string, string> = {
  linkedin: "in",
  indeed: "i",
  infojobs: "ij",
};

export function JobSourceBreakdown() {
  const { data, isLoading, isError, refetch } = useStats();
  const t = useTranslations("Dashboard");
  const locale = useLocale() as Locale;

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[100px] rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return <ErrorState message="Failed to load stats" onRetry={() => refetch()} />;
  }

  const distribution = data.platform_distribution ?? {};
  const entries = Object.entries(distribution);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  if (entries.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-4 shadow-sm">
        <p className="py-4 text-center text-sm text-muted-foreground">
          {t("platforms.noData")}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="grid grid-cols-3 gap-4">
        {entries.map(([platform, count]) => {
          const label = t(`platforms.${platform}` as never);
          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
          return (
            <div
              key={platform}
              className="flex flex-col items-center gap-1.5 rounded-lg p-3 text-center transition-colors hover:bg-muted/50"
            >
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-white ${getPlatformColorClass(platform)}`}
              >
                {PLATFORM_ICONS[platform] ?? platform.charAt(0).toUpperCase()}
              </span>
              <span className="text-sm font-medium">{label}</span>
              <span className="font-mono text-lg font-bold tracking-tight">
                {count}
              </span>
              <span className="text-xs text-muted-foreground">
                {t("platforms.percentOfTotal", { pct })}
              </span>
            </div>
          );
        })}
      </div>
      {data.last_sync && (
        <p className="mt-3 text-center text-xs text-muted-foreground">
          {t("stats.lastSync.label")} {formatRelativeDate(data.last_sync, locale)}
        </p>
      )}
    </div>
  );
}