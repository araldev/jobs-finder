import "server-only";

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import type { Job, Source } from "@/types/job";

/**
 * `GET /api/jobs/[id]` — return a single job by its source-native id.
 *
 * Phase 2 sub-task 2: previously this proxied
 * `${BACKEND_URL}/jobs/history/by-id/{id}` on the Python backend.
 * After the Supabase migration it reads directly from the `jobs`
 * table — `RLS is disabled on jobs (migration 009)`, so the
 * server-side `createClient()` returns the row regardless of the
 * caller's auth state (same anonymous-access contract as before).
 *
 * The response body is shaped as `Job` (the frontend
 * `useJobDetail` hook's query type). The backend's old
 * `HistoricalJobResponse` carried extra fields
 * (`first_seen_at`, `last_seen_at`, `query_snapshot`) that no
 * consumer reads — we drop them here for a tighter contract.
 *
 * Returns 404 if no row matches `source_id = id`.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("jobs")
    .select("source, source_id, title, company, location, url, description, posted_at")
    .eq("source_id", id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 503 });
  }
  if (!data) {
    return NextResponse.json({ error: "Job not found" }, { status: 404 });
  }

  const job: Job = {
    id: data.source_id,
    source: data.source as Source,
    title: data.title,
    company: data.company,
    location: data.location,
    url: data.url,
    posted_at: data.posted_at,
    description: data.description,
  };
  return NextResponse.json(job);
}