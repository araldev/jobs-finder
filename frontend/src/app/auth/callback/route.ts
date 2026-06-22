import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { sanitizeNext } from "@/lib/auth/sanitizeNext";

/**
 * OAuth callback (Supabase).
 *
 * v1 uses `localePrefix: 'never'`, so URLs never carry a locale prefix.
 * The active locale is communicated via the `NEXT_LOCALE` cookie (read by
 * the next-intl middleware on the next request) and is reflected in
 * `<html lang>` + translated strings — NOT in the URL itself. The callback
 * therefore lands the user on the canonical `/dashboard` (or wherever the
 * `?next=` query param points), and the locale middleware picks up the
 * cookie on the next request.
 *
 * The previous version of this file added a `/<locale>/` prefix to the
 * redirect target. That was correct under the design's
 * `localePrefix: 'as-needed'` + `[locale]/` segment plan, but the v1
 * implementation ships without the segment — leaving the prefix would
 * 404 the OAuth callback for English users. REQ-I18N-016 is satisfied
 * via the `NEXT_LOCALE` cookie pathway instead.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeNext(searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      return NextResponse.redirect(
        `${origin}/login?error=${encodeURIComponent(error.message)}`,
      );
    }
  }

  return NextResponse.redirect(`${origin}${next}`);
}
