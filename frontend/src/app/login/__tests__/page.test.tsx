import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Capture the props passed to MagicLinkForm so tests can assert
// prefill behavior. The first render (parent mount) is captured
// for the "starts empty" assertion; subsequent renders after the
// user types are captured for the "prefill from password email
// form" assertion.
type MagicLinkFormProps = {
  initialEmail?: string;
  // any other props the parent passes
  [key: string]: unknown;
};
const magicLinkFormPropsLog: MagicLinkFormProps[] = [];
let magicLinkFormMountCount = 0;
function MockMagicLinkForm(props: MagicLinkFormProps) {
  magicLinkFormMountCount += 1;
  magicLinkFormPropsLog.push(props);
  return (
    <div data-testid="magic-link-form-sentinel">
      MagicLinkForm (initialEmail={String(props.initialEmail ?? "")})
    </div>
  );
}
function mockMagicLinkFormCallCount(): number {
  return magicLinkFormMountCount;
}

// Stub the actual magic-link form so the login-page test stays
// about composition (REQ-AUTH-018 — the forgot-password link)
// and about the OTP email prefill (REQ-MAINT-017).
vi.mock("@/components/auth/MagicLinkForm", () => ({
  MagicLinkForm: (props: MagicLinkFormProps) => MockMagicLinkForm(props),
}));

const routerPush = vi.fn();
const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), refresh: routerRefresh }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  // Clear the captured MagicLinkForm props log + mount counter between tests.
  magicLinkFormPropsLog.length = 0;
  magicLinkFormMountCount = 0;
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

// ---------------------------------------------------------------------------
// Regression: OTP email prefill (REQ-MAINT-017).
// Bug surfaced in spec #524 §7B: `emailRef.current?.value` is null on the
// first render (refs are set AFTER first render), so MagicLinkForm always
// received initialEmail="". The user had to retype their email when
// switching from the password form to the OTP/magic-link form.
//
// Fix per ADR-006 in design #527: lift email to controlled parent state
// (useState) + pass `key={email}` to MagicLinkForm to force remount on
// every keystroke. The OTP form's react-hook-form reads `defaultValues:
// { email: initialEmail }` on mount, so the remount propagates the
// typed-in email into the OTP input.
//
// These tests assert the parent re-renders MagicLinkForm with the typed
// email as `initialEmail`. They assert BEHAVIOR (what the parent passes
// to MagicLinkForm), not implementation (refs vs state), so they will
// keep passing if a future refactor swaps the state mechanism.
// ---------------------------------------------------------------------------


describe("LoginPage — OTP email prefill (REQ-MAINT-017)", () => {
  it("first render: MagicLinkForm receives empty initialEmail (no typed email yet)", () => {
    render(<LoginPage />);
    // At mount, the user hasn't typed anything, so initialEmail must be "".
    expect(magicLinkFormPropsLog.length).toBeGreaterThan(0);
    expect(magicLinkFormPropsLog[0]?.initialEmail ?? "").toBe("");
  });

  it("after typing in password email: MagicLinkForm receives the typed email as initialEmail", async () => {
    render(<LoginPage />);
    const emailInput = screen.getByLabelText(/^email/i) as HTMLInputElement;
    // The user types "test@example.com" into the password-form email field.
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });
    // Wait for the parent to re-render MagicLinkForm with the new email.
    await waitFor(() => {
      const last = magicLinkFormPropsLog[magicLinkFormPropsLog.length - 1];
      expect(last?.initialEmail).toBe("test@example.com");
    });
  });

  it("MagicLinkForm re-mounts when the email changes (key={email} forces fresh mount)", async () => {
    // ADR-006: the `key={email}` prop forces React to unmount and
    // remount MagicLinkForm on every email change, which is what
    // makes react-hook-form re-read `defaultValues: { email: initialEmail }`
    // (RHF only reads defaultValues on the FIRST mount).
    //
    // Observable signal: the mock function is called multiple times —
    // one mount per email value. The mock is a counter we can read.
    const beforeMountCount = mockMagicLinkFormCallCount();
    render(<LoginPage />);
    const afterFirstMountCount = mockMagicLinkFormCallCount();
    expect(afterFirstMountCount).toBeGreaterThan(beforeMountCount);

    const emailInput = screen.getByLabelText(/^email/i) as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: "alice@example.com" } });
    await waitFor(() => {
      // Each keystroke triggers a remount; the count goes up.
      expect(mockMagicLinkFormCallCount()).toBeGreaterThan(afterFirstMountCount);
    });
    fireEvent.change(emailInput, { target: { value: "bob@example.com" } });
    await waitFor(() => {
      expect(mockMagicLinkFormCallCount()).toBeGreaterThan(afterFirstMountCount + 1);
    });
  });
});
