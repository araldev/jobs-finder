import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Stub the 3 sub-components so AccountSection tests are about composition.
vi.mock("@/components/settings/ChangePasswordForm", () => ({
  ChangePasswordForm: () => (
    <div data-testid="change-password-form-sentinel">ChangePasswordForm</div>
  ),
}));
vi.mock("@/components/settings/GlobalSignoutButton", () => ({
  GlobalSignoutButton: () => (
    <div data-testid="global-signout-sentinel">GlobalSignoutButton</div>
  ),
}));
vi.mock("@/components/settings/DeleteAccountDialog", () => ({
  DeleteAccountDialog: () => (
    <div data-testid="delete-account-sentinel">DeleteAccountDialog</div>
  ),
}));

import { AccountSection } from "../AccountSection";

beforeEach(() => {
  vi.clearAllMocks();
  // AccountSection calls supabase.auth.getUser() to fetch the current
  // user's email for the DeleteAccountDialog's typed-email safeguard.
  mockSupabaseAuth.auth.getUser.mockResolvedValue({
    data: {
      user: {
        id: "user-1",
        email: "user@example.com",
        email_confirmed_at: "2026-06-20T00:00:00Z",
      },
    },
    error: null,
  });
});

describe("AccountSection — REQ-AUTH-013 / REQ-AUTH-014", () => {
  it("renders the section heading + the 3 sub-components", async () => {
    render(<AccountSection />);
    // CardTitle is a styled <div>, not a heading; assert by text in
    // a more specific scope (CardHeader).
    const headers = screen.getAllByText(/Cuenta/i);
    expect(headers.length).toBeGreaterThan(0);
    expect(screen.getByTestId("change-password-form-sentinel")).toBeInTheDocument();
    expect(screen.getByTestId("global-signout-sentinel")).toBeInTheDocument();
    // AccountSection reads getUser() asynchronously — wait for it.
    expect(await screen.findByTestId("delete-account-sentinel")).toBeInTheDocument();
  });

  it("SCN-AUTH-013-1: destructive sub-card has border-destructive/40 styling AND is the LAST sub-card", async () => {
    const { container } = render(<AccountSection />);

    // Wait for the destructive sub-card to render after getUser resolves.
    const deleteSentinel = await screen.findByTestId("delete-account-sentinel");

    // The destructive sub-card is the wrapper around DeleteAccountDialog.
    const destructiveWrapper = deleteSentinel.parentElement;
    expect(destructiveWrapper).not.toBeNull();
    expect(destructiveWrapper!.className).toContain("border-destructive");

    // Document order: change-password, global-signout, delete-account.
    const allSentinels = container.querySelectorAll('[data-testid$="-sentinel"]');
    const ids = Array.from(allSentinels).map((el) => el.getAttribute("data-testid"));
    expect(ids).toEqual([
      "change-password-form-sentinel",
      "global-signout-sentinel",
      "delete-account-sentinel",
    ]);
  });
});
