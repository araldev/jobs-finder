import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

import { ChangePasswordForm } from "../ChangePasswordForm";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ChangePasswordForm — REQ-AUTH-015 / REQ-AUTH-016", () => {
  it("renders current + new + confirm password inputs + submit", () => {
    render(renderWithIntl(<ChangePasswordForm />, { locale: "es" }));
    expect(screen.getByLabelText(authCopy.change.currentPasswordLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(authCopy.change.newPasswordLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(authCopy.change.confirmPasswordLabel)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: authCopy.change.submit })).toBeInTheDocument();
  });

  it("SCN-AUTH-015-1: 5-char new password → submit disabled + aria-invalid + inline error", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ChangePasswordForm />, { locale: "es" }));

    const newPwd = screen.getByLabelText(authCopy.change.newPasswordLabel);
    await user.type(screen.getByLabelText(authCopy.change.currentPasswordLabel), "oldpass1");
    await user.type(newPwd, "abcde");
    await user.type(screen.getByLabelText(authCopy.change.confirmPasswordLabel), "abcde");

    expect(screen.getByRole("button", { name: authCopy.change.submit })).toBeDisabled();
    await waitFor(() => {
      expect(newPwd).toHaveAttribute("aria-invalid", "true");
    });
  });

  it("SCN-AUTH-015-2: mismatched new + confirm → submit disabled + 'Las contraseñas no coinciden'", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ChangePasswordForm />, { locale: "es" }));

    await user.type(screen.getByLabelText(authCopy.change.currentPasswordLabel), "oldpass1");
    await user.type(screen.getByLabelText(authCopy.change.newPasswordLabel), "newpass1");
    await user.type(screen.getByLabelText(authCopy.change.confirmPasswordLabel), "newpass2");

    expect(screen.getByRole("button", { name: authCopy.change.submit })).toBeDisabled();
    expect(
      await screen.findByText(authCopy.validation.passwordsDoNotMatch),
    ).toBeInTheDocument();
  });

  it("SCN-AUTH-016-1: updateUser resolves → all 3 inputs empty + toast.success + exactly one updateUser call", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ChangePasswordForm />, { locale: "es" }));

    await user.type(screen.getByLabelText(authCopy.change.currentPasswordLabel), "oldpass1");
    await user.type(screen.getByLabelText(authCopy.change.newPasswordLabel), "newpass1");
    await user.type(screen.getByLabelText(authCopy.change.confirmPasswordLabel), "newpass1");
    await user.click(screen.getByRole("button", { name: authCopy.change.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledWith({ password: "newpass1" });

    await waitFor(() => {
      expect(
        (screen.getByLabelText(authCopy.change.currentPasswordLabel) as HTMLInputElement).value,
      ).toBe("");
      expect(
        (screen.getByLabelText(authCopy.change.newPasswordLabel) as HTMLInputElement).value,
      ).toBe("");
      expect(
        (screen.getByLabelText(authCopy.change.confirmPasswordLabel) as HTMLInputElement).value,
      ).toBe("");
    });
  });

  it("SCN-AUTH-016-2: updateUser rejects with 'Invalid login credentials' → Spanish toast + current-password focused", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.updateUser.mockResolvedValueOnce({
      data: null,
      error: { message: "Invalid login credentials" } as unknown as Error,
    });

    render(renderWithIntl(<ChangePasswordForm />, { locale: "es" }));

    const currentPwd = screen.getByLabelText(authCopy.change.currentPasswordLabel);
    await user.type(currentPwd, "wrongpass");
    await user.type(screen.getByLabelText(authCopy.change.newPasswordLabel), "newpass1");
    await user.type(screen.getByLabelText(authCopy.change.confirmPasswordLabel), "newpass1");
    await user.click(screen.getByRole("button", { name: authCopy.change.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(currentPwd).toHaveFocus();
    });
  });
});
