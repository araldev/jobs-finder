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

import { AuthStatus } from "../AuthStatus";

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
  routerRefresh.mockClear();

  // Default: a logged-in user (so the "Cerrar sesión" button is shown)
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
