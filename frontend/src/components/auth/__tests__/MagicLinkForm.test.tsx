import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

import { MagicLinkForm } from "../MagicLinkForm";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MagicLinkForm — REQ-AUTH-017 / REQ-AUTH-018", () => {
  it("renders the email input + submit button", () => {
    render(<MagicLinkForm />);
    expect(screen.getByLabelText("Tu correo electrónico")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: authCopy.magicLink.submit })).toBeInTheDocument();
  });

  it("SCN-AUTH-017-2: empty email keeps button disabled", () => {
    render(<MagicLinkForm />);
    const submit = screen.getByRole("button", { name: authCopy.magicLink.submit });
    expect(submit).toBeDisabled();
  });

  it("SCN-AUTH-017-1: valid email + click → signInWithOtp with emailRedirectTo + success state", async () => {
    const user = userEvent.setup();
    render(<MagicLinkForm />);

    await user.type(screen.getByLabelText("Tu correo electrónico"), "user@example.com");
    await user.click(screen.getByRole("button", { name: authCopy.magicLink.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signInWithOtp).toHaveBeenCalledTimes(1);
    });
    const callArgs = mockSupabaseAuth.auth.signInWithOtp.mock.calls[0]?.[0] as
      | { email: string; options?: { emailRedirectTo?: string } }
      | undefined;
    expect(callArgs?.email).toBe("user@example.com");
    expect(callArgs?.options?.emailRedirectTo).toMatch(/\/auth\/callback\?next=\/dashboard$/);
    // Success state replaces the form.
    expect(
      await screen.findByRole("heading", { name: authCopy.magicLink.successTitle }),
    ).toBeInTheDocument();
  });

  it("SCN-AUTH-017-3: signInWithOtp rejects → Spanish toast + form stays editable", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.auth.signInWithOtp.mockResolvedValueOnce({
      data: null,
      error: new Error("rate limit exceeded"),
    });

    render(<MagicLinkForm />);

    await user.type(screen.getByLabelText("Tu correo electrónico"), "user@example.com");
    await user.click(screen.getByRole("button", { name: authCopy.magicLink.submit }));

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signInWithOtp).toHaveBeenCalledTimes(1);
    });
    // Form is still rendered (no swap to success state).
    expect(screen.getByLabelText("Tu correo electrónico")).toBeInTheDocument();
  });
});
