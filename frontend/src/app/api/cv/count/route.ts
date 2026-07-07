import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * GET /api/cv/count
 *
 * Returns today's CV generation count for the authenticated user.
 * Reads the `user_engagement` table directly from Supabase — replaces
 * the previous Python backend proxy (`GET /cv/count`).
 *
 * RLS on `user_engagement` (`auth.uid() = user_id`, migration 007)
 * scopes the query to the authenticated user automatically; we
 * additionally filter by `event_type = 'cv_adapted'` and
 * `created_at >= today UTC` so the response is just the user's own
 * daily quota consumption.
 *
 * Response shape: `{ total_today: number }`
 *
 * Returns `{ total_today: 0 }` when:
 *   - the user is not authenticated (anonymous users have no events),
 *   - the Supabase query fails (graceful degradation so the dashboard
 *     count widget never throws — `useCVAdapted` catches non-OK
 *     responses and keeps the count at 0).
 */
export async function GET(_request: NextRequest) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return NextResponse.json({ total_today: 0 });
  }

  // `today_utc` is the ISO date (YYYY-MM-DD) for the start of the
  // current UTC day. `created_at` is a `timestamptz`, so the
  // comparison is correct regardless of the user's locale.
  const todayUtc = new Date().toISOString().slice(0, 10);

  const { count, error } = await supabase
    .from("user_engagement")
    .select("id", { count: "exact", head: true })
    .eq("event_type", "cv_adapted")
    .gte("created_at", todayUtc);

  if (error) {
    console.error("cv/count: Supabase query failed", error);
    return NextResponse.json({ total_today: 0 });
  }

  return NextResponse.json({ total_today: count ?? 0 });
}