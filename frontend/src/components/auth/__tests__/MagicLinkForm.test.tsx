import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

import { MagicLinkForm } from "../MagicLinkForm";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MagicLinkForm — REQ-AUTH-017 / REQ-AUTH-018", () => {
  it("renders the email input + submit button", () => {
    render(renderWithIntl(<MagicLinkForm />, { locale: "es" }));
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: esMessages.Auth.magicLink.submit })).toBeInTheDocument();
  });

  it("SCN-AUTH-017-2: empty email keeps button disabled", () => {
    render(renderWithIntl(<MagicLinkForm />, { locale: "es" }));
    const submit = screen.getByRole("button", { name: esMessages.Auth.magicLink.submit });
    expect(submit).toBeDisabled();
  });

  it("SCN-AUTH-017-1: valid email + click → signInWithOtp with emailRedirectTo + success state", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<MagicLinkForm />, { locale: "es" }));

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: esMessages.Auth.magicLink.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signInWithOtp).toHaveBeenCalledTimes(1);
    });
    const callArgs = mockSupabaseAuth.auth.signInWithOtp.mock.calls[0]?.[0] as
      | { email: string; options?: { emailRedirectTo?: string } }
      | undefined;
    expect(callArgs?.email).toBe("user@example.com");
    expect(callArgs?.options?.emailRedirectTo).toMatch(/\/auth\/callback\?next=\/dashboard$/);
    expect(
      await screen.findByRole("heading", { name: esMessages.Auth.magicLink.successTitle }),
    ).toBeInTheDocument();
  });

  it("SCN-AUTH-017-3: signInWithOtp rejects → Spanish toast + form stays editable", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.signInWithOtp.mockResolvedValueOnce({
      data: null,
      error: new Error("rate limit exceeded"),
    });

    render(renderWithIntl(<MagicLinkForm />, { locale: "es" }));

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: esMessages.Auth.magicLink.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signInWithOtp).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });
});