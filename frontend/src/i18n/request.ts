import { getRequestConfig } from "next-intl/server";
import { routing, type Locale } from "./routing";

/**
 * Per-request i18n configuration loaded by next-intl on the server.
 *
 * `requestLocale` is a Promise that resolves to the `[locale]` segment
 * (or `undefined` for routes outside the `[locale]` segment). When it's
 * `undefined` or an invalid value, we fall back to the default locale
 * (`es`) so unprefixed routes continue to work.
 *
 * Messages are dynamically imported so Vite splits one chunk per locale.
 *
 * Closes REQ-I18N-005 (provider boundary) and REQ-I18N-012 (Common +
 * Errors namespaces). Additional namespaces (`Auth`, `Navigation`,
 * `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`, `Chat`,
 * `Landing`, `Footer`) are added in subsequent slices.
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: Locale = (routing.locales as readonly string[]).includes(
    requested ?? "",
  )
    ? (requested as Locale)
    : routing.defaultLocale;

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});