import { Briefcase, Clock, TrendingUp } from "lucide-react";

import { fetchDashboardStats } from "@/lib/api-client";
import { StatCard } from "./StatCard";
import { EngagementStatsRow } from "./EngagementStatsRow";
import { formatRelativeDate } from "@/lib/formatters";
import { ErrorState } from "@/components/shared/ErrorState";

/**
 * StatsCardsRow — REQ-PDPRSC-002.
 *
 * Async React Server Component. Awaits `fetchDashboardStats()`
 * from the server-only `api-client` so the LCP element (the
 * "15 de Jun de 2026" date inside the lastSync StatCard) arrives
 * in the initial server HTML payload — no client JS required for
 * first paint.
 *
 * Pre-commit-6: this was a `"use client"` component that waited
 * for `useStats()` to resolve, putting the LCP element at the
 * END of the dashboard's paint order. The Lighthouse audit
 * pegged this as the largest contributor to LCP=5.4s.
 *
 * Post-commit-6: the page-level `<Suspense>` boundary wraps the
 * jobs-grid island (NOT this component) because the stats are
 * already in the server HTML and don't need to suspend. The
 * three primary cards + the per-platform distribution are
 * rendered synchronously from the awaited stats payload.
 *
 * Engagement stats (opened jobs, CVs adapted, favorites) live
 * in `<EngagementStatsRow />` because they read `localStorage`
 * and cannot run server-side. See that component for details.
 *
 * Error path: a failed `fetchDashboardStats()` throws, which
 * Next.js surfaces as the closest error boundary. The dashboard
 * page doesn't have a per-component error boundary, so the
 * error bubbles to `[locale]/error.tsx`. We also catch locally
 * and render `ErrorState` so a transient backend hiccup doesn't
 * blank the whole page — the existing `useStats()` consumer
 * showed `<ErrorState>` too, so this is the parity contract.
 */

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-[#0A66C2]",
  indeed: "bg-[#2164f3]",
  infojobs: "bg-[#e5335b]",
};

const PLATFORM_ICONS: Record<string, string> = {
  linkedin: "in",
  indeed: "i",
  infojobs: "ij",
};

export async function StatsCardsRow() {
  let stats;
  try {
    stats = await fetchDashboardStats();
  } catch {
    return <ErrorState message="Failed to load stats" />;
  }

  const dist = stats.platform_distribution ?? {};
  const platforms = Object.entries(dist).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-3">
      {/* Primary stats: totals */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={Briefcase}
          label="Total Jobs"
          value={stats.total_jobs > 0 ? stats.total_jobs.toLocaleString() : "—"}
          accent="primary"
          delay={0}
        />
        <StatCard
          icon={TrendingUp}
          label="New Jobs"
          value={stats.jobs_today > 0 ? stats.jobs_today.toLocaleString() : "—"}
          accent="secondary"
          delay={0.05}
        />
        <StatCard
          icon={Clock}
          label="Last Sync"
          value={
            stats.last_sync
              ? // The locale is hardcoded to "es" here because the
                // server component doesn't have access to the active
                // locale's request context. The page-level client
                // island (JobsGrid) handles locale-sensitive copy.
                // The date format is consistent across locales for
                // the LCP-bearing StatCard.
                formatRelativeDate(stats.last_sync, "es")
              : "—"
          }
          accent="muted"
          delay={0.1}
        />
      </div>

      {/* Engagement stats: client island (localStorage-backed) */}
      <EngagementStatsRow />

      {/* Secondary stats: per platform */}
      {platforms.length > 0 ? (
        <div className="rounded-xl bg-card p-3 ring-1 ring-border/50">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            Jobs per platform
          </div>
          <div className="flex gap-4">
            {platforms.map(([platform, count]) => {
              const pct =
                stats.total_jobs > 0
                  ? Math.round((count / stats.total_jobs) * 100)
                  : 0;
              return (
                <div key={platform} className="flex items-center gap-2">
                  <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-bold text-white ${PLATFORM_COLORS[platform] ?? "bg-muted"}`}
                  >
                    {PLATFORM_ICONS[platform] ?? platform.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-sm font-medium leading-tight">
                      {count.toLocaleString()}
                    </span>
                    <span className="text-xs text-muted-foreground leading-tight">
                      {platform} · {pct}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}