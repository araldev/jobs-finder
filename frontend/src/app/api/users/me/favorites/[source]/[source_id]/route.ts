import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// DELETE /api/users/me/favorites/[source]/[source_id]
//
// URL changed from /api/users/me/favorites/[job_id] to the (source, source_id)
// composite. The frontend `Job.id` is the source-native id, not the SERIAL
// `jobs.id` surrogate — see engram obs id 768 and the POST handler in
// `favorites/route.ts` for the full convention. The new URL keeps the
// identifier that the frontend actually has (source + source_id) and lets
// the handler look up the surrogate id server-side.
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ source: string; source_id: string }> },
) {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { source, source_id } = await params;

  // Look up the surrogate `jobs.id` from (source, source_id). A simple
  // two-step SELECT + DELETE is fine here; we don't need a JOIN because
  // `user_favorites.job_id` is the SERIAL id, not a (source, source_id)
  // composite. Optimizing with a single DELETE … USING jobs would
  // complicate the SQL without measurable benefit at this scale.
  const { data: jobRow, error: lookupError } = await supabase
    .from("jobs")
    .select("id")
    .eq("source", source)
    .eq("source_id", source_id)
    .maybeSingle();

  if (lookupError) {
    return NextResponse.json({ error: lookupError.message }, { status: 500 });
  }

  if (!jobRow) {
    // Idempotent: the job was never upserted (e.g. the Python scheduler
    // hasn't scraped it, or it was favorited in a previous session that
    // somehow lost the `jobs` row). 204 makes the DELETE safe to retry.
    return new NextResponse(null, { status: 204 });
  }

  const { error } = await supabase
    .from("user_favorites")
    .delete()
    .eq("user_id", session.user.id)
    .eq("job_id", jobRow.id);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return new NextResponse(null, { status: 204 });
}