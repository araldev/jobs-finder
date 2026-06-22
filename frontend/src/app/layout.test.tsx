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
const dummyMessages = { Common: { loading: "Cargando…" } };

/**
 * RSC layouts are async functions; `render()` from @testing-library/react
 * expects a sync ReactElement. We invoke the layout function (returning a
 * Promise<ReactElement>) and pass the awaited element to render().
 */
async function renderLayout() {
  const { default: RootLayout } = await import("@/app/layout");
  const element = await RootLayout({ children: createElement("div", null, "child") });
  return render(element as React.ReactElement);
}

describe("RootLayout — dynamic <html lang>", () => {
  beforeEach(() => {
    localeMock.mockReset();
    messagesMock.mockReset();
    setRequestLocaleMock.mockReset();
    messagesMock.mockResolvedValue(dummyMessages);
  });

  it("renders <html lang='es'> by default (no locale prefix in URL)", async () => {
    localeMock.mockResolvedValue("es");
    await renderLayout();

    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("es");
  });

  it("renders <html lang='en'> for the /en/ prefix", async () => {
    localeMock.mockResolvedValue("en");
    await renderLayout();

    const html = document.documentElement;
    expect(html.getAttribute("lang")).toBe("en");
  });

  it("calls setRequestLocale with the resolved locale (next-intl 3.x+ requirement)", async () => {
    localeMock.mockResolvedValue("en");
    await renderLayout();

    expect(setRequestLocaleMock).toHaveBeenCalledWith("en");
  });

  it("renders children inside NextIntlClientProvider", async () => {
    localeMock.mockResolvedValue("es");
    await renderLayout();

    expect(screen.getByText("child")).toBeTruthy();
  });
});