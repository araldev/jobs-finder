import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanupJobsFinderLocalStorage } from "../cleanupJobsFinderLocalStorage";

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
});
