import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const limit = parseInt(searchParams.get("limit") ?? "20", 10);
  const offset = parseInt(searchParams.get("offset") ?? "0", 10);

  // RLS: Supabase automatically filters by auth.uid()
  const { data, error, count } = await supabase
    .from("user_favorites")
    .select("*, jobs(*)", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // CRITICAL: override `id` with `source_id` so the response shape
  // matches the rest of the codebase. The Postgres `jobs.id` is a
  // SERIAL surrogate (assigned by the DB), but the frontend `Job`
  // type and the `/api/jobs/history` endpoint (Python backend) both
  // use the source-native id (LinkedIn's `4432827022`, Indeed's
  // `dd6cc0f5b0f0cfc9`, etc.) as `id`. Without this mapping, the
  // DELETE handler can't find the job by `(source, source_id)`
  // because the frontend would pass `String(job.id) = surrogate` as
  // the source_id URL segment — which never exists in `jobs.source_id`.
  // The DELETE would silently return 204 idempotent without deleting
  // anything, and the optimistic update in the UI would never
  // match the GET response (because surrogate != native), making
  // `isFavorite(id)` always return false after the first refetch.
  return NextResponse.json({
    data: data?.map((f) => ({ ...f.jobs, id: f.jobs.source_id })) ?? [],
    total: count ?? 0,
    limit,
    offset,
  });
}

export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  // Body shape: { job: { id, source, title, company, location, url, posted_at, description? } }
  //
  // CONVENTION (cross-cutting, see engram obs id 768):
  //   Frontend `Job.id` is the SOURCE-NATIVE id (LinkedIn's `4432827022`,
  //   Indeed's numeric id, InfoJobs's id) — stored in the DB as
  //   `jobs.source_id` (TEXT).
  //   `jobs.id` is a SERIAL surrogate assigned by Postgres. It is NEVER
  //   exposed through the API and is NEVER the source-native id.
  //   The Python backend's scraper follows the same convention
  //   (see backend/src/jobs_finder/infrastructure/persistence/
  //   postgres_job_repository.py:49-61 — the UPSERT explicitly omits `id`).
  //
  // The composite UNIQUE constraint `UNIQUE (source, source_id)` (defined
  // in Migration 001) makes the upsert idempotent.
  const { job } = await request.json();

  if (
    !job?.id ||
    !job?.source ||
    !job?.title ||
    !job?.company ||
    !job?.location ||
    !job?.url ||
    !job?.posted_at
  ) {
    return NextResponse.json(
      { detail: "Missing required job fields (id, source, title, company, location, url, posted_at)" },
      { status: 400 },
    );
  }

  // Step 1: upsert the job by (source, source_id) WITHOUT specifying id.
  // The DB assigns the SERIAL surrogate id. We select it back so the next
  // INSERT into user_favorites can reference it (the FK is `job_id INTEGER
  // REFERENCES jobs(id)`, never source_id).
  const { data: upsertedJob, error: jobError } = await supabase
    .from("jobs")
    .upsert(
      {
        source: job.source,
        source_id: String(job.id),
        title: job.title,
        company: job.company,
        location: job.location,
        url: job.url,
        description: job.description ?? null,
        posted_at: job.posted_at,
        query_snapshot: "favorited-from-list",
        first_seen_at: new Date().toISOString(),
        last_seen_at: new Date().toISOString(),
      },
      { onConflict: "source,source_id" },
    )
    .select("id")
    .single();

  if (jobError || !upsertedJob) {
    return NextResponse.json(
      { error: jobError?.message ?? "Failed to upsert job" },
      { status: 500 },
    );
  }

  const surrogateJobId = upsertedJob.id;

  // Step 2: insert the favorite using the surrogate id returned above.
  const { error: favError } = await supabase
    .from("user_favorites")
    .insert({ user_id: session.user.id, job_id: surrogateJobId });

  if (favError?.code === "23505") {
    return NextResponse.json({ status: "already_exists" }, { status: 200 });
  }
  if (favError) {
    return NextResponse.json({ error: favError.message }, { status: 500 });
  }

  return NextResponse.json(
    { status: "created", job_id: surrogateJobId },
    { status: 201 },
  );
}