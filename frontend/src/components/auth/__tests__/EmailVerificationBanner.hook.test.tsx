/**
 * Tests for SCN-PDPRSC-004-C — `EmailVerificationBanner` consumes
 * the `useCurrentUser` hook instead of calling
 * `supabase.auth.getUser()` directly.
 *
 * This is the regression guard that proves the banner's auth
 * state lives in the React Query cache (shared with AuthStatus,
 * LayoutHeader, etc.) — not in a local useEffect + useState
 * pair. With this in place:
 *
 *   - The banner does NOT call `supabase.auth.getUser()` on mount;
 *     the cache is read instead.
 *   - Two banner mounts (e.g. on revalidation) share ONE
 *     `/auth/v1/user` fetch via queryKey dedup.
 *   - The `onAuthStateChange` subscriber (registered at hook
 *     module load) invalidates the query → banner re-renders
 *     automatically on sign-in/out, no local subscription needed.
 *
 * We mock `useCurrentUser` directly because the hook itself is
 * tested in `useCurrentUser.test.tsx`. The contract this file
 * verifies is "the banner calls useCurrentUser", not "the hook
 * works correctly" (that's the hook's own test's job).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

vi.mock("@/hooks/useCurrentUser", () => ({
  useCurrentUser: vi.fn(),
}));

import { EmailVerificationBanner } from "../EmailVerificationBanner";
import { useCurrentUser } from "@/hooks/useCurrentUser";

const mockUseCurrentUser = vi.mocked(useCurrentUser);

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  // Default: hook returns a known user with unconfirmed email.
  // We cast through `unknown` because the test only needs the
  // surface the banner reads (`data`, `isLoading`); the full
  // UseQueryResult type would require stubbing every field.
  mockUseCurrentUser.mockReturnValue({
    data: {
      id: "user-1",
      email: "user@example.com",
      email_confirmed_at: null,
    },
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useCurrentUser>);
});

describe("EmailVerificationBanner — SCN-PDPRSC-004-C (uses useCurrentUser)", () => {
  it("renders the banner when useCurrentUser returns an unconfirmed user", () => {
    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));

    expect(
      screen.getByText(esMessages.Auth.emailVerification.title),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("does NOT call supabase.auth.getUser() — auth state comes from the hook", () => {
    render(renderWithIntl(<EmailVerificationBanner />, { locale: "es" }));

    // The banner previously called supabase.auth.getUser() in a
    // useEffect. The hook version reads from the React Query
    // cache; the underlying supabase call is the hook's job,
    // not the banner's.
    expect(mockSupabaseAuth.auth.getUser).not.toHaveBeenCalled();
  });
});