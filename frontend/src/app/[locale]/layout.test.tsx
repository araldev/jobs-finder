import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

const localeMock = vi.fn();
const messagesMock = vi.fn();
const setRequestLocaleMock = vi.fn();

vi.mock("next-intl/server", () => ({
  getLocale: () => localeMock(),
  getMessages: () => messagesMock(),
  setRequestLocale: (locale: string) => setRequestLocaleMock(locale),
}));

vi.mock("@/app/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Minimal messages payload so getMessages resolves without errors.
// The exact shape is irrelevant to the lang-attribute assertion.
// `Footer` is mounted by the layout — include its keys so the test
// doesn't emit MISSING_MESSAGE warnings for production code (W9 in
// sdd/feat-frontend-i18n/verify-report).
const dummyMessages = {
  Common: { loading: "Cargando…" },
  Footer: {
    privacyNote: "Solo en español",
    privacy: "Privacidad",
    copyright: "© Jobs Finder",
  },
};

/**
 * RSC layouts are async functions; `render()` from @testing-library/react
 * expects a sync ReactElement. We invoke the layout function (returning a
 * Promise<ReactElement>) and pass the awaited element to render().
 *
 * In Next.js 15, layout `params` is a Promise. The new
 * `app/[locale]/layout.tsx` reads `locale` from `await params`, so we
 * pass `Promise.resolve({ locale: ... })` here.
 */
async function renderLayout(locale: string) {
  const { default: LocaleLayout } = await import("./layout");
  const element = await LocaleLayout({
    children: createElement("div", null, "child"),
    params: Promise.resolve({ locale }),
  });
  return render(element as React.ReactElement);
}

describe("LocaleLayout — dynamic <html lang>", () => {
  beforeEach(() => {
    localeMock.mockReset();
    messagesMock.mockReset();
    setRequestLocaleMock.mockReset();
    messagesMock.mockResolvedValue(dummyMessages);
  });

  it("renders <html lang='es'> for the default-locale segment (e.g. /dashboard)", async () => {
    await renderLayout("es");

    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("es");
  });

  it("renders <html lang='en'> for the /en/ prefix", async () => {
    await renderLayout("en");

    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("en");
  });

  it("calls setRequestLocale with the resolved locale (next-intl 3.x+ requirement)", async () => {
    await renderLayout("en");

    expect(setRequestLocaleMock).toHaveBeenCalledWith("en");
  });

  it("renders children inside NextIntlClientProvider", async () => {
    await renderLayout("es");

    expect(screen.getByText("child")).toBeTruthy();
  });
});