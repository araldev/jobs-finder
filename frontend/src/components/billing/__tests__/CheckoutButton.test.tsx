// Tests for the CheckoutButton — a thin wrapper around a POST to
// /api/billing/checkout that prevents double-click navigation and
// surfaces a sonner toast on failure.
//
// We stub the global fetch so we can assert call counts and the
// button's disabled state during the in-flight period.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));

const mockToast = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => mockToast(...args),
    success: (...args: unknown[]) => mockToast(...args),
  },
}));

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: vi.fn() }),
}));

const mockTranslations: Record<string, string> = {
  "cta.upgrade": "Mejorar a Pro",
  "errors.network": "No se pudo iniciar el checkout. Reintentá.",
};

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    mockTranslations[key] ?? `[missing:${key}]`,
}));

import { CheckoutButton } from "../CheckoutButton";

beforeEach(() => {
  mockToast.mockReset();
  mockPush.mockReset();
});

describe("CheckoutButton — double-click guard + failure toast", () => {
  it("renders the upgrade CTA with the correct label", () => {
    render(<CheckoutButton priceInterval="monthly" />);
    expect(
      screen.getByRole("button", { name: /Mejorar a Pro/i }),
    ).toBeInTheDocument();
  });

  it("POSTs to /api/billing/checkout with the right body on click", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      // A 200 from /api/billing/checkout means "you're already
      // redirected" — for the test we just need fetch to resolve.
      json: async () => ({ url: "https://stripe.example/cs_test" }),
    } as Response);

    const user = userEvent.setup();
    render(<CheckoutButton priceInterval="monthly" />);

    await user.click(screen.getByRole("button", { name: /Mejorar a Pro/i }));

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("/api/billing/checkout");
    const parsedInit = init as RequestInit;
    expect(parsedInit.method).toBe("POST");
    expect(JSON.parse(parsedInit.body as string)).toEqual({
      priceInterval: "monthly",
    });

    fetchSpy.mockRestore();
  });

  it("is DISABLED while the request is in flight (double-click safe)", async () => {
    let resolveFetch!: (value: Response) => void;
    const deferred = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockReturnValueOnce(deferred);

    const user = userEvent.setup();
    render(<CheckoutButton priceInterval="monthly" />);

    const button = screen.getByRole("button", { name: /Mejorar a Pro/i });
    await user.click(button);

    // While the request is in flight, the button is disabled so
    // a second click cannot fire another POST.
    expect(button).toBeDisabled();

    // Resolve so the test cleanup doesn't leak.
    resolveFetch({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);

    fetchSpy.mockRestore();
  });

  it("surfaces a sonner error toast when the POST fails", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as Response);

    const user = userEvent.setup();
    render(<CheckoutButton priceInterval="monthly" />);

    await user.click(screen.getByRole("button", { name: /Mejorar a Pro/i }));

    expect(mockToast).toHaveBeenCalledWith(
      expect.stringMatching(/No se pudo iniciar/i),
    );

    fetchSpy.mockRestore();
  });
});