import { vi } from "vitest";
import { type MockSupabaseAuthClient } from "./client";

/**
 * Supabase SERVER-client mock factory for vitest unit tests.
 *
 * Mirrors the shape of `frontend/src/lib/supabase/server.ts`'s
 * `createClient()` but with the auth methods exposed as `vi.fn()`
 * spies. Used by tests that drive Next.js Route Handlers (e.g. the
 * `auth/callback/route.ts` open-redirect defense test) where the
 * component-under-test calls `createServerClient` server-side and
 * we need to assert `exchangeCodeForSession` was invoked.
 */
export type MockSupabaseServerClient = MockSupabaseAuthClient;

export function createMockSupabaseServerClient(): MockSupabaseServerClient {
  return {
    auth: {
      exchangeCodeForSession: vi.fn(async (_code: string) => ({
        data: {
          user: {
            id: "user-1",
            email: "user@example.com",
            email_confirmed_at: null as string | null,
          },
        },
        error: null,
      })),
      getSession: vi.fn(async () => ({
        data: { session: null },
        error: null,
      })),
      getUser: vi.fn(async () => ({
        data: {
          user: {
            id: "user-1",
            email: "user@example.com",
            email_confirmed_at: null as string | null,
          },
        },
        error: null,
      })),
      // The server client is used by route handlers; the rest of the
      // auth surface is not exercised. Stub the remaining methods with
      // the same default shapes as the browser mock so any test that
      // accidentally touches them still gets a usable return value.
      resetPasswordForEmail: vi.fn(async () => ({ data: null, error: null })),
      updateUser: vi.fn(async () => ({ data: null, error: null })),
      resend: vi.fn(async () => ({ data: null, error: null })),
      signInWithOtp: vi.fn(async () => ({ data: null, error: null })),
      signInWithPassword: vi.fn(async () => ({ data: null, error: null })),
      signInWithOAuth: vi.fn(async () => ({ data: null, error: null })),
      signUp: vi.fn(async () => ({ data: null, error: null })),
      signOut: vi.fn(async () => ({ error: null })),
      onAuthStateChange: vi.fn(() => ({
        data: {
          subscription: { unsubscribe: () => {} },
        },
      })),
    },
    rpc: vi.fn(async () => ({ data: null, error: null })),
  };
}
