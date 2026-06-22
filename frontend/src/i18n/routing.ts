import { defineRouting } from "next-intl/routing";

/**
 * Single source of truth for the locale routing config.
 *
 * v1 — pragmatic mode (`localePrefix: 'never'`):
 * - Locales: only Spanish and English.
 * - `defaultLocale: 'es'`: preserves the current audience + existing
 *   `<html lang="es">` baseline. With `localePrefix: 'never'`, every
 *   page URL stays unprefixed (`/dashboard`, `/login`).
 * - Locale is resolved by the next-intl middleware from the
 *   `NEXT_LOCALE` cookie first, then the `Accept-Language` header,
 *   then defaults to `es`. The middleware sets the cookie and tells
 *   the render tree which locale to use via `setRequestLocale(locale)`
 *   + `getMessages()` in `[locale]/layout.tsx`.
 * - The LanguageSwitcher writes `NEXT_LOCALE=en`, calls `router.refresh()`,
 *   and the page re-renders in English. URL stays the same.
 *
 * v2 candidate (deferred): `localePrefix: 'as-needed'` WITH the
 * `[locale]/` route segment — gives canonical shareable URLs like
 * `/en/dashboard`. Requires moving every page under `app/[locale]/...`
 * (tracked as follow-up `feat-frontend-i18n-locale-prefix-urls`).
 *
 * Closes REQ-I18N-001, REQ-I18N-002, REQ-I18N-003, REQ-I18N-004.
 */
export const routing = defineRouting({
  locales: ["es", "en"] as const,
  defaultLocale: "es",
  localePrefix: "never",
  localeDetection: true,
});

export type Locale = (typeof routing.locales)[number];

/** Native-language labels for the LanguageSwitcher. */
export const LOCALE_LABELS: Record<Locale, string> = {
  es: "Español",
  en: "English",
};