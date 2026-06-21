import { vi, type Mock } from "vitest";

/**
 * Supabase auth-method mock factory for vitest unit tests.
 *
 * Every method is a `vi.fn()` returning a sensible default success shape
 * so tests can call the component code path without first wiring custom
 * `mockReturnValue` calls. Individual tests override with
 * `mockResolvedValueOnce` / `mockReturnValue` to exercise failure modes
 * (REQ-AUTH-027).
 *
 * Usage:
 * ```ts
 * import { createMockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
 *
 * vi.mock("@/lib/supabase/client", () => createMockSupabaseAuth());
 *
 * beforeEach(() => {
 *   vi.mocked(createClient().auth.signInWithOtp).mockResolvedValueOnce({ data: null, error: new Error("boom") });
 * });
 * ```
 *
 * Shape conventions follow `@supabase/supabase-js`:
 *   - auth methods return `{ data, error }` (data is null on failure).
 *   - `signOut` returns `{ error }` only.
 *   - `onAuthStateChange` returns `{ data: { subscription } }`.
 *   - top-level `rpc(fn)` returns `{ data, error }`.
 */

// We type the spies as `Mock` (the default Procedure generic) because
// vitest 4 removed multi-arg generics — `Mock<[Args], Return>` is no
// longer expressible. Each method's runtime contract is documented
// inline; consumers should rely on Supabase's published types when
// calling the mock from component code.
export type AnyMock = Mock;

export interface MockSupabaseAuthClient {
  auth: {
    resetPasswordForEmail: AnyMock;
    updateUser: AnyMock;
    resend: AnyMock;
    signInWithOtp: AnyMock;
    signOut: AnyMock;
    getUser: AnyMock;
    getSession: AnyMock;
    exchangeCodeForSession: AnyMock;
    onAuthStateChange: AnyMock;
  };
  rpc: AnyMock;
}

const DEFAULT_USER = {
  id: "user-1",
  email: "user@example.com",
  email_confirmed_at: null as string | null,
};

function successUserResult() {
  return {
    data: { user: { ...DEFAULT_USER } },
    error: null,
  };
}

function successSessionResult() {
  return {
    data: { session: null },
    error: null,
  };
}

export function createMockSupabaseAuth(): MockSupabaseAuthClient {
  return {
    auth: {
      resetPasswordForEmail: vi.fn(async (_email: string, _options?: { redirectTo?: string }) =>
        successUserResult(),
      ),
      updateUser: vi.fn(async (_attrs: { password?: string; email?: string }) =>
        successUserResult(),
      ),
      resend: vi.fn(async (_opts: { type: "signup" | "email_change" | "magiclink"; email: string }) =>
        successUserResult(),
      ),
      signInWithOtp: vi.fn(async (_opts: { email: string }) => successUserResult()),
      signOut: vi.fn(async () => ({ error: null })),
      getUser: vi.fn(async () => successUserResult()),
      getSession: vi.fn(async () => successSessionResult()),
      exchangeCodeForSession: vi.fn(async (_code: string) => successUserResult()),
      onAuthStateChange: vi.fn((_cb: (event: string, session: unknown) => void) => ({
        data: {
          subscription: {
            unsubscribe: () => {},
          },
        },
      })),
    },
    rpc: vi.fn(async (_fn: string, _args?: Record<string, unknown>) => ({
      data: null,
      error: null,
    })),
  };
}
