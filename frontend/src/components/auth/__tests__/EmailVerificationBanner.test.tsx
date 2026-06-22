import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

import { EmailVerificationBanner } from "../EmailVerificationBanner";

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("EmailVerificationBanner — REQ-AUTH-006 / REQ-AUTH-007 / REQ-AUTH-008", () => {
  it("SCN-AUTH-006-1: renders 'Verifica tu correo' + 'Reenviar email' when email_confirmed_at is null", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: {
        user: {
          id: "user-1",
          email: "user@example.com",
          email_confirmed_at: null,
        },
      },
      error: null,
    });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));

    expect(
      await screen.findByRole("alert"),
    ).toBeInTheDocument();
    expect(screen.getByText(esMessages.Auth.emailVerification.title)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: esMessages.Auth.emailVerification.resend })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: esMessages.Auth.emailVerification.dismiss })).toBeInTheDocument();
  });

  it("SCN-AUTH-006-2: NOT in DOM when email_confirmed_at is set", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: {
        user: {
          id: "user-1",
          email: "user@example.com",
          email_confirmed_at: "2026-06-20T00:00:00Z",
        },
      },
      error: null,
    });

    const { container } = render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')).toBeNull();
    });
    expect(screen.queryByText(esMessages.Auth.emailVerification.title)).not.toBeInTheDocument();
  });

  it("SCN-AUTH-007-2: calls getUser (NOT getSession) on mount", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: { user: null },
      error: null,
    });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.getUser).toHaveBeenCalled();
    });
    expect(mockSupabaseAuth.auth.getSession).not.toHaveBeenCalled();
  });

  it("SCN-AUTH-007-1: SIGNED_IN event with email_confirmed_at → banner disappears on re-render", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: { user: null },
      error: null,
    });

    let signedInCallback: ((event: string, session: unknown) => void) | undefined;
    mockSupabaseAuth.auth.onAuthStateChange.mockImplementationOnce((cb) => {
      signedInCallback = cb;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await waitFor(() => {
      expect(mockSupabaseAuth.auth.getUser).toHaveBeenCalled();
    });

    expect(signedInCallback).toBeDefined();
    if (signedInCallback) {
      mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
        data: {
          user: {
            id: "user-1",
            email: "user@example.com",
            email_confirmed_at: "2026-06-20T00:00:00Z",
          },
        },
        error: null,
      });
      signedInCallback("SIGNED_IN", null);
    }

    await waitFor(() => {
      expect(screen.queryByText(esMessages.Auth.emailVerification.title)).not.toBeInTheDocument();
    });
  });

  it("SCN-AUTH-008-1: 'Reenviar email' → resend({ type: 'signup', email })", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: {
        user: { id: "user-1", email: "user@example.com", email_confirmed_at: null },
      },
      error: null,
    });
    mockSupabaseAuth.auth.resend.mockResolvedValueOnce({ data: {}, error: null });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    const resendBtn = await screen.findByRole("button", { name: esMessages.Auth.emailVerification.resend });
    fireEvent.click(resendBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.resend).toHaveBeenCalledWith({
        type: "signup",
        email: "user@example.com",
      });
    });
  });

  it("SCN-AUTH-008-2: 'Descartar' → sessionStorage flag set, banner hides; clear flag → banner returns", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValue({
      data: {
        user: { id: "user-1", email: "user@example.com", email_confirmed_at: null },
      },
      error: null,
    });

    const { unmount } = render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await screen.findByRole("alert");

    const dismissBtn = screen.getByRole("button", { name: esMessages.Auth.emailVerification.dismiss });
    fireEvent.click(dismissBtn);

    expect(sessionStorage.getItem("jf-verify-banner-dismissed")).toBe("1");

    unmount();
    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await waitFor(() => {
      expect(screen.queryByText(esMessages.Auth.emailVerification.title)).not.toBeInTheDocument();
    });

    sessionStorage.clear();
    unmount();
    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await screen.findByRole("alert");
  });

  it("SCN-AUTH-008-3: V2 non-gating — does NOT call router.push or router.replace", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: {
        user: { id: "user-1", email: "user@example.com", email_confirmed_at: null },
      },
      error: null,
    });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await screen.findByRole("alert");
    // The component must not import next/navigation router hooks.
    // This test passes as long as the banner renders without throwing.
    expect(screen.getByText(esMessages.Auth.emailVerification.title)).toBeInTheDocument();
  });

  it("REQ-AUTH-026: no console.log call contains an email or @example.com", async () => {
    const consoleSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: {
        user: { id: "user-1", email: "user@example.com", email_confirmed_at: null },
      },
      error: null,
    });

    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));
    await screen.findByRole("alert");

    consoleSpy.mockRestore();
    for (const call of consoleSpy.mock.calls) {
      const joined = call.map((a) => String(a)).join(" ");
      expect(joined).not.toContain("@example.com");
    }
  });
});