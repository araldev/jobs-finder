"use client";

import { Briefcase, Clock, TrendingUp, Eye, FileText, Heart } from "lucide-react";
import { StatCard } from "./StatCard";
import { useStats } from "@/hooks/useStats";
import { useOpenedJobs } from "@/lib/chat-storage";
import { useFavorites } from "@/hooks/useFavorites";
import { useCVAdapted } from "@/hooks/useCVAdapted";
import { formatRelativeDate } from "@/lib/formatters";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/ErrorState";

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-[#0A66C2]",
  indeed: "bg-[#2164f3]",
  infojobs: "bg-[#e5335b]",
};

const PLATFORM_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  infojobs: "InfoJobs",
};

const PLATFORM_ICONS: Record<string, string> = {
  linkedin: "in",
  indeed: "i",
  infojobs: "ij",
};

export function StatsCardsRow() {
  const { data, isLoading, isError, refetch } = useStats();
  const openedJobIds = useOpenedJobs();
  const { favoriteCount } = useFavorites();
  const { cvAdaptedCount } = useCVAdapted();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[100px] rounded-xl" />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[100px] rounded-xl" />
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[64px] rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return <ErrorState message="Failed to load stats" onRetry={() => refetch()} />;
  }

  const dist = data.platform_distribution ?? {};
  const platforms = Object.entries(dist).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-3">
      {/* Primary stats: totals */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={Briefcase}
          label="Total en base de datos"
          value={data.total_jobs > 0 ? data.total_jobs.toLocaleString() : "—"}
          accent="primary"
          delay={0}
        />
        <StatCard
          icon={TrendingUp}
          label="Jobs de hoy"
          value={data.jobs_today > 0 ? data.jobs_today.toLocaleString() : "—"}
          accent="secondary"
          delay={0.05}
        />
        <StatCard
          icon={Clock}
          label="Última sincronización"
          value={data.last_sync ? formatRelativeDate(data.last_sync) : "—"}
          accent="muted"
          delay={0.1}
        />
      </div>

      {/* Engagement stats: opened jobs, CVs adapted, favorites */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={Eye}
          label="Ofertas clicadas"
          value={openedJobIds.size > 0 ? openedJobIds.size.toLocaleString() : "—"}
          accent="primary"
          delay={0.15}
        />
        <StatCard
          icon={FileText}
          label="CVs adaptados"
          value={cvAdaptedCount > 0 ? cvAdaptedCount.toLocaleString() : "—"}
          accent="secondary"
          delay={0.2}
        />
        <StatCard
          icon={Heart}
          label="Favoritos"
          value={favoriteCount > 0 ? favoriteCount.toLocaleString() : "—"}
          accent="muted"
          delay={0.25}
        />
      </div>

      {/* Secondary stats: per platform */}
      {platforms.length > 0 ? (
        <div className="rounded-xl bg-card p-3 ring-1 ring-border/50">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            Jobs por plataforma
          </div>
          <div className="flex gap-4">
            {platforms.map(([platform, count]) => {
              const label = PLATFORM_LABELS[platform] ?? platform;
              const pct = data.total_jobs > 0 ? Math.round((count / data.total_jobs) * 100) : 0;
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
                      {label} · {pct}%
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
