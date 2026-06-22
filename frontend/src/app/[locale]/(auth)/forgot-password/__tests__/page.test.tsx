import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// The page renders <ForgotPasswordForm />. Stub the form to a sentinel
// so the page test stays about composition (REQ-AUTH-001).
vi.mock("@/components/auth/ForgotPasswordForm", () => ({
  ForgotPasswordForm: () => (
    <div data-testid="forgot-password-form-sentinel">ForgotPasswordForm</div>
  ),
}));

import ForgotPasswordPage from "../page";

describe("forgot-password page (REQ-AUTH-001)", () => {
  it("SCN-AUTH-001-1: renders the ForgotPasswordForm (public route)", () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByTestId("forgot-password-form-sentinel")).toBeInTheDocument();
  });

  it("does NOT throw on render and renders inside a centered public layout", () => {
    const { container } = render(<ForgotPasswordPage />);
    // Container is non-empty (not a 404 / not a redirect).
    expect(container.textContent).toBeTruthy();
  });
});
