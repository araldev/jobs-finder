import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { Providers } from "@/app/providers";

/**
 * Locale-scoped layout — wraps every page under `app/[locale]/`.
 *
 * The `<html>` and `<body>` tags live in `app/layout.tsx` (Next.js
 * requires them at the root, see:
 * https://nextjs.org/docs/messages/missing-root-layout-tags). This
 * nested layout only contributes locale-specific wrapping: the
 * `NextIntlClientProvider` and the `Providers` chain (QueryClient +
 * ThemeProvider + Toaster).
 *
 * Layout choice (intentional, simple):
 *   - The outer wrapper is `<div className="min-h-screen">` — NO flex
 *     column, NO ConditionalFooter. Each page decides its own layout:
 *     - `(app)/*` pages use `<AppShell>` (h-screen + overflow-hidden)
 *       and own their viewport. The wrapper used to be `flex min-h-screen
 *       flex-col` with `flex-1` around children — that created a double
 *       scroll on the dashboard because AppShell (h-screen) inside a
 *       `min-h-screen flex-col` parent expanded the outer to >100vh
 *       (ConditionalFooter was null on app routes, so flex-1 took the
 *       AppShell height, but min-h-screen still allowed vertical
 *       expansion from any sub-pixel rounding + the outer html element
 *       had no `overflow-hidden`). Removing the flex wrapper fixes it.
 *     - Public marketing pages (landing, /privacidad, /jobs/[id])
 *       compose their own `<main>` + `<Footer>` and apply
 *       `min-h-screen` themselves.
 *     - Auth forms (login, signup, forgot/reset-password) render their
 *       own layout (centered card, no footer in the auth flow).
 *
 * `generateStaticParams` precomputes one entry per supported locale
 * so `next build` can statically render every locale variant of each
 * route under `[locale]/`.
 *
 * `setRequestLocale(locale)` is REQUIRED by next-intl 3.x+ for static
 * rendering — without this, every server-component child that calls
 * `useTranslations` would log "static rendering not enabled" warnings.
 *
 * Closes REQ-I18N-005 (dynamic `<html lang>`), REQ-I18N-018
 * (NextIntlClientProvider boundary), REQ-I18N-020 (locale-aware auth
 * redirects), and the runtime-broken SCN-I18N-002 (was a 404 before
 * slice 16's `[locale]/` migration). Closes the v3 dashboard double-
 * scroll bug by removing the flex wrapper that conflicted with AppShell.
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
        <div className="min-h-screen">{children}</div>
      </NextIntlClientProvider>
    </Providers>
  );
}
