import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { sanitizeNext } from "@/lib/auth/sanitizeNext";
import { routing } from "@/i18n/routing";

/**
 * Read the active locale prefix from the `NEXT_LOCALE` cookie set by the
 * LanguageSwitcher (and mirrored in localStorage client-side).
 *
 * Returns the non-default locale prefix (e.g. `"/en"`) if the user has
 * explicitly chosen English; `""` for the default locale (es) or no cookie.
 * Conservative on unknown values — only the locales declared in
 * `routing.locales` are honored. Anything else falls back to the
 * default-locale empty prefix.
 *
 * Used by the OAuth callback to land the user on the locale-correct
 * dashboard / login page after sign-in (REQ-I18N-016, REQ-I18N-021).
 */
function readLocalePrefix(request: NextRequest): string {
  const cookie = request.cookies.get("NEXT_LOCALE")?.value;
  if (cookie && (routing.locales as readonly string[]).includes(cookie)) {
    return cookie === routing.defaultLocale ? "" : `/${cookie}`;
  }
  return "";
}

/**
 * Prefix a sanitized path with the active locale prefix — unless the
 * path is already prefixed (e.g. the caller passed `/en/dashboard`
 * explicitly via `?next=`) or the path is the `/` root (which
 * intentionally has no segment).
 */
function localizePath(path: string, localePrefix: string): string {
  if (!localePrefix) return path;
  if (path === "/") return localePrefix;
  // Already prefixed with any known locale — don't double-prefix.
  for (const locale of routing.locales) {
    if (path === `/${locale}` || path.startsWith(`/${locale}/`)) {
      return path;
    }
  }
  return `${localePrefix}${path}`;
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeNext(searchParams.get("next"));
  const localePrefix = readLocalePrefix(request);

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      const loginUrl = `${localePrefix}/login?error=${encodeURIComponent(error.message)}`;
      return NextResponse.redirect(`${origin}${loginUrl}`);
    }
  }

  return NextResponse.redirect(`${origin}${localizePath(next, localePrefix)}`);
}
