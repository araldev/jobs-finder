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
  // v1 uses `localePrefix: 'never'`, so URLs never carry a locale prefix.
  // The `stripLocalePrefix` helper remains as a defensive no-op for the
  // future `feat-frontend-i18n-locale-prefix-urls` follow-up that will
  // reintroduce the `[locale]/` route segment.
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

  // Si la ruta NO es pública, NO es la raíz, NO es API, y NO hay usuario → redirect a /login.
  if (!user && !isPublic && !isRoot && !isApi) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Si está logueado y va a /login → redirect a /dashboard.
  if (
    user &&
    (strippedPath === "/login" || strippedPath.startsWith("/login/"))
  ) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return response;
}