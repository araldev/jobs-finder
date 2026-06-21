import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

const routerPush = vi.fn();
const routerReplace = vi.fn();
const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: routerReplace, refresh: routerRefresh }),
}));

import { ResetPasswordForm } from "../ResetPasswordForm";

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
  routerReplace.mockClear();
});

describe("ResetPasswordForm — REQ-AUTH-004 / REQ-AUTH-005", () => {
  it("renders new-password + confirm inputs + submit button", () => {
    render(<ResetPasswordForm />);
    expect(screen.getByLabelText(authCopy.reset.newPasswordLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(authCopy.reset.confirmPasswordLabel)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: authCopy.reset.submit })).toBeInTheDocument();
  });

  it("SCN-AUTH-005-1: 5-char password → submit disabled + inline 'Mínimo 6 caracteres'", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    const newPassword = screen.getByLabelText(authCopy.reset.newPasswordLabel);
    const confirm = screen.getByLabelText(authCopy.reset.confirmPasswordLabel);

    await user.type(newPassword, "abcde");
    await user.type(confirm, "abcde");

    const submit = screen.getByRole("button", { name: authCopy.reset.submit });
    expect(submit).toBeDisabled();
    await waitFor(() => {
      expect(newPassword).toHaveAttribute("aria-invalid", "true");
    });
  });

  it("SCN-AUTH-005-2: mismatched passwords → submit disabled + 'Las contraseñas no coinciden'", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(authCopy.reset.newPasswordLabel), "abc123");
    await user.type(screen.getByLabelText(authCopy.reset.confirmPasswordLabel), "abc124");

    const submit = screen.getByRole("button", { name: authCopy.reset.submit });
    expect(submit).toBeDisabled();
    const liveRegion = await screen.findByText(authCopy.validation.passwordsDoNotMatch);
    expect(liveRegion).toBeInTheDocument();
  });

  it("SCN-AUTH-005-3: aria-invalid + data-invalid + aria-live all wired", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(authCopy.reset.newPasswordLabel), "x");

    await waitFor(() => {
      const newPassword = screen.getByLabelText(authCopy.reset.newPasswordLabel);
      expect(newPassword).toHaveAttribute("aria-invalid", "true");
    });
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toBeInTheDocument();
  });

  it("success: calls updateUser({ password }) once → router.replace('/dashboard')", async () => {
    const user = userEvent.setup();
    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(authCopy.reset.newPasswordLabel), "newpass1");
    await user.type(screen.getByLabelText(authCopy.reset.confirmPasswordLabel), "newpass1");
    await user.click(screen.getByRole("button", { name: authCopy.reset.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledWith({ password: "newpass1" });
    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("error: updateUser rejects → form stays editable (Spanish toast, no auto-redirect)", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.updateUser.mockResolvedValueOnce({
      data: null,
      error: new Error("weak password"),
    });

    render(<ResetPasswordForm />);

    await user.type(screen.getByLabelText(authCopy.reset.newPasswordLabel), "newpass1");
    await user.type(screen.getByLabelText(authCopy.reset.confirmPasswordLabel), "newpass1");
    await user.click(screen.getByRole("button", { name: authCopy.reset.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByLabelText(authCopy.reset.newPasswordLabel)).toBeInTheDocument();
    expect(routerReplace).not.toHaveBeenCalled();
  });
});
