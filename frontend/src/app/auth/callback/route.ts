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

  if (process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.log(
      `[auth/callback] code=${code?.slice(0, 8) ?? "(none)"}... ` +
        `origin=${origin} ` +
        `cookies=${request.cookies
          .getAll()
          .map((c) => c.name)
          .join(",")}`,
    );
  }

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=missing_code`);
  }

  // Create the FINAL response first with the redirect target. The
  // Supabase client's `setAll` callback will attach the session
  // cookies directly to this response. We then return it (the
  // response carries BOTH the redirect AND the Set-Cookie headers
  // — the browser lands on `next` with the new session active).
  //
  // IMPORTANT: `NextResponse.next({ request })` is for MIDDLEWARE
  // only. Calling it in a Route Handler throws "NextResponse.next()
  // was used in a app route handler, this is not supported". The
  // Route-Handler pattern is: build the FINAL response up front,
  // let the Supabase client write cookies to it via setAll, and
  // return that same response. No `next()` indirection.
  const redirectUrl = new URL(`${origin}${next}`);
  const response = NextResponse.redirect(redirectUrl, { status: 307 });

  let supabase;
  try {
    supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            // Attach each freshly-written cookie to the FINAL
            // response so it travels with the 307 redirect to
            // `next`. The browser lands on `/dashboard` (or wherever)
            // with the session cookies set.
            for (const { name, value, options } of cookiesToSet) {
              response.cookies.set(name, value, options);
            }
          },
        },
      },
    );
  } catch (err) {
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[auth/callback] createServerClient threw:", err);
    }
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent(
        err instanceof Error ? err.message : String(err),
      )}`,
    );
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code).catch(
    (err) => {
      // Supabase client throws (not just returns { error }) on
      // network failures, malformed responses, and certain
      // protocol errors. We catch here so the route can return
      // a clean redirect to /login instead of a 500. The error
      // is logged in the dev server console for diagnosis.
      if (process.env.NODE_ENV !== "production") {
        // eslint-disable-next-line no-console
        console.error(
          "[auth/callback] exchangeCodeForSession threw:",
          err,
        );
      }
      return {
        data: { user: null, session: null },
        error: { message: err?.message ?? String(err) } as Error,
      };
    },
  );
  if (error) {
    return NextResponse.redirect(
      `${origin}/login?error=${encodeURIComponent(error.message)}`,
    );
  }

  // Session cookies are already attached to `response` via setAll.
  // Return the same response object — it carries both the
  // 307 redirect AND the Set-Cookie headers.
  return response;
}
