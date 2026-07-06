import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import esMessages from "@/messages/es.json";
import type { ReactNode } from "react";
import { useFavorites, FAVORITES_QUERY_KEY } from "../useFavorites";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";
import type { Job } from "@/types/job";

// Mock the storageKeys module to use a fake prefix so the regression
// test (and the existing tests) prove the production code reads the
// constant instead of a hardcoded literal. Both test setup and
// production code resolve the constant to FAKE_PREFIX.favorites,
// keeping them in sync.
const { FAKE_PREFIX } = vi.hoisted(() => ({
  FAKE_PREFIX: "auth-flows-test-",
}));
vi.mock("@/lib/auth/storageKeys", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth/storageKeys")>(
    "@/lib/auth/storageKeys",
  );
  return {
    ...actual,
    STORAGE_KEY_PREFIX: FAKE_PREFIX,
    JOBS_FINDER_STORAGE_KEYS: {
      favorites: `${FAKE_PREFIX}favorites`,
      chat: `${FAKE_PREFIX}chat-v1`,
    },
  };
});

const mockJob: Job = {
  id: "job-1",
  source: "linkedin",
  title: "Software Engineer",
  company: "Acme Inc",
  location: "Remote",
  url: "https://example.com/job-1",
  posted_at: "2026-06-10T10:00:00Z",
  description: "A great job",
};

const mockJob2: Job = {
  id: "job-2",
  source: "indeed",
  title: "Product Manager",
  company: "Beta Corp",
  location: "New York",
  url: "https://example.com/job-2",
  posted_at: "2026-06-11T10:00:00Z",
  description: "Another great job",
};

const STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.favorites;

/**
 * Fresh `QueryClient` per test — mirrors the project's existing
 * pattern (`useJobs.queryKey.test.tsx`, `useCurrentUser.test.tsx`).
 * `retry: false` so failures surface immediately. `staleTime: 0`
 * and `gcTime: Infinity` keep the cache predictable across the
 * short test runs.
 */
function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  return {
    queryClient,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <NextIntlClientProvider locale="es" messages={esMessages}>
          {children}
        </NextIntlClientProvider>
      </QueryClientProvider>
    ),
  };
}

beforeEach(() => {
  // localStorage mock — fresh Map per test, mirrors the existing
  // pattern. The hook's `readLocalFavorites` / `writeLocalFavorites`
  // helpers call into this prototype spy.
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => { store.set(key, value); },
  );
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(
    (key: string) => { store.delete(key); },
  );
  vi.spyOn(Storage.prototype, "clear").mockImplementation(() => { store.clear(); });

  // fetch mock: GET returns 401 (the queryFn falls back to
  // localStorage on 401). POST/DELETE return a never-resolving
  // Promise so the optimistic update stays visible — no rollback
  // from `onError`, no overwrite from `onSuccess` invalidation.
  // Individual tests can override per-method via `mockImplementationOnce`.
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
    if (init?.method && init.method !== "GET") {
      return new Promise<Response>(() => {});
    }
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useFavorites", () => {
  it("starts with empty favorites", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
      expect(result.current.favoriteCount).toBe(0);
    });
  });

  it("toggleFavorite adds a job", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(1);
      expect(result.current.favorites[0]?.id).toBe("job-1");
      expect(result.current.isFavorite("job-1")).toBe(true);
      expect(result.current.favoriteCount).toBe(1);
    });
  });

  it("toggleFavorite removes an already-favorited job", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    await waitFor(() => {
      expect(result.current.favoriteCount).toBe(1);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(0);
      expect(result.current.isFavorite("job-1")).toBe(false);
      expect(result.current.favoriteCount).toBe(0);
    });
  });

  it("handles duplicate toggles showing correct state", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    act(() => {
      result.current.toggleFavorite(mockJob2);
    });
    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(2);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(1);
      expect(result.current.favorites[0]?.id).toBe("job-2");
    });
  });

  it("isFavorite returns correct boolean", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.isFavorite("job-1")).toBe(false);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    await waitFor(() => {
      expect(result.current.isFavorite("job-1")).toBe(true);
      expect(result.current.isFavorite("job-2")).toBe(false);
    });
  });

  it("removeFavorite removes a specific job", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
      result.current.toggleFavorite(mockJob2);
    });
    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(2);
    });

    act(() => {
      result.current.removeFavorite(mockJob);
    });

    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(1);
      expect(result.current.favorites[0]?.id).toBe("job-2");
      expect(result.current.isFavorite("job-1")).toBe(false);
    });
  });

  it("persists to localStorage on toggle", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    await waitFor(() => {
      const raw = localStorage.getItem(STORAGE_KEY);
      expect(raw).not.toBeNull();
      const parsed = JSON.parse(raw!);
      expect(parsed).toHaveLength(1);
      expect(parsed[0]?.id).toBe("job-1");
    });
  });

  it("handles corrupted localStorage gracefully", async () => {
    localStorage.setItem(STORAGE_KEY, "invalid-json{{{");

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
      expect(result.current.favoriteCount).toBe(0);
    });
  });

  it("handles non-array localStorage gracefully", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ not: "an array" }));

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });
  });
});

