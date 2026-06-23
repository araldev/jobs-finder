import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  // Get favorites count
  const { count: favorites_count, error: favError } = await supabase
    .from("user_favorites")
    .select("id", { count: "exact" });

  if (favError) {
    return NextResponse.json({ error: favError.message }, { status: 500 });
  }

  // Get engagement counts by event type
  const { data: engagements, error: engError } = await supabase
    .from("user_engagement")
    .select("event_type");

  if (engError) {
    return NextResponse.json({ error: engError.message }, { status: 500 });
  }

  // Aggregate in JS
  let job_views = 0;
  let job_clicks = 0;
  let searches = 0;
  let cv_adapted = 0;

  for (const eng of engagements ?? []) {
    if (eng.event_type === "job_view") job_views++;
    else if (eng.event_type === "job_click") job_clicks++;
    else if (eng.event_type === "search") searches++;
    else if (eng.event_type === "cv_adapted") cv_adapted++;
  }

  // Get top favorite sources via a join (user_favorites with jobs)
  const { data: favsWithJobs, error: sourcesError } = await supabase
    .from("user_favorites")
    .select("jobs(source)");

  if (sourcesError) {
    return NextResponse.json({ error: sourcesError.message }, { status: 500 });
  }

  // Aggregate sources - jobs is an array due to FK relationship
  const sourceCount: Record<string, number> = {};
  for (const fav of favsWithJobs ?? []) {
    const jobs = fav.jobs as { source: string }[] | null;
    if (jobs && jobs.length > 0) {
      const source = jobs[0]?.source;
      if (source) {
        sourceCount[source] = (sourceCount[source] ?? 0) + 1;
      }
    }
  }

  const top_favorite_sources = Object.entries(sourceCount)
    .map(([source, count]) => ({ source, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  return NextResponse.json({
    favorites_count: favorites_count ?? 0,
    job_views,
    job_clicks,
    searches,
    cv_adapted,
    top_favorite_sources,
  });
}
