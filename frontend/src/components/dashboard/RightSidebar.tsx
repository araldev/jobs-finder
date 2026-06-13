"use client";

import { Activity, BarChart3 } from "lucide-react";
import { useStats } from "@/hooks/useStats";
import { useJobs } from "@/hooks/useJobs";
import { PlatformDistribution } from "./PlatformDistribution";
import { formatRelativeDate } from "@/lib/formatters";
import { Skeleton } from "@/components/ui/skeleton";

export function RightSidebar() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: jobsData } = useJobs({ limit: 5 });

  const sourceCount = stats?.platform_distribution
    ? Object.keys(stats.platform_distribution).length
    : 0;

  return (
    <aside className="hidden w-72 flex-shrink-0 lg:block">
      <div className="sticky top-6 space-y-6">
        {/* Summary card */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-display text-sm font-semibold">Summary</h3>
          </div>
          {statsLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Total jobs</dt>
                <dd className="font-mono font-semibold">{stats?.total_jobs ?? "—"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Sources</dt>
                <dd className="font-mono font-semibold">{sourceCount || "—"}</dd>
              </div>
              {stats?.last_sync && (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Last sync</dt>
                  <dd className="font-mono text-xs">{formatRelativeDate(stats.last_sync)}</dd>
                </div>
              )}
            </dl>
          )}
        </div>

        {/* Latest Jobs */}
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-display text-sm font-semibold">Latest Jobs</h3>
          </div>
          {jobsData?.items ? (
            <div className="space-y-2">
              {jobsData.items.slice(0, 5).map((job) => (
                <div key={job.id} className="text-sm">
                  <p className="truncate font-medium">{job.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {job.company} · {job.posted_at ? formatRelativeDate(job.posted_at) : "—"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No jobs yet</p>
          )}
        </div>
      </div>
    </aside>
  );
}
