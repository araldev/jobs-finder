import type { Metadata } from "next";
import { getLocale, getMessages, setRequestLocale } from "next-intl/server";
import { NextIntlClientProvider } from "next-intl";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Jobs Finder",
  description: "Encuentra tu próximo empleo. Busca en LinkedIn, Indeed e InfoJobs simultáneamente.",
  icons: {
    icon: "/favicon.svg",
  },
};

/**
 * Root layout — RSC (no 'use client' directive). Resolves the active
 * locale from next-intl's middleware-set request context and wraps the
 * tree in `<NextIntlClientProvider>` so client components can call
 * `useTranslations('Namespace')` from anywhere downstream.
 *
 * `setRequestLocale(locale)` is REQUIRED by next-intl 3.x+ for static
 * rendering — without it, every child that calls `useTranslations` from
 * a server component would log "static rendering not enabled" warnings
 * (design §Provider Boundary, D7).
 *
 * `<html lang={locale}>` flips ES ↔ EN so screen readers and search
 * engines see the right document language.
 *
 * Closes REQ-I18N-005 (dynamic `<html lang>`) and REQ-I18N-018 (the
 * `NextIntlClientProvider` boundary so client components can translate).
 */
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();
  // Make the locale available to all server-side child renders in this
  // request. next-intl's static rendering requires this — see
  // https://next-intl.dev/docs/getting-started/app-router#static-rendering
  setRequestLocale(locale);

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}