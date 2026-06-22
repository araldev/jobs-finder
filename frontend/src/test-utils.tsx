import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

export function TestProviders({ children }: { children: ReactNode }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem={false}>
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/**
 * i18n-aware render wrapper. Use for any test that mounts components
 * which call `useTranslations` / `useLocale` from next-intl. Defaults to
 * Spanish (the project's default locale per design D3); pass
 * `{ locale: 'en' }` to render in English.
 *
 * Composes the existing `TestProviders` (react-query + theme) with
 * `<NextIntlClientProvider>` so the consumer doesn't need to nest them
 * manually.
 */
export function renderWithIntl(
  ui: React.ReactElement,
  {
    locale = "es",
    messages = locale === "es" ? esMessages : enMessages,
  }: {
    locale?: "es" | "en";
    messages?: Record<string, unknown>;
  } = {},
) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem={false}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {ui}
        </NextIntlClientProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}