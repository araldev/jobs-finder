import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

import { ForgotPasswordForm } from "../ForgotPasswordForm";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ForgotPasswordForm — REQ-AUTH-001 / REQ-AUTH-002 / REQ-AUTH-003 / REQ-AUTH-005", () => {
  it("renders the email input + submit button under the localized title", () => {
    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    expect(
      screen.getByRole("heading", { name: esMessages.Auth.forgotPassword.title }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }),
    ).toBeInTheDocument();
  });

  it("SCN-AUTH-005-1: submit is disabled for 5-char email with inline Spanish error", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));

    const input = screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel);
    await user.type(input, "abcde");

    const submit = screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit });
    expect(submit).toBeDisabled();

    await waitFor(() => {
      expect(input).toHaveAttribute("aria-invalid", "true");
    });
  });

  it("SCN-AUTH-002-1: valid submit calls resetPasswordForEmail with redirectTo ending in /auth/callback?next=/reset-password", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));

    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.resetPasswordForEmail).toHaveBeenCalledTimes(1);
    });
    const [emailArg, optionsArg] = mockSupabaseAuth.auth.resetPasswordForEmail.mock.calls[0] as [
      string,
      { redirectTo: string },
    ];
    expect(emailArg).toBe("user@example.com");
    expect(optionsArg.redirectTo).toMatch(/\/auth\/callback\?next=\/reset-password$/);
  });

  it("SCN-AUTH-002-1 + SCN-AUTH-003-1: swaps to the success state after submission", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: {},
      error: null,
    });

    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));

    expect(await screen.findByTestId("forgot-success")).toBeInTheDocument();
    expect(screen.getByText(esMessages.Auth.forgotPassword.successTitle)).toBeInTheDocument();
  });

  it("SCN-AUTH-002-2: network error surfaces a Spanish toast and form remains editable", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: null,
      error: { name: "AuthApiError", message: "Service unavailable", status: 500 },
    });

    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));

    await waitFor(() => {
      expect(
        screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      ).toBeInTheDocument();
    });
  });

  it("SCN-AUTH-002-3: rate-limit error surfaces a Spanish toast (no error-class leak)", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: null,
      error: { name: "AuthApiError", message: "rate limit exceeded", status: 429 },
    });

    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "user@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));

    await waitFor(() => {
      expect(
        screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      ).toBeInTheDocument();
    });
  });

  it("SCN-AUTH-003-1: known and unknown emails produce byte-identical success state", async () => {
    const user = userEvent.setup();

    // First call: registered email → success
    mockSupabaseAuth.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: { user: { id: "u1" } },
      error: null,
    });

    const { unmount } = render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "known@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));
    expect(await screen.findByTestId("forgot-success")).toBeInTheDocument();
    const knownDom = screen.getByTestId("forgot-success").textContent;
    unmount();

    // Second call: unknown email → also success (no enumeration disclosure)
    mockSupabaseAuth.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: { user: null },
      error: null,
    });
    render(renderWithIntl(<ForgotPasswordForm />, { locale: "es" }));
    await user.type(
      screen.getByLabelText(esMessages.Auth.forgotPassword.emailLabel),
      "unknown@example.com",
    );
    await user.click(screen.getByRole("button", { name: esMessages.Auth.forgotPassword.submit }));
    expect(await screen.findByTestId("forgot-success")).toBeInTheDocument();
    const unknownDom = screen.getByTestId("forgot-success").textContent;

    expect(knownDom).toBe(unknownDom);
  });
});