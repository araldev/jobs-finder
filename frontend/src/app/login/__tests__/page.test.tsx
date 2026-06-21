import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Stub the actual magic-link form so the login-page test stays
// about composition (REQ-AUTH-018 — the forgot-password link).
vi.mock("@/components/auth/MagicLinkForm", () => ({
  MagicLinkForm: () => (
    <div data-testid="magic-link-form-sentinel">MagicLinkForm</div>
  ),
}));

const routerPush = vi.fn();
const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), refresh: routerRefresh }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
  routerRefresh.mockClear();
  // Login page calls getSession/getUser in some flows.
  mockSupabaseAuth.auth.getSession.mockResolvedValue({
    data: { session: null },
    error: null,
  });
  mockSupabaseAuth.auth.getUser.mockResolvedValue({
    data: { user: null },
    error: null,
  });
  mockSupabaseAuth.auth.signInWithPassword.mockResolvedValue({
    data: { user: { id: "u", email: "u@example.com" } },
    error: null,
  });
});

// Import AFTER mocks are registered.
import LoginPage from "../page";

describe("LoginPage — REQ-AUTH-018", () => {
  it("SCN-AUTH-018-1: renders an <a href='/forgot-password'> with the Spanish 'Olvidaste tu contraseña?' copy that is keyboard-focusable", async () => {
    render(<LoginPage />);
    const link = await screen.findByRole("link", { name: /olvidaste tu contraseña/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/forgot-password");
    // Keyboard focusable — <a href> is focusable by default.
    link.focus();
    expect(link).toHaveFocus();
  });

  it("mounts the MagicLinkForm (the 'Enviar enlace mágico' button lives in the form)", () => {
    render(<LoginPage />);
    expect(screen.getByTestId("magic-link-form-sentinel")).toBeInTheDocument();
  });

  it("still exposes the email/password login form (no regression)", () => {
    render(<LoginPage />);
    // The existing email + password inputs are still rendered.
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /entrar/i })).toBeInTheDocument();
  });

  it("regression: authCopy.forgot.title referenced (no dead copy)", () => {
    expect(authCopy.forgot.title).toBeTruthy();
  });
});
