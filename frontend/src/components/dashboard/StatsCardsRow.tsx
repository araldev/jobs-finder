"use client";

import { Briefcase, Globe, Clock } from "lucide-react";
import { StatCard } from "./StatCard";
import { useStats } from "@/hooks/useStats";
import { formatRelativeDate } from "@/lib/formatters";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/ErrorState";

export function StatsCardsRow() {
  const { data, isLoading, isError, refetch } = useStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[132px] rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return <ErrorState message="Failed to load stats" onRetry={() => refetch()} />;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatCard
        icon={Briefcase}
        label="Total Jobs"
        value={data.total_jobs}
        iconClassName="bg-primary/10"
        delay={0}
      />
      <StatCard
        icon={Globe}
        label="Active Platforms"
        value={data.active_platforms}
        iconClassName="bg-accent/10"
        delay={0.1}
      />
      <StatCard
        icon={Clock}
        label="Last Updated"
        value={data.last_sync ? formatRelativeDate(data.last_sync) : "—"}
        iconClassName="bg-muted/50"
        delay={0.2}
      />
    </div>
  );
}
