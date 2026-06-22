import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

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
    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));
    expect(screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel)).toBeInTheDocument();
    expect(screen.getByLabelText(esMessages.Auth.resetPassword.confirmPasswordLabel)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: esMessages.Auth.resetPassword.submit })).toBeInTheDocument();
  });

  it("SCN-AUTH-005-1: 5-char password → submit disabled + inline 'Mínimo 6 caracteres'", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));

    const newPassword = screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel);
    const confirm = screen.getByLabelText(esMessages.Auth.resetPassword.confirmPasswordLabel);

    await user.type(newPassword, "abcde");
    await user.type(confirm, "abcde");

    const submit = screen.getByRole("button", { name: esMessages.Auth.resetPassword.submit });
    expect(submit).toBeDisabled();
    await waitFor(() => {
      expect(newPassword).toHaveAttribute("aria-invalid", "true");
    });
  });

  it("SCN-AUTH-005-2: mismatched passwords → submit disabled + 'Las contraseñas no coinciden'", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));

    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel),
      "abc123",
    );
    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.confirmPasswordLabel),
      "abc124",
    );

    const submit = screen.getByRole("button", { name: esMessages.Auth.resetPassword.submit });
    expect(submit).toBeDisabled();
    const liveRegion = await screen.findByText(esMessages.Validation.passwordsDoNotMatch);
    expect(liveRegion).toBeInTheDocument();
  });

  it("SCN-AUTH-005-3: aria-invalid + data-invalid + aria-live all wired", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));

    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel),
      "x",
    );

    await waitFor(() => {
      const newPassword = screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel);
      expect(newPassword).toHaveAttribute("aria-invalid", "true");
    });
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toBeInTheDocument();
  });

  it("success: calls updateUser({ password }) once → router.replace('/dashboard')", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));

    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel),
      "newpass1",
    );
    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.confirmPasswordLabel),
      "newpass1",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.resetPassword.submit }));

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

    render(renderWithIntl(<ResetPasswordForm />, { locale: "es" }));

    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel),
      "newpass1",
    );
    await user.type(
      screen.getByLabelText(esMessages.Auth.resetPassword.confirmPasswordLabel),
      "newpass1",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.resetPassword.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.updateUser).toHaveBeenCalledTimes(1);
    });
    expect(
      screen.getByLabelText(esMessages.Auth.resetPassword.newPasswordLabel),
    ).toBeInTheDocument();
    expect(routerReplace).not.toHaveBeenCalled();
  });
});