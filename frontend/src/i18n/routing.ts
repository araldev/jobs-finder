import { defineRouting } from "next-intl/routing";

/**
 * Single source of truth for the locale routing config.
 *
 * v2 — `localePrefix: 'as-needed'` (canonical URL mode):
 * - Locales: only Spanish and English.
 * - `defaultLocale: 'es'`: preserves the current audience + existing
 *   `<html lang="es">` baseline. Default-locale URLs stay unprefixed
 *   (`/dashboard`, `/login`).
 * - Non-default locales get a prefix (`/en/dashboard`, `/en/login`)
 *   — these are canonical, shareable, SaaS-grade URLs.
 * - Locale precedence (verified in next-intl 4.x `resolveLocale.tsx`
 *   Prio 1):
 *   1. URL path prefix (`/en/...`)
 *   2. `NEXT_LOCALE` cookie
 *   3. `Accept-Language` header
 *   4. `defaultLocale` (`es`)
 *
 * The `[locale]/` route segment was added in slice 16 so these URLs
 * actually resolve to real routes (previously this config caused 404s).
 * The middleware chain in `frontend/src/middleware.ts` uses the
 * `baseResponse` pattern so the intl middleware's `x-middleware-rewrite`
 * header survives into the final response — Supabase's `updateSession`
 * reads it to build locale-aware auth redirects (e.g. unauth on
 * `/en/dashboard` → `/en/login`, not `/login`).
 *
 * Closes REQ-I18N-001, REQ-I18N-002 (modified), REQ-I18N-003, REQ-I18N-004.
 */
export const routing = defineRouting({
  locales: ["es", "en"] as const,
  defaultLocale: "es",
  localePrefix: "as-needed",
  localeDetection: true,
});

export type Locale = (typeof routing.locales)[number];

/** Native-language labels for the LanguageSwitcher. */
export const LOCALE_LABELS: Record<Locale, string> = {
  es: "Español",
  en: "English",
};