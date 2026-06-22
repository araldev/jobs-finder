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

  // Run the next-intl middleware first. With `localePrefix: 'as-needed'`
  // and no `[locale]/` route segment, this issues an INTERNAL REWRITE
  // (header `x-middleware-rewrite`) for non-default locales so the URL
  // the browser sees (`/en/dashboard`) maps to the canonical app route
  // (`/dashboard`) at render time. We must pass that response as the
  // `baseResponse` to `updateSession` so the rewrite header survives —
  // otherwise we'd discard it and the user would see a 404 on every
  // `/en/*` URL (REQ-I18N-002 + REQ-I18N-015).
  const intlResponse = intlMiddleware(request);

  // `updateSession` mutates the base response (adds Supabase cookies).
  // When auth forces a redirect (e.g. protected /dashboard with no user),
  // it returns a fresh NextResponse.redirect() that overrides the base —
  // the intl redirect target is locale-aware so the bounce lands on the
  // correct-locale login page.
  return await updateSession(request, intlResponse);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - /api/*  (server-side proxies; never translated, never redirected)
     * - /auth/*  (Supabase OAuth callback — locale lives in cookie, not URL)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.svg (favicon)
     * - public folder files (.svg, .png, etc.)
     *
     * We MUST exclude:
     * - /api/* because the intl middleware would otherwise rewrite
     *   `/api/jobs` → `/en/api/jobs` for an English-locale visitor,
     *   breaking the route handlers the browser fetches via fetch().
     * - /auth/* because the Supabase OAuth callback hits `/auth/callback`
     *   as a redirect target from the Supabase auth server — that target
     *   is set at sign-in time and MUST be a stable URL regardless of
     *   locale. The callback route preserves locale via the NEXT_LOCALE
     *   cookie (see frontend/src/app/auth/callback/route.ts). Without
     *   this exclusion, intl rewrites `/auth/callback` → `/es/auth/callback`,
     *   which doesn't exist as a route (the file lives at
     *   `app/auth/callback/route.ts`, outside the `[locale]/` segment),
     *   and Next.js returns 404. Symptom: stuck on /auth/callback after
     *   sign-in, dashboard never loads.
     */
    "/((?!api|auth|_next/static|_next/image|favicon.svg|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};