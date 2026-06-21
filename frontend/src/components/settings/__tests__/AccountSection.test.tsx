import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Stub the 3 sub-components so AccountSection tests are about composition.
vi.mock("../ChangePasswordForm", () => ({
  ChangePasswordForm: () => (
    <div data-testid="change-password-form-sentinel">ChangePasswordForm</div>
  ),
}));
vi.mock("../GlobalSignoutButton", () => ({
  GlobalSignoutButton: () => (
    <div data-testid="global-signout-sentinel">GlobalSignoutButton</div>
  ),
}));
vi.mock("../DeleteAccountDialog", () => ({
  DeleteAccountDialog: () => (
    <div data-testid="delete-account-sentinel">DeleteAccountDialog</div>
  ),
}));

import { AccountSection } from "../AccountSection";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AccountSection — REQ-AUTH-013 / REQ-AUTH-014", () => {
  it("renders the section heading + the 3 sub-components", () => {
    render(<AccountSection />);
    // CardTitle is a styled <div>, not a heading; assert by text in
    // a more specific scope (CardHeader).
    const headers = screen.getAllByText(/Cuenta/i);
    expect(headers.length).toBeGreaterThan(0);
    expect(screen.getByTestId("change-password-form-sentinel")).toBeInTheDocument();
    expect(screen.getByTestId("global-signout-sentinel")).toBeInTheDocument();
    expect(screen.getByTestId("delete-account-sentinel")).toBeInTheDocument();
  });

  it("SCN-AUTH-013-1: destructive sub-card has border-destructive/40 styling AND is the LAST sub-card", () => {
    const { container } = render(<AccountSection />);

    // The destructive sub-card is the wrapper around DeleteAccountDialog.
    const destructiveWrapper = screen.getByTestId("delete-account-sentinel").parentElement;
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
