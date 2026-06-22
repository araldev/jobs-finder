import { NextResponse } from "next/server";
import { fetchDashboardStats } from "@/lib/api-client";

/**
 * `GET /api/stats` — proxies the backend's consolidated
 * `GET /jobs/stats` endpoint (REQ-PDPRSC-003).
 *
 * The previous version of this handler did 6 outbound fetches
 * to FastAPI in 3 waterfall chains (~600ms TTFB on cache miss).
 * The new version does ONE outbound fetch to the new backend
 * endpoint (which itself uses `asyncio.gather` + per-port
 * timeout to consolidate the per-source counts + scheduler
 * status). The Next.js Data Cache (`revalidate: 60,
 * tags: ["jobs-stats"]`) absorbs repeat hits at the framework
 * level.
 *
 * Response shape is preserved exactly (`DashboardStats`) so
 * the existing `useStats` client hook + `StatsCardsRow`
 * component keep working without any consumer-side changes.
 *
 * Graceful degradation: if the backend is unreachable (e.g.
 * uvicorn not running), we return the zero-shape payload
 * instead of a 500. The dashboard's `useStats` renders an
 * EmptyState on `total_jobs === 0` — the same path it took
 * pre-change.
 */
export async function GET() {
  try {
    const stats = await fetchDashboardStats();
    return NextResponse.json(stats);
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
