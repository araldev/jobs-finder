import Link from "next/link";
import { Activity, BarChart3, ArrowRight } from "lucide-react";

import { fetchDashboardStats, fetchJobsHistory } from "@/lib/supabase-queries";
import { PlatformBadge } from "@/components/jobs/PlatformBadge";
import { formatRelativeDate } from "@/lib/formatters";
import type { Locale } from "@/i18n/routing";

/**
 * RightSidebar — REQ-PDPRSC-002.
 *
 * Async React Server Component. Awaits `fetchDashboardStats()`
 * + `fetchLatestJobs({ limit: 5 })` in parallel via
 * `Promise.all`, so both the Summary section AND the Latest Jobs
 * list arrive in the server HTML payload.
 *
 * Pre-commit-6: this was a `"use client"` component that called
 * `useStats()` + `useJobs()` — both client-side React Query
 * hooks that deferred the sidebar content to post-hydration.
 *
 * Post-commit-6: server-fetched data renders synchronously into
 * the RSC tree. No client JS runs for the first paint of the
 * sidebar.
 *
 * The `locale` prop arrives from `dashboard/page.tsx`, which
 * reads it from `params.locale` (the `[locale]` dynamic route
 * segment). Since `localePrefix: 'never'`, the locale is
 * resolved by next-intl middleware from cookie or header.
 */

export async function RightSidebar({ locale }: { locale: Locale }) {
  const [stats, jobsData] = await Promise.all([
    fetchDashboardStats(),
    fetchJobsHistory({ limit: 5 }),
  ]);

  const sourceCount = stats?.platform_distribution
    ? Object.keys(stats.platform_distribution).length
    : 0;

  const items = jobsData?.items ?? [];

  return (
    <aside className="hidden w-72 flex-shrink-0 lg:block">
      <div className="sticky top-6 space-y-6">
        {/* Summary */}
        <section>
          <div className="mb-3 flex items-center gap-2 text-muted-foreground">
            <BarChart3 className="h-3.5 w-3.5" />
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider">
              Summary
            </h3>
          </div>
          <dl className="space-y-2 text-sm">
            <div className="flex items-baseline justify-between border-b border-dashed border-border/60 pb-2">
              <dt className="text-muted-foreground">Total Jobs</dt>
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
                <dt className="text-muted-foreground">Last Sync</dt>
                <dd className="font-mono text-xs">
                  {formatRelativeDate(stats.last_sync, locale)}
                </dd>
              </div>
            )}
          </dl>
        </section>

        {/* Latest Jobs */}
        <section>
          <div className="mb-3 flex items-center gap-2 text-muted-foreground">
            <Activity className="h-3.5 w-3.5" />
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider">
              Latest Jobs
            </h3>
          </div>
          {items.length > 0 ? (
            <ul className="divide-y divide-border/60 overflow-hidden rounded-lg bg-card ring-1 ring-border/50">
              {items.slice(0, 5).map((job) => (
                <li key={job.id}>
                  <Link
                    href={`/jobs/${job.id}`}
                    className="group block px-3 py-2.5 transition-colors hover:bg-muted/50"
                  >
                    <div className="mb-1 flex items-center gap-1.5">
                      <PlatformBadge platform={job.source} />
                      <span className="text-[10px] text-muted-foreground tabular-nums">
                        {job.posted_at
                          ? formatRelativeDate(job.posted_at, locale)
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

          {items.length > 0 && (
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