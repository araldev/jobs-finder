import type { Metadata } from "next";

/**
 * Root layout — required by Next.js, but minimal.
 *
 * All locale-specific layout lives in `app/[locale]/layout.tsx`
 * (which sets the dynamic `<html lang>`, wraps children in
 * `NextIntlClientProvider`, and renders the providers chain).
 *
 * The reason for the split is next-intl 4.x's standard pattern:
 * `app/[locale]/` is the localized segment, so the locale parameter
 * is available to `setRequestLocale(locale)` and `getMessages()`
 * before the children render. The root layout exists only to
 * satisfy Next.js's requirement that `app/layout.tsx` be present.
 *
 * See: https://next-intl.dev/docs/getting-started/app-router/with-i18n-routing
 */

export const metadata: Metadata = {
  title: "Jobs Finder",
  description:
    "Find your next job across LinkedIn, Indeed, and InfoJobs.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return children;
}