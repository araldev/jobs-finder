import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useJobsInfinite } from "../useJobsInfinite";

/**
 * Tests for REQ-CACHEUX-006 (`placeholderData: keepPreviousData` on
 * `useJobsInfinite`).
 *
 * Bug surfaced in the perf-frontend-cache-ux audit: when the user
 * changes the filter (e.g. `q: "react"` → `q: "python"`), React
 * Query enters a fresh fetch cycle for the new queryKey. Without
 * `placeholderData`, `data` becomes `undefined` mid-flight and the
 * grid flashes back to the empty/loading skeleton — losing the
 * scroll position and the perceived smoothness.
 *
 * `keepPreviousData` (TanStack v5 re-export from query-core) keeps
 * the previous queryKey's `data` populated during the in-flight
 * period of the new queryKey. The user sees the OLD items while the
 * NEW items load.
 *
 * These tests use `renderHook` + a fresh `QueryClient` so the test
 * environment mirrors how the hook is consumed in production
 * (inside `<QueryClientProvider>`), without the global
 * `TestProviders` wrapper (which would force the 5min `staleTime`
 * default and complicate the in-flight timing).
 */

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // No staleTime default — we want each query to be a "fresh"
        // fetch so we can drive queryKey changes and observe the
        // in-flight placeholder behavior.
        staleTime: 0,
        gcTime: Infinity,
      },
    },
  });
  return {
    queryClient,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  };
}

function fakeHistoryResponse(seed: number) {
  return {
    items: Array.from({ length: 3 }).map((_, i) => ({
      id: `${seed}-${i}`,
      source: "linkedin",
      title: `Job ${seed}-${i}`,
      company: `Co ${seed}-${i}`,
      location: "Madrid",
      url: `https://example.com/${seed}/${i}`,
      posted_at: "2026-06-01T00:00:00Z",
      description: null,
    })),
    total: 10,
    limit: 20,
    offset: 0,
  };
}

describe("useJobsInfinite — placeholderData: keepPreviousData (REQ-CACHEUX-006)", () => {
  beforeEach(() => {
    // The hook calls fetch('/api/jobs?...'). Mock globally so we
    // can stage responses per queryKey.
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      // Default: return a stable response; individual tests
      // override via mockImplementationOnce.
      return new Response(JSON.stringify(fakeHistoryResponse(0)), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps the previous items visible while a new query is in-flight", async () => {
    const { queryClient, Wrapper } = makeWrapper();

    // Stage two different responses — one for `q:"react"`, one for
    // `q:"python"`. The python response is delayed so the
    // placeholder behavior can be observed.
    const reactResponse = fakeHistoryResponse(1);
    const pythonResponse = fakeHistoryResponse(2);

    let resolvePython!: (r: Response) => void;
    const pythonPromise = new Promise<Response>((resolve) => {
      resolvePython = resolve;
    });

    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input) => {
        const url = String(input);
        if (url.includes("q=react")) {
          return new Response(JSON.stringify(reactResponse), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        if (url.includes("q=python")) {
          return pythonPromise;
        }
        return new Response(JSON.stringify(fakeHistoryResponse(0)), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      },
    );

    // First mount with q="react" — wait for the initial fetch.
    const { result, rerender } = renderHook(
      ({ q }: { q: string }) => useJobsInfinite({ q, pageSize: 20 }),
      { wrapper: Wrapper, initialProps: { q: "react" } },
    );

    await waitFor(() => {
      expect(result.current.data?.pages?.[0]?.items?.[0]?.id).toBe("1-0");
    });

    // Now flip to q="python" — this triggers a NEW fetch with a
    // DIFFERENT queryKey. The previous fetch for `react` is in the
    // cache; the new fetch for `python` is in-flight (we haven't
    // resolved it yet).
    rerender({ q: "python" });

    // With `keepPreviousData`, `data` should still reflect the
    // previous ("react") items while the python fetch is pending.
    // Wait one microtask for React Query to settle the queryKey
    // change.
    await waitFor(() => {
      expect(result.current.isFetching).toBe(true);
    });

    // The previous data MUST still be present in `data.pages[0].items`.
    // Without `keepPreviousData`, `data` would be `undefined` here
    // and the test would observe no items.
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.pages?.[0]?.items?.[0]?.id).toBe("1-0");

    // Now resolve the python fetch — data should swap to python.
    resolvePython(
      new Response(JSON.stringify(pythonResponse), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await waitFor(() => {
      expect(result.current.data?.pages?.[0]?.items?.[0]?.id).toBe("2-0");
    });

    // Cleanup the spy — the test fetcher returned the python
    // response so the spy is no longer needed.
    void fetchMock;
    void queryClient;
  });
});
