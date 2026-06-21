import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the storageKeys module to use a fake prefix so the regression tests
// prove the production code reads the constant instead of a hardcoded
// literal. If production keeps the literal "jobs-finder-chat-v1", the
// writes/clears go to the real key (not the FAKE_PREFIX one) and the tests fail.
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

import { markJobAsOpened, clearChatStorage } from "../chat-storage";

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

describe("chat-storage storage key (regression)", () => {
  it("markJobAsOpened writes to JOBS_FINDER_STORAGE_KEYS.chat (not a hardcoded literal)", () => {
    markJobAsOpened("job-123");

    // Production MUST write to the FAKE_PREFIX.chat-v1 key (the mocked constant).
    // If production keeps a hardcoded "jobs-finder-chat-v1" literal, this is null.
    expect(localStorage.getItem(`${FAKE_PREFIX}chat-v1`)).not.toBeNull();
    expect(localStorage.getItem("jobs-finder-chat-v1")).toBeNull();
  });

  it("clearChatStorage removes JOBS_FINDER_STORAGE_KEYS.chat (not a hardcoded literal)", () => {
    // Set up BOTH the mocked key AND a legacy real key. clearChatStorage MUST
    // only clear the mocked key (the constant) and leave the real key alone.
    localStorage.setItem(
      `${FAKE_PREFIX}chat-v1`,
      JSON.stringify({ messages: [], openedJobIds: [] }),
    );
    localStorage.setItem(
      "jobs-finder-chat-v1",
      JSON.stringify({ messages: [], openedJobIds: ["legacy-id"] }),
    );

    clearChatStorage();

    // The constant key is cleared:
    expect(localStorage.getItem(`${FAKE_PREFIX}chat-v1`)).toBeNull();
    // The legacy real key is NOT touched (proves the literal is NOT in the code):
    expect(localStorage.getItem("jobs-finder-chat-v1")).not.toBeNull();
  });
});
