import { formatDistanceToNow, format, isToday, isYesterday } from "date-fns";
import { es, enUS } from "date-fns/locale";
import type { Locale } from "@/i18n/routing";

/**
 * Locale-aware date / number formatting primitives.
 *
 * Every helper accepts an OPTIONAL `locale: Locale` parameter that defaults
 * to `'es'` (the project's default locale — design D3 + D14). This
 * preserves the existing behavior for every callsite that hasn't been
 * migrated yet (slices 7, 8, 9, 10 migrate their individual callers to
 * pass the active locale explicitly).
 *
 * Spanish uses `date-fns/locale#es`; English uses `enUS`. Currency
 * formatting is intentionally deferred (F2 follow-up) — this module
 * does not touch the backend currency schema.
 *
 * Closes REQ-I18N-014 (formatters locale-aware).
 */

export function formatRelativeDate(
  dateStr: string | null,
  locale: Locale = "es",
): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const dfnsLocale = locale === "es" ? es : enUS;
  if (isToday(date)) {
    return formatDistanceToNow(date, { addSuffix: true, locale: dfnsLocale });
  }
  if (isYesterday(date)) {
    return locale === "es" ? "Ayer" : "Yesterday";
  }
  return format(
    date,
    locale === "es" ? "d 'de' MMM 'de' yyyy" : "MMM d, yyyy",
  );
}

export function formatNumber(n: number, locale: Locale = "es"): string {
  return new Intl.NumberFormat(locale).format(n);
}

export function getPlatformColorClass(platform: string): string {
  const map: Record<string, string> = {
    linkedin: "bg-[hsl(var(--linkedin))]",
    indeed: "bg-[hsl(var(--indeed))]",
    infojobs: "bg-[hsl(var(--infojobs))]",
  };
  return map[platform.toLowerCase()] ?? "bg-muted";
}