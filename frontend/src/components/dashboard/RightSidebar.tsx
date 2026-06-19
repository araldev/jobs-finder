"use client";

import Link from "next/link";
import { Activity, BarChart3, ArrowRight } from "lucide-react";
import { useStats } from "@/hooks/useStats";
import { useJobs } from "@/hooks/useJobs";
import { PlatformBadge } from "@/components/jobs/PlatformBadge";
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
        {/* Summary — pure metric list (no card chrome, different from job cards) */}
        <section>
          <div className="mb-3 flex items-center gap-2 text-muted-foreground">
            <BarChart3 className="h-3.5 w-3.5" />
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider">
              Summary
            </h3>
          </div>
          {statsLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : (
            <dl className="space-y-2 text-sm">
              <div className="flex items-baseline justify-between border-b border-dashed border-border/60 pb-2">
                <dt className="text-muted-foreground">Total jobs</dt>
                <dd className="font-mono font-semibold tabular-nums">
                  {stats?.total_jobs?.toLocaleString() ?? "—"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between border-b border-dashed border-border/60 pb-2">
                <dt className="text-muted-foreground">Sources</dt>
                <dd className="font-mono font-semibold tabular-nums">
                  {sourceCount || "—"}
                </dd>
              </div>
              {stats?.last_sync && (
                <div className="flex items-baseline justify-between">
                  <dt className="text-muted-foreground">Last sync</dt>
                  <dd className="font-mono text-xs">
                    {formatRelativeDate(stats.last_sync)}
                  </dd>
                </div>
              )}
            </dl>
          )}
        </section>

        {/* Latest Jobs — list style (rows, not cards) */}
        <section>
          <div className="mb-3 flex items-center gap-2 text-muted-foreground">
            <Activity className="h-3.5 w-3.5" />
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider">
              Latest Jobs
            </h3>
          </div>
          {jobsData?.items && jobsData.items.length > 0 ? (
            <ul className="divide-y divide-border/60 overflow-hidden rounded-lg bg-card ring-1 ring-border/50">
              {jobsData.items.slice(0, 5).map((job) => (
                <li key={job.id}>
                  <Link
                    href={`/jobs/${job.id}`}
                    className="group block px-3 py-2.5 transition-colors hover:bg-muted/50"
                  >
                    <div className="mb-1 flex items-center gap-1.5">
                      <PlatformBadge platform={job.source} />
                      <span className="text-[10px] text-muted-foreground tabular-nums">
                        {job.posted_at
                          ? formatRelativeDate(job.posted_at)
                          : "—"}
                      </span>
                    </div>
                    <p className="line-clamp-1 text-sm font-medium leading-snug group-hover:text-primary">
                      {job.title}
                    </p>
                    <p className="line-clamp-1 text-xs text-muted-foreground">
                      {job.company}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-lg bg-card p-3 text-sm text-muted-foreground ring-1 ring-border/50">
              No jobs yet
            </p>
          )}

          {jobsData?.items && jobsData.items.length > 0 && (
            <Link
              href="/search"
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-primary"
            >
              View all jobs
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </section>
      </div>
    </aside>
  );
}
