import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFavorites } from "../useFavorites";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";
import type { Job } from "@/types/job";

// Mock the storageKeys module to use a fake prefix so the regression test
// (and the existing tests) prove the production code reads the constant
// instead of a hardcoded literal. Both test setup and production code
// resolve the constant to FAKE_PREFIX.favorites, keeping them in sync.
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
      cvAdaptedCount: `${FAKE_PREFIX}cv-adapted-count`,
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

beforeEach(() => {
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
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useFavorites", () => {
  it("starts with empty favorites", () => {
    const { result } = renderHook(() => useFavorites());
    expect(result.current.favorites).toEqual([]);
    expect(result.current.favoriteCount).toBe(0);
  });

  it("toggleFavorite adds a job", () => {
    const { result } = renderHook(() => useFavorites());

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    expect(result.current.favorites).toHaveLength(1);
    expect(result.current.favorites[0]?.id).toBe("job-1");
    expect(result.current.isFavorite("job-1")).toBe(true);
    expect(result.current.favoriteCount).toBe(1);
  });

  it("toggleFavorite removes an already-favorited job", () => {
    const { result } = renderHook(() => useFavorites());

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    expect(result.current.favoriteCount).toBe(1);

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    expect(result.current.favorites).toHaveLength(0);
    expect(result.current.isFavorite("job-1")).toBe(false);
    expect(result.current.favoriteCount).toBe(0);
  });

  it("handles duplicate toggles showing correct state", () => {
    const { result } = renderHook(() => useFavorites());

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    act(() => {
      result.current.toggleFavorite(mockJob2);
    });
    expect(result.current.favorites).toHaveLength(2);

    act(() => {
      result.current.toggleFavorite(mockJob);
    });
    expect(result.current.favorites).toHaveLength(1);
    expect(result.current.favorites[0]?.id).toBe("job-2");
  });

  it("isFavorite returns correct boolean", () => {
    const { result } = renderHook(() => useFavorites());

    expect(result.current.isFavorite("job-1")).toBe(false);

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    expect(result.current.isFavorite("job-1")).toBe(true);
    expect(result.current.isFavorite("job-2")).toBe(false);
  });

  it("removeFavorite removes a specific job", () => {
    const { result } = renderHook(() => useFavorites());

    act(() => {
      result.current.toggleFavorite(mockJob);
      result.current.toggleFavorite(mockJob2);
    });
    expect(result.current.favorites).toHaveLength(2);

    act(() => {
      result.current.removeFavorite("job-1");
    });

    expect(result.current.favorites).toHaveLength(1);
    expect(result.current.favorites[0]?.id).toBe("job-2");
    expect(result.current.isFavorite("job-1")).toBe(false);
  });

  it("persists to localStorage on toggle", () => {
    const { result } = renderHook(() => useFavorites());

    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]?.id).toBe("job-1");
  });

  it("handles corrupted localStorage gracefully", () => {
    localStorage.setItem(STORAGE_KEY, "invalid-json{{{");

    const { result } = renderHook(() => useFavorites());
    expect(result.current.favorites).toEqual([]);
    expect(result.current.favoriteCount).toBe(0);
  });

  it("handles non-array localStorage gracefully", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ not: "an array" }));

    const { result } = renderHook(() => useFavorites());
    expect(result.current.favorites).toEqual([]);
  });
});

describe("useFavorites storage key (regression)", () => {
  it("writes to JOBS_FINDER_STORAGE_KEYS.favorites (not a hardcoded literal)", () => {
    const { result } = renderHook(() => useFavorites());
    act(() => {
      result.current.toggleFavorite(mockJob);
    });

    // Production MUST write to the FAKE_PREFIX.favorites key (the mocked
    // constant). If production keeps a hardcoded "jobs-finder-favorites"
    // literal, this is null and the real key has the value instead.
    expect(localStorage.getItem(`${FAKE_PREFIX}favorites`)).not.toBeNull();
    expect(localStorage.getItem("jobs-finder-favorites")).toBeNull();
  });
});
