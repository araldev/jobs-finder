import { describe, it, expect } from "vitest";
import { JOBS_FINDER_STORAGE_KEYS, STORAGE_KEY_PREFIX } from "../storageKeys";

describe("storageKeys (REQ-AUTH-026 / ADR-005)", () => {
  it("STORAGE_KEY_PREFIX is 'jobs-finder-'", () => {
    expect(STORAGE_KEY_PREFIX).toBe("jobs-finder-");
  });

  it("exports the 3 documented keys", () => {
    expect(JOBS_FINDER_STORAGE_KEYS.favorites).toBe("jobs-finder-favorites");
    expect(JOBS_FINDER_STORAGE_KEYS.chat).toBe("jobs-finder-chat-v1");
    expect(JOBS_FINDER_STORAGE_KEYS.cvAdaptedCount).toBe("jobs-finder-cv-adapted-count");
  });

  it("every key starts with the prefix", () => {
    for (const value of Object.values(JOBS_FINDER_STORAGE_KEYS)) {
      expect(value.startsWith(STORAGE_KEY_PREFIX)).toBe(true);
    }
  });
});
