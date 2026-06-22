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
const dummyMessages = {
  Common: { loading: "Cargando…" },
};

/**
 * RSC layouts are async functions; `render()` from @testing-library/react
 * expects a sync ReactElement. We invoke the layout function (returning a
 * Promise<ReactElement>) and pass the awaited element to render().
 *
 * In Next.js 15, layout `params` is a Promise. The
 * `app/[locale]/layout.tsx` reads `locale` from `await params`, so we
 * pass `Promise.resolve({ locale: ... })` here.
 *
 * The `<html>` and `<body>` tags live in `app/layout.tsx` (Next.js
 * requires them at the root). These tests focus on the
 * locale-specific wrapping: `setRequestLocale` and the
 * NextIntlClientProvider boundary. Footer mounting is the
 * responsibility of each individual page now (added in the
 * fix-frontend-root-layout-tags branch).
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
});
