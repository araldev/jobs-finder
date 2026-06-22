import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMockSupabaseServerClient } from "@/lib/supabase/__mocks__/server";
import esMessages from "@/messages/es.json";

// The page uses the SERVER module (`createClient` from
// `@/lib/supabase/server`), NOT the browser one.
const serverMock = createMockSupabaseServerClient();
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => serverMock,
}));

// Stub the actual form so the page test is about the session branch.
vi.mock("@/components/auth/ResetPasswordForm", () => ({
  ResetPasswordForm: () => (
    <div data-testid="reset-password-form-sentinel">ResetPasswordForm</div>
  ),
}));

// The page calls `getTranslations("Auth.resetPassword")` (next-intl/server)
// at render time. In a test environment there is no server boundary, so
// `getTranslations` resolves to the react-client stub which throws
// "not supported in Client Components" — we replace it with a tiny
// lookup over the ES messages file so the page renders the same strings
// the user would see in the running app.
const resetCopy = esMessages.Auth.resetPassword;
vi.mock("next-intl/server", () => ({
  getTranslations: async (namespace: string) => {
    if (namespace === "Auth.resetPassword") {
      return (key: string) =>
        (resetCopy as Record<string, string>)[key] ?? key;
    }
    throw new Error(`unmocked namespace: ${namespace}`);
  },
}));

beforeEach(() => {
  serverMock.auth.getSession.mockReset();
});

describe("reset-password page (REQ-AUTH-004)", () => {
  it("SCN-AUTH-004-1: NO active session → shows invalid-link copy + 'Volver a solicitar' anchor; form NOT rendered", async () => {
    serverMock.auth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null });

    const Page = (await import("../page")).default;
    const page = await Page();
    render(page);

    expect(await screen.findByText(resetCopy.invalidLinkTitle)).toBeInTheDocument();
    expect(screen.queryByTestId("reset-password-form-sentinel")).not.toBeInTheDocument();
  });

  it("SCN-AUTH-004-1: invalid-link anchor points to /forgot-password", async () => {
    serverMock.auth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null });

    const Page = (await import("../page")).default;
    const page = await Page();
    render(page);

    const link = await screen.findByRole("link", { name: resetCopy.resendLink });
    expect(link).toHaveAttribute("href", "/forgot-password");
  });

  it("SCN-AUTH-004-2: active recovery session → renders the ResetPasswordForm", async () => {
    serverMock.auth.getSession.mockResolvedValueOnce({
      data: {
        session: {
          access_token: "tok",
          refresh_token: "ref",
          expires_in: 3600,
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          token_type: "bearer",
          user: { id: "u1", email: "u@example.com" },
        },
      },
      error: null,
    });

    const Page = (await import("../page")).default;
    const page = await Page();
    render(page);
    expect(await screen.findByTestId("reset-password-form-sentinel")).toBeInTheDocument();
  });
});
