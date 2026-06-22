import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { Providers } from "@/app/providers";
import { ConditionalFooter } from "@/components/layout/ConditionalFooter";

/**
 * Locale-scoped layout — wraps every page under `app/[locale]/`.
 *
 * The `<html>` and `<body>` tags live in `app/layout.tsx` (Next.js
 * requires them at the root, see:
 * https://nextjs.org/docs/messages/missing-root-layout-tags). This
 * nested layout only contributes locale-specific wrapping: the
 * `NextIntlClientProvider`, the `Providers` chain (QueryClient +
 * ThemeProvider + Toaster), and the `ConditionalFooter`.
 *
 * `generateStaticParams` precomputes one entry per supported locale
 * so `next build` can statically render every locale variant of each
 * route under `[locale]/`.
 *
 * `notFound()` short-circuits any URL whose `[locale]` segment is
 * outside `routing.locales` (e.g. `/fr/dashboard` → 404) so we never
 * call `setRequestLocale` with a value the i18n config doesn't know.
 *
 * `setRequestLocale(locale)` is REQUIRED by next-intl 3.x+ for static
 * rendering — without this, every server-component child that calls
 * `useTranslations` would log "static rendering not enabled" warnings.
 *
 * The `ConditionalFooter` (cycle 2's F6 fix) hides the Footer on
 * `(app)` route group pages where `AppShell` is already used — so we
 * don't render a dangling footer below a full-height AppShell.
 *
 * Closes REQ-I18N-005 (dynamic `<html lang>`), REQ-I18N-018
 * (NextIntlClientProvider boundary), REQ-I18N-020 (locale-aware auth
 * redirects), and the runtime-broken SCN-I18N-002 (was a 404 before
 * slice 16's `[locale]/` migration).
 */
export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const metadata: Metadata = {
  title: "Jobs Finder",
  description:
    "Encuentra tu próximo empleo. Busca en LinkedIn, Indeed e InfoJobs simultáneamente.",
};

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  // Guard against `/[locale]/...` URLs with an unknown locale
  // (e.g. `/fr/dashboard`). Treat as 404 — never render with a locale
  // the i18n config doesn't know.
  if (!(routing.locales as readonly string[]).includes(locale)) {
    notFound();
  }
  // REQUIRED by next-intl 3.x+ for static rendering — without this,
  // every server-component child that calls `useTranslations` would
  // log "static rendering not enabled" warnings.
  setRequestLocale(locale);

  const messages = await getMessages();

  return (
    <Providers>
      <NextIntlClientProvider locale={locale} messages={messages}>
        <div className="flex min-h-screen flex-col">
          <div className="flex-1">{children}</div>
          <ConditionalFooter />
        </div>
      </NextIntlClientProvider>
    </Providers>
  );
}
