import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

const messagesMock = vi.fn();
const setRequestLocaleMock = vi.fn();

vi.mock("next-intl/server", () => ({
  getMessages: () => messagesMock(),
  setRequestLocale: (locale: string) => setRequestLocaleMock(locale),
}));

vi.mock("@/app/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Minimal messages payload so getMessages resolves without errors.
// The exact shape is irrelevant to the unit tests below.
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
 *
 * The `<html>` and `<body>` tags live in `app/layout.tsx` (Next.js
 * requires them at the root). These tests focus on the
 * locale-specific wrapping: `setRequestLocale`, `getMessages`,
 * `NextIntlClientProvider`, and `ConditionalFooter` mounting.
 */
async function renderLayout(locale: string) {
  const { default: LocaleLayout } = await import("./layout");
  const element = await LocaleLayout({
    children: createElement("div", null, "child"),
    params: Promise.resolve({ locale }),
  });
  return render(element as React.ReactElement);
}

describe("LocaleLayout — locale-specific wrapping", () => {
  beforeEach(() => {
    messagesMock.mockReset();
    setRequestLocaleMock.mockReset();
    messagesMock.mockResolvedValue(dummyMessages);
  });

  it("calls setRequestLocale with the resolved locale (next-intl 3.x+ requirement)", async () => {
    await renderLayout("en");

    expect(setRequestLocaleMock).toHaveBeenCalledWith("en");
  });

  it("renders children inside the NextIntlClientProvider boundary", async () => {
    await renderLayout("es");

    expect(screen.getByText("child")).toBeTruthy();
  });

  it("renders the ConditionalFooter on public routes (not the (app) segment)", async () => {
    // useSelectedLayoutSegment("(app)") is null on public routes —
    // ConditionalFooter renders the marketing Footer.
    await renderLayout("es");

    expect(screen.getByText(/Privacidad/)).toBeTruthy();
    expect(screen.getByText(/Jobs Finder/)).toBeTruthy();
  });
});
