import { NextResponse } from "next/server";
import { fetchJobsHistory, fetchSchedulerStatus } from "@/lib/api-client";

export async function GET() {
  try {
    const [history, status] = await Promise.all([
      fetchJobsHistory({ limit: 1 }),
      fetchSchedulerStatus().catch(() => null),
    ]);

    // Always fetch a sample to build distribution (don't gate on scheduler status)
    const sample = await fetchJobsHistory({ limit: 200 });
    const dist: Record<string, number> = {};
    let latestDate: string | null = null;
    for (const j of sample.items) {
      // Count per source
      dist[j.source] = (dist[j.source] ?? 0) + 1;
      // Track most recent posted_at
      if (j.posted_at && (!latestDate || j.posted_at > latestDate)) {
        latestDate = j.posted_at;
      }
    }

    // Count jobs from today (approximate — same day as latest)
    const todayDate = latestDate?.slice(0, 10);
    const todayCount = todayDate
      ? sample.items.filter((j) => j.posted_at?.startsWith(todayDate)).length
      : sample.items.length;

    return NextResponse.json({
      total_jobs: history.total,
      jobs_today: todayCount || sample.items.length,
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
