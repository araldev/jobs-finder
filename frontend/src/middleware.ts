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

  const intlResponse = intlMiddleware(request);
  const supabaseResponse = await updateSession(request);

  // Preserve any NEXT_LOCALE cookie that next-intl set.
  intlResponse.cookies.getAll().forEach(({ name, value }) =>
    supabaseResponse.cookies.set(name, value),
  );

  return supabaseResponse;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.svg (favicon)
     * - public folder files (.svg, .png, etc.)
     *
     * Note: we intentionally do NOT exclude `/api/*` here because the
     * Supabase `updateSession` middleware short-circuits API routes
     * internally (it never redirects them and always allows access).
     * next-intl's middleware is also safe on API routes — it only sets
     * a cookie and never rewrites non-page URLs.
     */
    "/((?!_next/static|_next/image|favicon.svg|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};