import { defineRouting } from "next-intl/routing";

/**
 * Single source of truth for the locale routing config.
 *
 * - `locales`: only Spanish and English are supported in v1.
 * - `defaultLocale: 'es'`: preserves the current audience and the existing
 *   `<html lang="es">` baseline; combined with `localePrefix: 'as-needed'`,
 *   this means `/dashboard` still resolves to Spanish.
 * - `localePrefix: 'as-needed'`: the default locale URLs stay unprefixed
 *   (`/dashboard`, `/login`), keeping zero-regression for current Spanish
 *   users. Non-default locales get a prefix (`/en/dashboard`).
 * - `localeDetection: true`: the middleware reads the `NEXT_LOCALE` cookie
 *   first and falls back to `Accept-Language` before defaulting to `es`.
 *
 * Closes REQ-I18N-001, REQ-I18N-002, REQ-I18N-003, REQ-I18N-004.
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