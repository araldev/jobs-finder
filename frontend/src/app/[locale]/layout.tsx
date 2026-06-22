import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { Providers } from "@/app/providers";
import { ConditionalFooter } from "@/components/layout/ConditionalFooter";
import "../globals.css";

/**
 * Locale-scoped layout — wraps every page under `app/[locale]/`.
 *
 * This is the standard next-intl 4.x pattern: a dynamic `[locale]`
 * segment lets `params.locale` flow into `setRequestLocale(locale)`
 * and `getMessages()` BEFORE the children render, which is required
 * for static rendering of server components that call
 * `useTranslations('Namespace')` (see:
 * https://next-intl.dev/docs/getting-started/app-router/with-i18n-routing).
 *
 * `generateStaticParams` precomputes one entry per supported locale
 * so `next build` can statically render every locale variant of each
 * route under `[locale]/`.
 *
 * `notFound()` short-circuits any URL whose `[locale]` segment is
 * outside `routing.locales` (e.g. `/fr/dashboard` → 404) so we never
 * call `setRequestLocale` with a value the i18n config doesn't know.
 *
 * The root `app/layout.tsx` is a minimal pass-through that exists
 * only to satisfy Next.js's requirement that `app/layout.tsx` be
 * present. The `<html>` / `<body>` tags live here so we can read
 * `locale` from `params` and set `<html lang={locale}>`.
 *
 * Closes REQ-I18N-005 (dynamic `<html lang>`), REQ-I18N-018
 * (NextIntlClientProvider boundary), and the runtime-broken
 * SCN-I18N-002 (was a 404 before this slice).
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
    <html lang={locale} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>
            <div className="flex min-h-screen flex-col">
              <div className="flex-1">{children}</div>
              <ConditionalFooter />
            </div>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}