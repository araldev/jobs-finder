/**
 * Locale-aware formatting helpers for the UI.
 *
 * The UI is monolingual Spanish (es-ES) for v1. The RelativeTimeFormat
 * wrapper is the only one that needs the locale, but keeping them
 * here makes the eventual i18n follow-up a one-file change.
 */

const LOCALE = "es-ES";

/**
 * Format an ISO-8601 timestamp as a Spanish relative-time string.
 *
 * Examples:
 *   "hace 2 días"
 *   "hace 30+ días"
 *   "Recién publicado"  (less than 1 hour ago)
 *   ""                   (input is null or unparseable)
 */
export function formatRelativeTime(iso: string | null): string {
  if (iso === null || iso.length === 0) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const now = Date.now();
  const diffSeconds = Math.round((then - now) / 1000);
  const absSeconds = Math.abs(diffSeconds);

  if (absSeconds < 60) return "Recién publicado";

  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
  if (absSeconds < 60 * 60) {
    return rtf.format(Math.round(diffSeconds / 60), "minute");
  }
  if (absSeconds < 60 * 60 * 24) {
    return rtf.format(Math.round(diffSeconds / 3600), "hour");
  }
  if (absSeconds < 60 * 60 * 24 * 30) {
    return rtf.format(Math.round(diffSeconds / 86400), "day");
  }
  if (absSeconds < 60 * 60 * 24 * 365) {
    return rtf.format(Math.round(diffSeconds / (86400 * 30)), "month");
  }
  return "hace 30+ días";
}
