import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
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
 *
 * Cookie handling uses the response-object pattern (the more reliable
 * Next.js 15 pattern). The previous version used `cookies()` from
 * `next/headers` to set cookies, but those writes don't always attach
 * to the redirect response in App Router. The response-object pattern
 * makes the cookie writes explicit and survives in both Server Actions
 * and Route Handlers.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeNext(searchParams.get("next"));

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=missing_code`);
  }

  // Mutable response — Supabase's `setAll` callback may replace it
  // with a fresh one that has the new auth cookies attached. This
  // is the pattern recommended by Supabase's docs for Route Handlers
  // in Next.js 15 (avoids the cookie-write loss bug we hit with the
  // cookies()-from-next/headers pattern).
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          // 1) Echo cookies back to the request (so server
          //    components reading them see the freshly-written values).
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          // 2) Write cookies to a fresh response object (so they
          //    actually travel with the response we return below).
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent(error.message)}`,
    );
  }

  // Attach the `?next=` redirect target. The session cookies are
  // already on `response` (set by the Supabase client above).
  return NextResponse.redirect(`${origin}${next}`, {
    headers: response.headers,
  });
}
