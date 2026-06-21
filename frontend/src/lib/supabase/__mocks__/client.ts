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
 * Usage (mock the browser `@/lib/supabase/client` module):
 * ```ts
 * import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
 *
 * vi.mock("@/lib/supabase/client", () => ({
 *   createClient: () => mockSupabaseAuth,
 * }));
 *
 * beforeEach(() => {
 *   vi.mocked(mockSupabaseAuth.auth.signInWithOtp).mockResolvedValueOnce({
 *     data: null,
 *     error: new Error("boom"),
 *   });
 * });
 * ```
 *
 * `mockSupabaseAuth` is a SINGLETON — every `createClient()` call inside
 * the component-under-test returns the same mock object, so test code
 * that references `mockSupabaseAuth.auth.signInWithOtp` sees the same
 * `vi.fn()` the component calls. `vi.hoisted()` guarantees the singleton
 * is created BEFORE `vi.mock()` runs, so the factory can close over it.
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

const hoisted = vi.hoisted(() => {
  // vi.hoisted runs before vi.mock factories, so we can stash the
  // singleton here and reach it from the test factory below.
  const singleton = {} as MockSupabaseAuthClient;
  return { singleton };
});

const successUserResult = () => ({
  data: {
    user: {
      id: "user-1",
      email: "user@example.com",
      email_confirmed_at: null as string | null,
    },
  },
  error: null,
});

const successSessionResult = () => ({
  data: { session: null },
  error: null,
});

hoisted.singleton = {
  auth: {
    resetPasswordForEmail: vi.fn(async () => successUserResult()),
    updateUser: vi.fn(async () => successUserResult()),
    resend: vi.fn(async () => successUserResult()),
    signInWithOtp: vi.fn(async () => successUserResult()),
    signOut: vi.fn(async () => ({ error: null })),
    getUser: vi.fn(async () => successUserResult()),
    getSession: vi.fn(async () => successSessionResult()),
    exchangeCodeForSession: vi.fn(async () => successUserResult()),
    onAuthStateChange: vi.fn(() => ({
      data: {
        subscription: { unsubscribe: () => {} },
      },
    })),
  },
  rpc: vi.fn(async () => ({ data: null, error: null })),
};

/**
 * The single shared Supabase mock instance. Every `createClient()` call
 * inside the component-under-test returns this object so test code that
 * references `mockSupabaseAuth.auth.signInWithOtp` sees the same
 * `vi.fn()` the component calls.
 */
export const mockSupabaseAuth: MockSupabaseAuthClient = hoisted.singleton;

/**
 * Factory function — returns the singleton `mockSupabaseAuth`. Kept as
 * a function for backward compatibility with the old call site shape;
 * new tests should prefer importing `mockSupabaseAuth` directly.
 */
export function createMockSupabaseAuth(): MockSupabaseAuthClient {
  return mockSupabaseAuth;
}
