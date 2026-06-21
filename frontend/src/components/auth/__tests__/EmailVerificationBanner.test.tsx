import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";

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

    render(<EmailVerificationBanner />);

    expect(
      await screen.findByRole("alert"),
    ).toBeInTheDocument();
    expect(screen.getByText(authCopy.banner.title)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: authCopy.banner.resend })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: authCopy.banner.dismiss })).toBeInTheDocument();
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

    const { container } = render(<EmailVerificationBanner />);
    // Give the effect a tick to run
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')).toBeNull();
    });
    expect(screen.queryByText(authCopy.banner.title)).not.toBeInTheDocument();
  });

  it("SCN-AUTH-007-2: calls getUser (NOT getSession) on mount", async () => {
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

    render(<EmailVerificationBanner />);

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.getUser).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.auth.getSession).not.toHaveBeenCalled();
  });

  it("SCN-AUTH-007-1: SIGNED_IN event with email_confirmed_at → banner disappears on re-render", async () => {
    // 1st render: unverified user
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
    // Capture the onAuthStateChange callback
    const capturedCb: ((event: string, session: unknown) => void) | null = null;
    const cbRef: { current: ((event: string, session: unknown) => void) | null } = {
      current: capturedCb,
    };
    mockSupabaseAuth.auth.onAuthStateChange.mockImplementationOnce(
      (cb: (event: string, session: unknown) => void) => {
        cbRef.current = cb;
        return { data: { subscription: { unsubscribe: () => {} } } };
      },
    );

    const { rerender, container } = render(<EmailVerificationBanner />);
    await screen.findByRole("alert");

    // Simulate SIGNED_IN event with verified email
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
    cbRef.current?.("SIGNED_IN", { user: { email_confirmed_at: "2026-06-20T00:00:00Z" } });

    // Re-render triggers getUser again → returns verified → banner hides
    rerender(<EmailVerificationBanner />);
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')).toBeNull();
    });
  });

  it("SCN-AUTH-008-1: 'Reenviar email' → resend({ type: 'signup', email })", async () => {
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
    mockSupabaseAuth.auth.resend.mockResolvedValueOnce({
      data: { user: { id: "user-1", email: "user@example.com" } },
      error: null,
    });

    render(<EmailVerificationBanner />);
    const resendBtn = await screen.findByRole("button", { name: authCopy.banner.resend });
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
        user: {
          id: "user-1",
          email: "user@example.com",
          email_confirmed_at: null,
        },
      },
      error: null,
    });

    const { container, rerender } = render(<EmailVerificationBanner />);
    await screen.findByRole("alert");

    fireEvent.click(screen.getByRole("button", { name: authCopy.banner.dismiss }));

    await waitFor(() => {
      expect(sessionStorage.getItem("jf-verify-banner-dismissed")).toBe("1");
    });
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')).toBeNull();
    });

    // Clear flag → banner returns
    sessionStorage.removeItem("jf-verify-banner-dismissed");
    rerender(<EmailVerificationBanner />);
    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeInTheDocument();
    });
  });

  it("SCN-AUTH-008-3: V2 non-gating — does NOT call router.push or router.replace", async () => {
    const push = vi.fn();
    const replace = vi.fn();
    vi.doMock("next/navigation", () => ({
      useRouter: () => ({ push, replace, refresh: vi.fn() }),
    }));

    mockSupabaseAuth.auth.getUser.mockResolvedValue({
      data: {
        user: {
          id: "user-1",
          email: "user@example.com",
          email_confirmed_at: null,
        },
      },
      error: null,
    });

    render(<EmailVerificationBanner />);
    await screen.findByRole("alert");

    // Click both buttons; neither should redirect.
    fireEvent.click(screen.getByRole("button", { name: authCopy.banner.resend }));
    fireEvent.click(screen.getByRole("button", { name: authCopy.banner.dismiss }));

    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();

    vi.doUnmock("next/navigation");
  });

  it("REQ-AUTH-026: no console.log call contains an email or @example.com", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

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

    render(<EmailVerificationBanner />);
    await screen.findByRole("alert");

    const allCalls = [
      ...logSpy.mock.calls,
      ...errorSpy.mock.calls,
      ...warnSpy.mock.calls,
    ];
    for (const call of allCalls) {
      for (const arg of call) {
        const text = String(arg);
        expect(text).not.toContain("user@example.com");
        expect(text).not.toMatch(/@example\.com/);
      }
    }

    logSpy.mockRestore();
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
