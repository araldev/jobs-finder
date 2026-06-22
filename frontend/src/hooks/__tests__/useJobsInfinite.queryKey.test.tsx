import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useJobs } from "../useJobs";
import { useJobsInfinite } from "../useJobsInfinite";

/**
 * Tests for REQ-CACHEUX-003 (unified queryKey prefix for `useJobsInfinite`).
 *
 * See `useJobs.queryKey.test.tsx` for the rationale. The mode
 * discriminator for `useJobsInfinite` is `"infinite"` and the size
 * tail is `pageSize`. The two hooks share the
 * `["jobs", "list", sharedArgs]` prefix so the L2 Next.js Data
 * Cache dedupes the underlying `/api/jobs` URL.
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

function readQueryKey(queryClient: QueryClient): readonly unknown[] {
  const queries = queryClient.getQueryCache().getAll();
  return queries[queries.length - 1]?.queryKey ?? [];
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

describe("useJobsInfinite — queryKey shape (REQ-CACHEUX-003)", () => {
  it("queryKey starts with ['jobs', 'list'] and ends with 'infinite' + the pageSize", () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useJobsInfinite({ pageSize: 20 }), { wrapper: Wrapper });

    const key = readQueryKey(queryClient);
    expect(Array.isArray(key)).toBe(true);
    expect(key[0]).toBe("jobs");
    expect(key[1]).toBe("list");
    expect(key[key.length - 2]).toBe("infinite");
    expect(key[key.length - 1]).toBe(20);
  });

  it("queryKey uses default pageSize of 20 when pageSize is omitted", () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useJobsInfinite({}), { wrapper: Wrapper });

    const key = readQueryKey(queryClient);
    expect(key[1]).toBe("list");
    expect(key[key.length - 2]).toBe("infinite");
    expect(key[key.length - 1]).toBe(20);
  });

  it("identical sharedArgs produce an identical middle segment across mounts", () => {
    const { queryClient: qcA, Wrapper: wA } = makeWrapper();
    const { queryClient: qcB, Wrapper: wB } = makeWrapper();

    renderHook(
      () =>
        useJobsInfinite({
          q: "react",
          location: "Madrid",
          sources: "linkedin",
          pageSize: 20,
        }),
      { wrapper: wA },
    );
    renderHook(
      () =>
        useJobsInfinite({
          q: "react",
          location: "Madrid",
          sources: "linkedin",
          pageSize: 20,
        }),
      { wrapper: wB },
    );

    const keyA = readQueryKey(qcA);
    const keyB = readQueryKey(qcB);
    expect(keyA[2]).toBe(keyB[2]);
  });

  it("same sharedArgs between useJobs and useJobsInfinite share the prefix + middle segment", () => {
    const { queryClient: qcA, Wrapper: wA } = makeWrapper();
    const { queryClient: qcB, Wrapper: wB } = makeWrapper();

    renderHook(
      () =>
        useJobs({
          q: "react",
          location: "Madrid",
          sources: "linkedin",
          limit: 5,
        }),
      { wrapper: wA },
    );
    renderHook(
      () =>
        useJobsInfinite({
          q: "react",
          location: "Madrid",
          sources: "linkedin",
          pageSize: 20,
        }),
      { wrapper: wB },
    );

    const useJobsKey = readQueryKey(qcA);
    const useInfiniteKey = readQueryKey(qcB);

    // The whole point of the unified prefix: the first 3 entries
    // (["jobs", "list", sharedArgs]) are IDENTICAL even though
    // the hooks return different data shapes.
    expect(useJobsKey[0]).toBe(useInfiniteKey[0]);
    expect(useJobsKey[1]).toBe(useInfiniteKey[1]);
    expect(useJobsKey[2]).toBe(useInfiniteKey[2]);
    // But the mode tail differs.
    expect(useJobsKey[useJobsKey.length - 2]).toBe("single");
    expect(
      useInfiniteKey[useInfiniteKey.length - 2],
    ).toBe("infinite");
  });
});
