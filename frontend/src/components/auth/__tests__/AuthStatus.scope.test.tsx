import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

const routerPush = vi.fn();
const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), refresh: routerRefresh }),
}));

// Mock useCurrentUser so the AuthStatus component reads auth state
// from the React Query cache instead of calling supabase.auth directly.
const mockUseCurrentUser = vi.fn();
vi.mock("@/hooks/useCurrentUser", () => ({
  useCurrentUser: () => mockUseCurrentUser(),
}));

import { AuthStatus } from "../AuthStatus";

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
  routerRefresh.mockClear();

  // Default for the existing scope tests: a logged-in user via
  // the legacy getSession + onAuthStateChange path (which the
  // hook version does NOT exercise).
  mockSupabaseAuth.auth.getSession.mockResolvedValue({
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
  mockSupabaseAuth.auth.onAuthStateChange.mockImplementation(() => ({
    data: { subscription: { unsubscribe: () => {} } },
  }));

  // Default for the hook test: a logged-in user from the hook.
  mockUseCurrentUser.mockReturnValue({
    data: { id: "u1", email: "u@example.com" },
    isLoading: false,
    isError: false,
  });
});

describe("AuthStatus — scope prop (REQ-AUTH-020)", () => {
  it("SCN-AUTH-020-1: default → signOut called WITHOUT scope arg (local)", async () => {
    const user = userEvent.setup();
    render(<AuthStatus />);

    const logoutBtn = await screen.findByRole("button", { name: /Cerrar sesi/i });
    await user.click(logoutBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledTimes(1);
    });
    // Default behavior unchanged: no scope arg → local sign-out.
    expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledWith();
  });

  it("SCN-AUTH-020-2: scope='global' → signOut called with { scope: 'global' }", async () => {
    const user = userEvent.setup();
    render(<AuthStatus scope="global" />);

    const logoutBtn = await screen.findByRole("button", { name: /Cerrar sesi/i });
    await user.click(logoutBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledWith({ scope: "global" });
  });
});

/**
 * SCN-PDPRSC-004-D — `AuthStatus` consumes `useCurrentUser` for
 * auth state instead of calling `supabase.auth.getSession()` +
 * subscribing to `onAuthStateChange` directly. Sharing the
 * React Query cache with `EmailVerificationBanner` deduplicates
 * `/auth/v1/user` across the two components.
 */
describe("AuthStatus — SCN-PDPRSC-004-D (uses useCurrentUser)", () => {
  it("reads email from useCurrentUser; never calls supabase.auth.getSession", async () => {
    render(<AuthStatus />);

    // The hook returns a user → the email link is rendered.
    expect(await screen.findByText("u@example.com")).toBeInTheDocument();

    // The component reads auth state from the hook's cache,
    // NOT from `supabase.auth.getSession()`. The legacy code
    // path is gone.
    expect(mockSupabaseAuth.auth.getSession).not.toHaveBeenCalled();
  });
});
