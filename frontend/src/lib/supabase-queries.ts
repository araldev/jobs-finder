import "server-only";
import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import type { DashboardStats } from "@/types/stats";
import type { HistoryResponse, Job, Source } from "@/types/job";

export interface FetchJobsHistoryArgs {
  readonly keywords?: string;
  readonly location?: string;
  readonly sources?: string;
  readonly limit?: number;
  readonly offset?: number;
}

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 200;
const SOURCES: readonly Source[] = ["linkedin", "indeed", "infojobs"] as const;

interface JobRow {
  readonly source: string;
  readonly source_id: string;
  readonly title: string;
  readonly company: string;
  readonly location: string;
  readonly url: string;
  readonly description: string | null;
  readonly posted_at: string;
}

function rowToJob(row: JobRow): Job {
  return {
    id: row.source_id,
    source: row.source as Source,
    title: row.title,
    company: row.company,
    location: row.location,
    url: row.url,
    posted_at: row.posted_at,
    description: row.description,
  };
}

function parseSources(sources: string | undefined): string[] | null {
  if (!sources) return null;
  const list = sources
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && (SOURCES as readonly string[]).includes(s));
  return list.length > 0 ? list : null;
}

function clampLimit(limit: number | undefined): number {
  if (!limit || limit <= 0) return DEFAULT_LIMIT;
  return Math.min(limit, MAX_LIMIT);
}

function clampOffset(offset: number | undefined): number {
  if (!offset || offset < 0) return 0;
  return offset;
}

function escapeIlike(value: string): string {
  return value.replace(/[%_\\]/g, (ch) => `\\${ch}`);
}

/**
 * Read the consolidated dashboard stats directly from Supabase
 * (replaces the backend's `GET /jobs/stats` endpoint).
 *
 * Five count queries in parallel — `head: true` makes each call
 * a count-only request (no row payload) so the per-port cost is
 * just the count header from PostgREST. RLS is disabled on `jobs`
 * (migration 009) so the server-side client reads all rows
 * regardless of the caller's auth state.
 *
 * `last_sync` is `null` for now — the backend's `BackgroundJobScheduler`
 * keeps the runtime state in process memory and we do not yet have a
 * shared table for it. The dashboard's `useStats` consumer renders
 * `null` as "—". A follow-up will either add a `scheduler_state`
 * table or have the backend write the timestamp to Supabase.
 */
export const fetchDashboardStats = cache(async (): Promise<DashboardStats> => {
  const supabase = await createClient();

  const today = new Date().toISOString().slice(0, 10);

  const [totalRes, todayRes, linkedinRes, indeedRes, infojobsRes] =
    await Promise.all([
      supabase.from("jobs").select("*", { count: "exact", head: true }),
      supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .gte("posted_at", today),
      supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .eq("source", "linkedin"),
      supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .eq("source", "indeed"),
      supabase
        .from("jobs")
        .select("*", { count: "exact", head: true })
        .eq("source", "infojobs"),
    ]);

  const errors = [
    totalRes.error,
    todayRes.error,
    linkedinRes.error,
    indeedRes.error,
    infojobsRes.error,
  ].filter((e): e is NonNullable<typeof e> => e !== null);
  if (errors.length > 0) {
    throw new Error(
      `fetchDashboardStats: ${errors.map((e) => e.message).join("; ")}`,
    );
  }

  const total_jobs = totalRes.count ?? 0;
  const jobs_today = todayRes.count ?? 0;
  const platform_distribution: Record<string, number> = {
    linkedin: linkedinRes.count ?? 0,
    indeed: indeedRes.count ?? 0,
    infojobs: infojobsRes.count ?? 0,
  };
  const active_platforms = Object.values(platform_distribution).filter(
    (v) => v > 0,
  ).length;

  return {
    total_jobs,
    jobs_today,
    active_platforms,
    // TODO: read from a scheduler_state table once the backend writes it there.
    last_sync: null,
    platform_distribution,
  };
});

/**
 * Read the latest N jobs directly from Supabase.
 *
 * Thin wrapper over `fetchJobsHistory` — sidebar consumers pass
 * `limit: 5` and the same caching boundary applies.
 */
export const fetchLatestJobs = cache(
  async (
    args: { readonly limit?: number } = {},
  ): Promise<HistoryResponse> => {
    return fetchJobsHistoryInternal({ limit: args.limit ?? 5 });
  },
);

/**
 * Read job history directly from Supabase (replaces the backend's
 * `GET /jobs/history` endpoint).
 *
 * Mirrors the backend's `search_jobs_history` filter shape:
 *   - `keywords` → ILIKE on title OR company
 *   - `location` → ILIKE on location
 *   - `sources`  → `source IN (...)` (CSV-parsed, validated against
 *     the canonical 3 sources)
 *   - order: `posted_at DESC`
 *   - pagination via `.range()`
 *
 * The Spain-locations-priority ordering (the backend's
 * `ORDER BY CASE WHEN spain_clauses THEN 0 ELSE 1 END, posted_at DESC`)
 * is intentionally NOT replicated — simple `posted_at DESC` is fine
 * for the dashboard's "latest jobs" view. The priority ordering can
 * be added as a `.order()` chain in a follow-up.
 *
 * Returns `{ items, total, limit, offset }`. The `id` field on
 * each item is the source-native id (`source_id`) per the
 * cross-cutting convention documented in
 * `app/api/users/me/favorites/route.ts`.
 */
export const fetchJobsHistory = cache(
  async (args: FetchJobsHistoryArgs = {}): Promise<HistoryResponse> => {
    return fetchJobsHistoryInternal(args);
  },
);

async function fetchJobsHistoryInternal(
  args: FetchJobsHistoryArgs,
): Promise<HistoryResponse> {
  const limit = clampLimit(args.limit);
  const offset = clampOffset(args.offset);
  const sourceList = parseSources(args.sources);
  const keywordPattern = args.keywords
    ? `%${escapeIlike(args.keywords)}%`
    : null;
  const locationPattern = args.location
    ? `%${escapeIlike(args.location)}%`
    : null;

  const supabase = await createClient();

  const buildCountQuery = () => {
    let q = supabase.from("jobs").select("*", { count: "exact", head: true });
    if (sourceList) q = q.in("source", sourceList);
    if (keywordPattern) {
      q = q.or(`title.ilike.${keywordPattern},company.ilike.${keywordPattern}`);
    }
    if (locationPattern) q = q.ilike("location", locationPattern);
    return q;
  };

  const buildDataQuery = () => {
    let q = supabase
      .from("jobs")
      .select(
        "source, source_id, title, company, location, url, description, posted_at",
      );
    if (sourceList) q = q.in("source", sourceList);
    if (keywordPattern) {
      q = q.or(`title.ilike.${keywordPattern},company.ilike.${keywordPattern}`);
    }
    if (locationPattern) q = q.ilike("location", locationPattern);
    q = q
      .order("posted_at", { ascending: false })
      .range(offset, offset + limit - 1);
    return q;
  };

  const [countRes, dataRes] = await Promise.all([
    buildCountQuery(),
    buildDataQuery(),
  ]);

  if (countRes.error) {
    throw new Error(`fetchJobsHistory count: ${countRes.error.message}`);
  }
  if (dataRes.error) {
    throw new Error(`fetchJobsHistory data: ${dataRes.error.message}`);
  }

  const rows = (dataRes.data ?? []) as unknown as JobRow[];
  return {
    items: rows.map(rowToJob),
    total: countRes.count ?? 0,
    limit,
    offset,
  };
}