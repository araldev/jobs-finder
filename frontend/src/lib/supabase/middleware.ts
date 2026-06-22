import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "@/i18n/routing";

/**
 * Strip a leading locale prefix from a pathname.
 *
 * Examples:
 *   stripLocalePrefix('/en/dashboard')  -> '/dashboard'
 *   stripLocalePrefix('/en/login')      -> '/login'
 *   stripLocalePrefix('/en')            -> '/'
 *   stripLocalePrefix('/dashboard')     -> '/dashboard'   (no match)
 *   stripLocalePrefix('/')              -> '/'
 *
 * Used by `updateSession` so the existing `publicPaths.some(...)` check
 * (which doesn't know about locale prefixes) keeps working for `/en/...`
 * URLs. Iterating over `routing.locales` (instead of regex) keeps the
 * helper trivial to read and easy to unit-test (design D5).
 */
export function stripLocalePrefix(path: string): string {
  for (const locale of routing.locales) {
    if (path === `/${locale}`) return "/";
    if (path.startsWith(`/${locale}/`)) return path.slice(locale.length + 1);
  }
  return path;
}

export async function updateSession(
  request: NextRequest,
  baseResponse?: NextResponse,
): Promise<NextResponse> {
  // Use the caller-provided response as the base so middleware-chain
  // callers (e.g. next-intl) can pre-set headers like `x-middleware-rewrite`
  // that must survive into the final response. When called standalone
  // (e.g. from tests or the kill-switch branch), fall back to a fresh
  // NextResponse.next() so the original contract is preserved.
  const response = baseResponse ?? NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Rutas públicas: / (landing page), /jobs (detalle público), /login, /signup, /auth
  // APIs (/api/*) son siempre accesibles. /forgot-password and /reset-password
  // are part of the public auth flow (REQ-AUTH-021) so an unauthenticated
  // user can request + complete a password reset without bouncing to /login.
  //
  // v2 uses `localePrefix: 'as-needed'`, so URLs MAY carry a locale prefix
  // (`/en/dashboard`). Strip it before comparing so `publicPaths.some(...)`
  // still matches the canonical Spanish-path shape (REQ-I18N-004).
  const publicPaths = [
    "/jobs",
    "/login",
    "/signup",
    "/auth",
    "/forgot-password",
    "/reset-password",
  ];
  const strippedPath = stripLocalePrefix(request.nextUrl.pathname);
  const isPublic = publicPaths.some(
    (path) => strippedPath === path || strippedPath.startsWith(path + "/"),
  );

  // La raíz / es la landing page pública (also matched after locale stripping).
  const isRoot = strippedPath === "/";

  // Las APIs son siempre accesibles
  const isApi = request.nextUrl.pathname.startsWith("/api");

  // Derive the locale prefix from the ORIGINAL (un-stripped) URL so the
  // auth-redirect bounce lands on the locale-correct login/dashboard page
  // (REQ-I18N-020). Default locale `es` has no prefix; non-default locales
  // (currently only `en`) prepend `/<locale>`.
  const localePrefix = deriveLocalePrefix(request.nextUrl.pathname);

  // Si la ruta NO es pública, NO es la raíz, NO es API, y NO hay usuario → redirect
  // to the locale-aware login path (REQ-I18N-020).
  if (!user && !isPublic && !isRoot && !isApi) {
    const url = request.nextUrl.clone();
    url.pathname = `${localePrefix}/login`;
    return NextResponse.redirect(url);
  }

  // Si está logueado y va a /login → redirect al dashboard (locale-aware).
  if (
    user &&
    (strippedPath === "/login" || strippedPath.startsWith("/login/"))
  ) {
    const url = request.nextUrl.clone();
    url.pathname = `${localePrefix}/dashboard`;
    return NextResponse.redirect(url);
  }

  return response;
}

/**
 * Derive the locale prefix for auth-redirect URLs.
 *
 * Returns:
 *   `""` for the default locale (`es`) or unprefixed paths
 *   (e.g. `/dashboard`, `/login`).
 *   `"/<locale>"` for non-default locales (e.g. `/en/dashboard`).
 *
 * Implementation: scan the pathname for any known locale prefix and
 * return the prefix iff the locale is NOT the default. Iterating over
 * `routing.locales` (vs. regex) keeps this trivial to read and unit-test.
 */
function deriveLocalePrefix(pathname: string): string {
  for (const locale of routing.locales) {
    if (pathname === `/${locale}` || pathname.startsWith(`/${locale}/`)) {
      return locale === routing.defaultLocale ? "" : `/${locale}`;
    }
  }
  return "";
}