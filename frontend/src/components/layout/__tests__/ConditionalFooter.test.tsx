import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import esMessages from "@/messages/es.json";

const useSelectedLayoutSegmentMock = vi.fn();

vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: (segment: string) =>
    useSelectedLayoutSegmentMock(segment),
}));

vi.mock("../Footer", () => ({
  Footer: () => <footer data-testid="footer">Footer content</footer>,
}));

// Import after mocks are registered.
import { ConditionalFooter } from "../ConditionalFooter";

function renderConditionalFooter() {
  return render(
    <NextIntlClientProvider locale="es" messages={esMessages}>
      <ConditionalFooter />
    </NextIntlClientProvider>,
  );
}

describe("ConditionalFooter", () => {
  beforeEach(() => {
    useSelectedLayoutSegmentMock.mockReset();
  });

  it("renders Footer on public routes (no active (app) segment)", () => {
    // null return value = the (app) parallel slot has no active segment.
    // This is what happens on /, /login, /signup, /forgot-password,
    // /reset-password, /privacidad, /jobs/[id].
    useSelectedLayoutSegmentMock.mockReturnValue(null);

    renderConditionalFooter();

    expect(screen.getByTestId("footer")).toBeInTheDocument();
  });

  it("hides Footer on (app) routes (active segment in the (app) slot)", () => {
    // A non-null return = some (app) child is active (dashboard, search,
    // favorites, settings). The Footer must NOT render, otherwise it
    // appears below AppShell's h-screen frame — the dangling-Footer bug.
    useSelectedLayoutSegmentMock.mockReturnValue("dashboard");

    renderConditionalFooter();

    expect(screen.queryByTestId("footer")).not.toBeInTheDocument();
  });

  it("queries the (app) segment slot by name", () => {
    useSelectedLayoutSegmentMock.mockReturnValue(null);

    renderConditionalFooter();

    // Must pass the literal "(app)" string so Next resolves the
    // matching parallel slot rather than the top-level segment.
    expect(useSelectedLayoutSegmentMock).toHaveBeenCalledWith("(app)");
  });
});