describe("useFavorites — React Query integration", () => {
  it("uses queryKey ['favorites'] for the shared cache", async () => {
    const { queryClient, Wrapper } = makeWrapper();
    renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      const entries = queryClient.getQueryCache().getAll();
      const favoritesEntry = entries.find(
        (e) => JSON.stringify(e.queryKey) === JSON.stringify(FAVORITES_QUERY_KEY),
      );
      expect(favoritesEntry).toBeDefined();
      expect(favoritesEntry?.queryKey).toEqual(["favorites"]);
    });
  });

  it("mutation invalidates the ['favorites'] cache on success", async () => {
    // Override the default fetch mock for this test: GET returns
    // empty data, POST returns 201 (success), DELETE returns 204.
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ status: "created", job_id: 42 }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      if (init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify({ data: [], total: 0 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const { queryClient, Wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["favorites"],
      });
    });
  });

  it("falls back to localStorage when the API returns 401", async () => {
    // Pre-populate localStorage with a job. The default fetch mock
    // returns 401 on GET — the hook's queryFn catches that and
    // returns localStorage contents.
    localStorage.setItem(STORAGE_KEY, JSON.stringify([mockJob]));

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toHaveLength(1);
      expect(result.current.favorites[0]?.id).toBe("job-1");
      expect(result.current.isFavorite("job-1")).toBe(true);
      expect(result.current.favoriteCount).toBe(1);
    });
  });

  it("applies the optimistic update without waiting for the network round-trip", async () => {
    // The default fetch mock hangs POST/DELETE on a never-resolving
    // promise. The mutation's mutationFn never resolves, so the
    // optimistic value is never rolled back by onError and never
    // overwritten by onSuccess's invalidation refetch. This proves
    // the cache update lands BEFORE the API call completes — i.e.,
    // the user sees the heart flip instantly, regardless of network.
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    // React Query runs `onMutate` after `mutate()` is called and
    // schedules the cache update via a setTimeout(0) — `act`
    // doesn't drain that queue. From the user's perspective the
    // update is instantaneous (no spinner, no waitFor polling);
    // the test just needs to flush the same microtask.
    await act(async () => {
      result.current.toggleFavorite(mockJob);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(result.current.favorites).toHaveLength(1);
    expect(result.current.favorites[0]?.id).toBe("job-1");
    expect(result.current.isFavorite("job-1")).toBe(true);
  });
});

describe("useFavorites storage key (regression)", () => {
  it("writes to JOBS_FINDER_STORAGE_KEYS.favorites (not a hardcoded literal)", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useFavorites(), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.favorites).toEqual([]);
    });

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    await waitFor(() => {
      // Production MUST write to the FAKE_PREFIX.favorites key
      // (the mocked constant). If production keeps a hardcoded
      // "jobs-finder-favorites" literal, this is null and the
      // real key has the value instead.
      expect(localStorage.getItem(`${FAKE_PREFIX}favorites`)).not.toBeNull();
      expect(localStorage.getItem("jobs-finder-favorites")).toBeNull();
    });
  });
});