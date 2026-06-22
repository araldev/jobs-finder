import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useJobs } from "../useJobs";

/**
 * Tests for REQ-CACHEUX-003 (unified queryKey prefix for `useJobs`).
 *
 * The shared prefix `["jobs", "list", sharedArgs]` lets the Next.js
 * Data Cache (L2, set up by REQ-CACHEUX-001) dedupe repeat calls to
 * `/api/jobs` across the two hooks. The mode discriminator
 * (`"single"` vs `"infinite"`) and size tail (`limit` vs `pageSize`)
 * keep the React Query entries distinct so they don't collide at
 * L3 (React Query).
 *
 * Implementation note: TanStack Query v5 does NOT expose `queryKey`
 * on the result object. We read the actual `queryKey` from the
 * QueryClient's query cache — the source of truth for what
 * queryKey React Query stored for this hook's call.
 */

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: Infinity },
    },
  });
  return {
    queryClient,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  };
}

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    return new Response(
      JSON.stringify({ items: [], total: 0, limit: 0, offset: 0 }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

/**
 * Read the queryKey React Query stored for the most-recent mount of
 * `useJobs`. Each `renderHook` mounts a fresh `QueryClient`, so we
 * only ever read from the client we control.
 */
function readQueryKey(queryClient: QueryClient): readonly unknown[] {
  const queries = queryClient.getQueryCache().getAll();
  // The most recently observed queryKey is the one we just registered.
  return queries[queries.length - 1]?.queryKey ?? [];
}

describe("useJobs — queryKey shape (REQ-CACHEUX-003)", () => {
  it("queryKey starts with ['jobs', 'list'] and ends with 'single' + the limit", () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useJobs({ limit: 5 }), { wrapper: Wrapper });

    const key = readQueryKey(queryClient);
    expect(Array.isArray(key)).toBe(true);
    expect(key[0]).toBe("jobs");
    expect(key[1]).toBe("list");
    expect(key[key.length - 2]).toBe("single");
    expect(key[key.length - 1]).toBe(5);
  });

  it("queryKey uses null limit when limit is omitted", () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useJobs({}), { wrapper: Wrapper });

    const key = readQueryKey(queryClient);
    expect(key[0]).toBe("jobs");
    expect(key[1]).toBe("list");
    expect(key[key.length - 2]).toBe("single");
    // When no limit is passed, the tail is null.
    expect(key[key.length - 1]).toBeNull();
  });

  it("identical sharedArgs produce an identical middle segment across mounts", () => {
    const { queryClient: qcA, Wrapper: wA } = makeWrapper();
    const { queryClient: qcB, Wrapper: wB } = makeWrapper();

    const args1 = { q: "react", location: "Madrid", sources: "linkedin" };
    const args2 = { q: "react", location: "Madrid", sources: "linkedin" };

    renderHook(() => useJobs(args1), { wrapper: wA });
    renderHook(() => useJobs(args2), { wrapper: wB });

    const keyA = readQueryKey(qcA);
    const keyB = readQueryKey(qcB);
    // Index 2 is the sharedArgs serialization.
    expect(keyA[2]).toBe(keyB[2]);
  });
});
