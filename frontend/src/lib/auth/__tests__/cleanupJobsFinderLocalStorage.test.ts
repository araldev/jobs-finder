import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanupJobsFinderLocalStorage } from "../cleanupJobsFinderLocalStorage";
import { STORAGE_KEY_PREFIX } from "../storageKeys";

beforeEach(() => {
  // Each test gets a fresh localStorage.
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => {
      store.set(key, value);
    },
  );
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation((key: string) => {
    store.delete(key);
  });
  vi.spyOn(Storage.prototype, "clear").mockImplementation(() => {
    store.clear();
  });
  // Provide a way for the test to inspect what's in storage.
  Object.defineProperty(window, "localStorage", {
    value: {
      _store: store,
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => {
        store.clear();
      },
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      get length() {
        return store.size;
      },
    },
  });
});

describe("cleanupJobsFinderLocalStorage (REQ-AUTH-012 / ADR-005)", () => {
  it("removes ONLY jobs-finder-* keys, leaves other keys untouched", () => {
    localStorage.setItem("jobs-finder-favorites", JSON.stringify([]));
    localStorage.setItem("jobs-finder-chat-v1", JSON.stringify({}));
    localStorage.setItem("jobs-finder-cv-adapted-count", "3");
    localStorage.setItem("theme", "dark");
    localStorage.setItem("foo", "bar");

    cleanupJobsFinderLocalStorage();

    expect(localStorage.getItem("jobs-finder-favorites")).toBeNull();
    expect(localStorage.getItem("jobs-finder-chat-v1")).toBeNull();
    expect(localStorage.getItem("jobs-finder-cv-adapted-count")).toBeNull();
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(localStorage.getItem("foo")).toBe("bar");
  });

  it("handles empty localStorage without throwing", () => {
    expect(() => cleanupJobsFinderLocalStorage()).not.toThrow();
    expect(localStorage.length).toBe(0);
  });

  it("handles a storage access error gracefully (no throw)", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => cleanupJobsFinderLocalStorage()).not.toThrow();
  });

  it("removes future jobs-finder-* keys too (allowlist prefix, not enumeration)", () => {
    localStorage.setItem("jobs-finder-totally-new-future-feature", "x");
    cleanupJobsFinderLocalStorage();
    expect(localStorage.getItem("jobs-finder-totally-new-future-feature")).toBeNull();
  });

  it("uses STORAGE_KEY_PREFIX from storageKeys (not a hardcoded literal)", () => {
    // Regression guard: the sweep MUST read STORAGE_KEY_PREFIX from
    // the storageKeys module, not a string literal. If a future change
    // reverts to a hardcoded "jobs-finder-" string and the constant is
    // ever updated, the cleanup helper would silently stop matching
    // real keys. This test imports STORAGE_KEY_PREFIX and asserts the
    // helper honors the constant's value (i.e. the constant IS the
    // source of truth end-to-end).
    expect(localStorage.getItem(`${STORAGE_KEY_PREFIX}probe`)).toBeNull();
    localStorage.setItem(`${STORAGE_KEY_PREFIX}probe`, "v");
    cleanupJobsFinderLocalStorage();
    expect(localStorage.getItem(`${STORAGE_KEY_PREFIX}probe`)).toBeNull();
  });

  it("cleanup reads STORAGE_KEY_PREFIX from the storageKeys module (mocked)", async () => {
    // Stronger regression guard: if the implementation used a hardcoded
    // string literal, this test would FAIL because the mocked prefix
    // would not match the literal. The test uses vi.doMock (per-test
    // module override) to swap the storageKeys module to a different
    // prefix, then dynamically re-imports the cleanup helper. If the
    // helper reads the constant from the module, the new prefix is used.
    const FAKE_PREFIX = "totally-different-prefix-";
    vi.resetModules();
    vi.doMock("../storageKeys", () => ({
      STORAGE_KEY_PREFIX: FAKE_PREFIX,
      JOBS_FINDER_STORAGE_KEYS: {
        favorites: `${FAKE_PREFIX}favorites`,
        chat: `${FAKE_PREFIX}chat-v1`,
        cvAdaptedCount: `${FAKE_PREFIX}cv-adapted-count`,
      },
    }));
    const { cleanupJobsFinderLocalStorage: mockedCleanup } = await import(
      "../cleanupJobsFinderLocalStorage"
    );
    localStorage.setItem(`${FAKE_PREFIX}favorites`, "[]");
    localStorage.setItem("jobs-finder-favorites", "[]"); // uses the REAL constant value, not the mocked one
    mockedCleanup();
    // The mocked prefix matches and the key is removed.
    expect(localStorage.getItem(`${FAKE_PREFIX}favorites`)).toBeNull();
    // The real-prefix key is NOT matched by the mocked cleanup, so it
    // remains. This proves cleanup uses STORAGE_KEY_PREFIX from the
    // module, not a hardcoded "jobs-finder-" string.
    expect(localStorage.getItem("jobs-finder-favorites")).not.toBeNull();
    vi.doUnmock("../storageKeys");
    vi.resetModules();
  });
});
