import type { Metadata } from "next";
import { cookies } from "next/headers";
import { DM_Sans, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/**
 * Root layout — required by Next.js 15.
 *
 * Owns the `<html>` and `<body>` tags + the global CSS import.
 * Next.js requires these tags to live in `app/layout.tsx` (not in a
 * nested segment layout) — see:
 * https://nextjs.org/docs/messages/missing-root-layout-tags
 *
 * The `<html lang>` is derived from the `NEXT_LOCALE` cookie (set by
 * the LanguageSwitcher and mirrored in localStorage). This makes the
 * root layout locale-aware WITHOUT requiring it to know about the
 * `[locale]/` segment params. Default falls back to `"es"` (the
 * configured `defaultLocale` in `frontend/src/i18n/routing.ts`).
 *
 * The `suppressHydrationWarning` flag is required because the
 * next-themes `<ThemeProvider>` flips a `class` attribute on the
 * `<html>` element client-side; without this flag React would log a
 * hydration warning on every theme switch.
 *
 * Locale-specific provider wiring (NextIntlClientProvider, QueryClient,
 * sonner Toaster, ConditionalFooter) lives in
 * `app/[locale]/layout.tsx` so it has access to the `[locale]` params.
 *
 * Closes REQ-I18N-005 (dynamic `<html lang>`) — root now reads the
 * NEXT_LOCALE cookie and propagates the value to the html element.
 *
 * Closes REQ-PDPRSC-005 (next/font/google self-hosting) — the 3
 * fonts are imported via `next/font/google` (build-time woff2
 * download, served from `_next/static/media/`) instead of an
 * `@import url(https://fonts.googleapis.com/...)` line in
 * `globals.css`. The generated `.variable` classes are applied to
 * `<body>` and the CSS variables (`--font-inter`,
 * `--font-dm-sans`, `--font-jetbrains-mono`) are consumed by
 * `tailwind.config.ts`'s `fontFamily.{sans,display,mono}` keys.
 * Zero runtime requests to `fonts.googleapis.com` /
 * `fonts.gstatic.com`; `size-adjust` injected by `next/font`
 * prevents font-swap CLS.
 */
export const metadata: Metadata = {
  title: "Jobs Finder",
  description:
    "Find your next job across LinkedIn, Indeed, and InfoJobs.",
  icons: {
    icon: "/favicon.svg",
  },
};

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get("NEXT_LOCALE")?.value;
  const locale: "es" | "en" = cookieLocale === "en" ? "en" : "es";

  return (
    <html lang={locale} suppressHydrationWarning>
      <body
        className={`${inter.variable} ${dmSans.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
