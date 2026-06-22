import "server-only";
import type { DashboardStats } from "@/types/stats";
import type { HistoryResponse, SchedulerStatus } from "@/types/job";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

function _headers() {
  const h: Record<string, string> = { Accept: "application/json" };
  if (BACKEND_API_KEY) h["X-API-Key"] = BACKEND_API_KEY;
  return h;
}

export interface FetchJobsHistoryArgs {
  readonly keywords?: string;
  readonly location?: string;
  readonly sources?: string;
  readonly limit?: number;
  readonly offset?: number;
}

export async function fetchJobsHistory(args: FetchJobsHistoryArgs = {}): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  if (args.keywords) params.set("keywords", args.keywords);
  if (args.location) params.set("location", args.location);
  if (args.sources) params.set("sources", args.sources);
  if (args.limit) params.set("limit", String(args.limit));
  if (args.offset) params.set("offset", String(args.offset));
  const qs = params.toString();
  const res = await fetch(`${BACKEND_URL}/jobs/history${qs ? `?${qs}` : ""}`, {
    headers: _headers(),
    next: { revalidate: 60, tags: ["jobs-history"] },
  });
  if (!res.ok) throw new Error(`Backend error: ${res.status}`);
  return res.json();
}

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetch(`${BACKEND_URL}/scheduler/status`, {
    headers: _headers(),
    next: { revalidate: 60, tags: ["scheduler-status"] },
  });
  if (!res.ok) throw new Error(`Backend error: ${res.status}`);
  return res.json();
}

/**
 * Fetch the consolidated dashboard stats from the new backend
 * `GET /jobs/stats` endpoint (REQ-PDPRSC-003).
 *
 * The backend endpoint consolidates the 6 fetches the legacy
 * `/api/stats` route handler did (3 waterfall chains) into a
 * single `asyncio.gather` with per-port timeout. The Next.js
 * Route Handler in `app/api/stats/route.ts` calls this function
 * so the browser sees ONE outbound HTTP request to the backend
 * (not 6).
 *
 * The `next: { revalidate: 60, tags: ["jobs-stats"] }` config
 * integrates with the Next.js Data Cache (L2): repeat calls
 * within 60s are deduped at the framework level, so even on a
 * cache miss the backend aggregator's own `InMemoryTTLCache`
 * (60s TTL) absorbs repeat hits without hitting SQLite.
 */
export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await fetch(`${BACKEND_URL}/jobs/stats`, {
    headers: _headers(),
    next: { revalidate: 60, tags: ["jobs-stats"] },
  });
  if (!res.ok) throw new Error(`Backend error: ${res.status}`);
  return res.json();
}

export async function fetchBackendJobsDirect(args: FetchJobsHistoryArgs = {}): Promise<HistoryResponse> {
  return fetchJobsHistory(args);
}
