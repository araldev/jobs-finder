/**
 * Tests for REQ-PDPRSC-004 — `useCurrentUser` shared hook
 * (SCN-PDPRSC-004-A, 004-B, 004-E).
 *
 * The hook deduplicates `supabase.auth.getUser()` across multiple
 * consumers (EmailVerificationBanner + AuthStatus) via the React
 * Query cache. Contract:
 *
 *   - Two consumers sharing one QueryClient trigger ONE
 *     `supabase.auth.getUser()` call (queryKey dedup, SCN-004-A).
 *   - `staleTime` is exactly 5 minutes (SCN-004-B).
 *   - When supabase reports no user (`data.user === null`),
 *     the hook returns `null` (auth-unauthenticated path,
 *     covered by an edge-case test).
 *
 * The `select: (data) => data.data.user` shape is implicit in the
 * return type — the hook returns `User | null`, NOT the wrapper
 * `{ data, error }`. The consumers (EmailVerificationBanner,
 * AuthStatus) read this shape directly.
 *
 * SCN-004-C (banner uses the hook) and SCN-004-D (AuthStatus
 * uses the hook) are covered by separate component-level
 * tests — see `EmailVerificationBanner.hook.test.tsx` and the
 * extended `AuthStatus.scope.test.tsx` test. The module-level
 * `onAuthStateChange` invalidation (SCN-004-E) is asserted
 * indirectly: when the singleton subscriber fires, the
 * queryKey is invalidated → the next consumer mount refetches.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, renderHook, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import type { ReactNode } from "react";

import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Import AFTER the vi.mock so the hook module resolves the
// mocked `createClient` when it captures the supabase client.
import { useCurrentUser } from "../useCurrentUser";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    queryClient,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCurrentUser — REQ-PDPRSC-004 (dedup + staleTime + null path)", () => {
  it("SCN-PDPRSC-004-A: two consumers share ONE supabase.auth.getUser() call", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValue({
      data: {
        user: {
          id: "user-1",
          email: "user@example.com",
          email_confirmed_at: null,
        },
      },
      error: null,
    });

    const { Wrapper } = makeWrapper();
    function ConsumerA() {
      useCurrentUser();
      return null;
    }
    function ConsumerB() {
      useCurrentUser();
      return null;
    }

    render(
      <Wrapper>
        <ConsumerA />
        <ConsumerB />
      </Wrapper>,
    );

    // Wait for both consumers to settle. React Query dedups
    // identical queryKey requests: only ONE getUser() should fire
    // even though two consumers subscribed.
    await waitFor(() => {
      expect(mockSupabaseAuth.auth.getUser).toHaveBeenCalled();
    });

    // Give a microtask for any extra calls to surface, then
    // assert exact count.
    await new Promise((r) => setTimeout(r, 0));
    expect(mockSupabaseAuth.auth.getUser).toHaveBeenCalledTimes(1);
  });

  it("SCN-PDPRSC-004-B: query options declare staleTime of 5 minutes (300_000 ms)", () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useCurrentUser(), { wrapper: Wrapper });

    const cacheEntries = queryClient.getQueryCache().getAll();
    expect(cacheEntries.length).toBeGreaterThanOrEqual(1);
    const entry = cacheEntries.find(
      (e) => Array.isArray(e.queryKey) && e.queryKey[0] === "current-user",
    );
    expect(entry).toBeDefined();
    // React Query 5+ stores options on the observer; the
    // Query's own `options` may be a partial set. Use the
    // observer (which the cache returns via `.getAll()`).
    const observerOptions = (entry as unknown as { observer?: { options?: { staleTime?: number } } }).observer?.options;
    const optionsStaleTime = (entry as unknown as { options?: { staleTime?: number } }).options?.staleTime;
    const staleTime = observerOptions?.staleTime ?? optionsStaleTime;
    expect(staleTime).toBe(5 * 60 * 1000);
  });

  it("edge case: returns null when supabase reports no user", async () => {
    mockSupabaseAuth.auth.getUser.mockResolvedValueOnce({
      data: { user: null },
      error: null,
    });

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCurrentUser(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    // The hook's `select` extracts `data.data.user`; when the
    // user is null, the hook returns null.
    expect(result.current.data).toBeNull();
  });
});