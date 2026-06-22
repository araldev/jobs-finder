import createIntlMiddleware from "next-intl/middleware";
import { type NextRequest } from "next/server";
import { routing } from "@/i18n/routing";
import { updateSession } from "@/lib/supabase/middleware";

/**
 * Middleware chain — runs `next-intl`'s locale middleware FIRST so the
 * Supabase layer can read the locale-aware pathname (e.g. `/en/dashboard`),
 * then `updateSession` so the Supabase session cookies are attached.
 *
 * Order is intentional (design D4):
 *   1. `intlResponse` — reads/writes the `NEXT_LOCALE` cookie, performs
 *      locale-prefix redirects for non-default locales, and rewrites
 *      the URL so the page render sees the right `[locale]` segment.
 *   2. `supabaseResponse` — runs the existing auth/redirect logic
 *      against the SAME `request` (the rewrite happened in-memory, not
 *      on the URL the user sees), with locale-prefix stripping applied
 *      inside `updateSession` via `stripLocalePrefix()` so the existing
 *      `publicPaths.some(...)` check still matches `/dashboard`,
 *      `/login`, etc., when the URL was `/en/dashboard`, `/en/login`.
 *   3. Merge the intl cookies onto the supabase response so `NEXT_LOCALE`
 *      survives the round-trip — without this, the switcher would set
 *      the cookie but it would be silently dropped by the supabase
 *      response constructor.
 *
 * The `NEXT_PUBLIC_I18N_ENABLED === 'false'` kill-switch (design D14)
 * short-circuits the intl layer entirely and routes the request straight
 * to Supabase. This is the escape hatch if a future slice regresses
 * production traffic — flip the env var, redeploy, no other change.
 *
 * Closes REQ-I18N-003 (chain ordering), REQ-I18N-004 (locale-aware
 * public paths), REQ-I18N-016 (OAuth callback locale-aware).
 */
const intlMiddleware = createIntlMiddleware(routing);

export async function middleware(request: NextRequest) {
  // Feature-flag escape hatch — instant rollback if intl regresses.
  if (process.env.NEXT_PUBLIC_I18N_ENABLED === "false") {
    return await updateSession(request);
  }

  // Run the next-intl middleware first. With `localePrefix: 'as-needed'`,
  // it may issue either:
  //   - a 307 redirect (e.g. `/dashboard` + `Accept-Language: en-US` →
  //     `/en/dashboard` for canonical URL fan-out), or
  //   - an internal rewrite (e.g. `/en/dashboard` → `/dashboard` render
  //     path with locale=en).
  const intlResponse = intlMiddleware(request);

  // If intl issued a REDIRECT, respect it — the canonical locale-prefixed
  // URL is the correct outcome. Returning updateSession's response here
  // would silently overwrite the intl redirect with the auth bounce to
  // `/login`, losing the locale prefix. The user's NEXT request will
  // hit `/en/dashboard` (or `/en/...`), where updateSession will then
  // bounce them to `/en/login` (locale-aware, per REQ-I18N-020).
  if (intlResponse.status === 307 || intlResponse.status === 308) {
    return intlResponse;
  }

  // For rewrites and passthrough, run Supabase with the intl response as
  // the base so cookies and rewrite headers survive. updateSession's
  // locale-aware auth redirect (REQ-I18N-020) inspects the original URL
  // via `deriveLocalePrefix()` and bounces to `/en/login` (or `/login`
  // for the default locale) as appropriate.
  return await updateSession(request, intlResponse);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - /api/*  (server-side proxies; never translated, never redirected)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.svg (favicon)
     * - public folder files (.svg, .png, etc.)
     *
     * We MUST exclude /api/* because the intl middleware would otherwise
     * rewrite `/api/jobs` → `/en/api/jobs` for an English-locale visitor,
     * breaking the route handlers that the browser fetches via fetch().
     */
    "/((?!api|_next/static|_next/image|favicon.svg|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};