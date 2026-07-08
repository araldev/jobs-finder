import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

const usePathnameMock = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

vi.mock("../ThemeToggle", () => ({
  ThemeToggle: () => null,
}));

vi.mock("../LanguageSwitcher", () => ({
  LanguageSwitcher: () => null,
}));

vi.mock("@/components/auth/AuthStatus", () => ({
  AuthStatus: () => null,
}));

vi.mock("@/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ data: null }),
}));

// Import after the mocks are registered.
import { Header } from "../Header";

function renderHeader(locale: "es" | "en" = "es") {
  const messages = locale === "es" ? esMessages : enMessages;
  return render(
    <NextIntlClientProvider locale={locale} messages={messages}>
      <Header />
    </NextIntlClientProvider>,
  );
}

describe("Header — page name resolution (bilingual)", () => {
  beforeEach(() => {
    usePathnameMock.mockReset();
  });

  it.each([
    { path: "/dashboard", es: "Panel", en: "Dashboard" },
    { path: "/search", es: "Buscar", en: "Search" },
    { path: "/favorites", es: "Favoritos", en: "Favorites" },
    { path: "/settings", es: "Configuración", en: "Settings" },
    { path: "/jobs/abc-123", es: "Detalle de empleo", en: "Job Detail" },
  ])(
    "route '$path' → ES='$es' / EN='$en'",
    ({ path, es, en }) => {
      usePathnameMock.mockReturnValue(path);

      // Spanish locale
      usePathnameMock.mockReturnValue(path);
      const { unmount } = renderHeader("es");
      const h1Es = document.querySelector("h1");
      expect(h1Es?.textContent).toContain(es);
      unmount();

      // English locale
      usePathnameMock.mockReturnValue(path);
      renderHeader("en");
      const h1En = document.querySelector("h1");
      expect(h1En?.textContent).toContain(en);
    },
  );

  it("unknown route → 'Jobs Finder' fallback (never 'JobsBoard')", () => {
    usePathnameMock.mockReturnValue("/totally-unknown");

    const { unmount } = renderHeader("es");
    const h1Es = document.querySelector("h1");
    expect(h1Es?.textContent).toContain("Jobs Finder");
    expect(h1Es?.textContent).not.toContain("JobsBoard");
    unmount();

    renderHeader("en");
    const h1En = document.querySelector("h1");
    expect(h1En?.textContent).toContain("Jobs Finder");
    expect(h1En?.textContent).not.toContain("JobsBoard");
  });
});