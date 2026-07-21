import "server-only";

import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { monthStartUtc } from "@/lib/billing/quota";

/**
 * GET /api/cv/count
 *
 * Returns the current month's CV generation count for the authenticated
 * user. Reads the `user_engagement` table directly from Supabase.
 *
 * RLS on `user_engagement` (`auth.uid() = user_id`, migration 007)
 * scopes the query to the authenticated user automatically; we
 * additionally filter by `event_type = 'cv_adapted'` and
 * `created_at >= month_start_utc` so the response is the user's
 * monthly quota consumption (D5: monthly, not daily).
 *
 * Response shape: `{ total_this_month: number }`
 *
 * Returns `{ total_this_month: 0 }` when:
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
    return NextResponse.json({ total_this_month: 0 });
  }

  // `month_start_utc` is the ISO timestamp for the start of the
  // current UTC month. `created_at` is a `timestamptz`, so the
  // comparison is correct regardless of the user's locale.
  const monthStart = monthStartUtc();

  const { count, error } = await supabase
    .from("user_engagement")
    .select("id", { count: "exact", head: true })
    .eq("event_type", "cv_adapted")
    .gte("created_at", monthStart);

  if (error) {
    console.error("cv/count: Supabase query failed", error);
    return NextResponse.json({ total_this_month: 0 });
  }

  return NextResponse.json({ total_this_month: count ?? 0 });
}