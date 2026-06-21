import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mock the storageKeys module to use a fake prefix so the regression test
// proves the production code reads the constant instead of a hardcoded
// literal. If production keeps the literal "jobs-finder-cv-adapted-count",
// the write goes to the real key (not the FAKE_PREFIX one) and the test fails.
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

import { useCVAdapted } from "../useCVAdapted";

beforeEach(() => {
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => {
      store.set(key, value);
    },
  );
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(
    (key: string) => {
      store.delete(key);
    },
  );
  vi.spyOn(Storage.prototype, "clear").mockImplementation(() => {
    store.clear();
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCVAdapted storage key (regression)", () => {
  it("writes to JOBS_FINDER_STORAGE_KEYS.cvAdaptedCount (not a hardcoded literal)", () => {
    const { result } = renderHook(() => useCVAdapted());

    act(() => {
      result.current.incrementCVAdapted();
    });

    // Production MUST write to the FAKE_PREFIX.cv-adapted-count key (the
    // mocked constant). If production keeps a hardcoded literal, this is null.
    expect(localStorage.getItem(`${FAKE_PREFIX}cv-adapted-count`)).not.toBeNull();
    expect(localStorage.getItem("jobs-finder-cv-adapted-count")).toBeNull();
  });
});
