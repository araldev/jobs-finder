import { NextResponse } from "next/server";
import { fetchJobsHistory, fetchSchedulerStatus } from "@/lib/api-client";

export async function GET() {
  try {
    const [status, history] = await Promise.all([
      fetchSchedulerStatus().catch(() => null),
      fetchJobsHistory({ limit: 1 }),
    ]);

    // Fetch counts per source in parallel — each returns total for that source
    const [linkedin, indeed, infojobs] = await Promise.all([
      fetchJobsHistory({ limit: 1, sources: "linkedin" }).catch(() => ({ total: 0 })),
      fetchJobsHistory({ limit: 1, sources: "indeed" }).catch(() => ({ total: 0 })),
      fetchJobsHistory({ limit: 1, sources: "infojobs" }).catch(() => ({ total: 0 })),
    ]);

    const dist: Record<string, number> = {};
    if (linkedin.total > 0) dist.linkedin = linkedin.total;
    if (indeed.total > 0) dist.indeed = indeed.total;
    if (infojobs.total > 0) dist.infojobs = infojobs.total;

    // Sample for last sync date and today's count
    const sample = await fetchJobsHistory({ limit: 200 }).catch(() => ({ items: [] }));
    const items = sample.items ?? [];
    let latestDate: string | null = null;
    for (const j of items) {
      if (j.posted_at && (!latestDate || j.posted_at > latestDate)) {
        latestDate = j.posted_at;
      }
    }

    const todayDate = latestDate?.slice(0, 10);
    const todayCount = todayDate
      ? items.filter((j) => Boolean(j.posted_at?.startsWith(todayDate))).length
      : 0;

    return NextResponse.json({
      total_jobs: history.total,
      jobs_today: todayCount,
      active_platforms: Object.keys(dist).length || 1,
      last_sync: status?.last_run_end ?? latestDate,
      platform_distribution: dist,
    });
  } catch {
    return NextResponse.json({
      total_jobs: 0,
      jobs_today: 0,
      active_platforms: 0,
      last_sync: null,
      platform_distribution: {},
    });
  }
}
