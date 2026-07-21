// Tests for the per-user plan cache (60s TTL).
//
// The cache is module-level (singleton Map keyed by userId) — that
// means tests share state across files within the same vitest worker
// unless we reset it explicitly. `planCacheClear()` is the official
// escape hatch and we use it in beforeEach.

import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  planCacheGet,
  planCacheSet,
  planCacheInvalidate,
  planCacheClear,
} from "../plan-cache";
import type { Subscription } from "@/types/billing";

const PRO_SUB: Subscription = {
  plan: "pro",
  status: "active",
  currentPeriodEnd: "2027-01-01T00:00:00.000Z",
  trialEnd: null,
  cancelAtPeriodEnd: false,
  stripeCustomerId: "cus_xyz",
};

const TRIAL_SUB: Subscription = {
  plan: "pro",
  status: "trialing",
  currentPeriodEnd: "2026-08-01T00:00:00.000Z",
  trialEnd: "2026-07-28T00:00:00.000Z",
  cancelAtPeriodEnd: false,
  stripeCustomerId: "cus_trial",
};

describe("plan-cache — TTL + invalidation", () => {
  beforeEach(() => {
    planCacheClear();
  });

  it("returns null for an unknown user (cache miss)", () => {
    expect(planCacheGet("user-unknown")).toBeNull();
  });

  it("stores and retrieves a subscription for the same user (cache hit)", () => {
    planCacheSet("user-1", PRO_SUB);
    expect(planCacheGet("user-1")).toEqual(PRO_SUB);
  });

  it("isolates entries across users (no cross-user leak)", () => {
    planCacheSet("user-1", PRO_SUB);
    planCacheSet("user-2", TRIAL_SUB);

    expect(planCacheGet("user-1")).toEqual(PRO_SUB);
    expect(planCacheGet("user-2")).toEqual(TRIAL_SUB);
  });

  it("expires entries after 60s (TTL boundary)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-21T12:00:00.000Z"));

    planCacheSet("user-1", PRO_SUB);

    // 30s later — still valid.
    vi.setSystemTime(new Date("2026-07-21T12:00:30.000Z"));
    expect(planCacheGet("user-1")).toEqual(PRO_SUB);

    // 59.999s later — still valid (the TTL check uses strict `>`).
    vi.setSystemTime(new Date("2026-07-21T12:00:59.999Z"));
    expect(planCacheGet("user-1")).toEqual(PRO_SUB);

    // 61s later — expired.
    vi.setSystemTime(new Date("2026-07-21T12:01:01.000Z"));
    expect(planCacheGet("user-1")).toBeNull();

    // After expiry, the key is also evicted from the map so a
    // subsequent set re-populates it cleanly.
    expect(planCacheSet("user-1", TRIAL_SUB)).toBeUndefined();
    expect(planCacheGet("user-1")).toEqual(TRIAL_SUB);

    vi.useRealTimers();
  });

  it("planCacheInvalidate(userId) evicts only that user's entry", () => {
    planCacheSet("user-1", PRO_SUB);
    planCacheSet("user-2", TRIAL_SUB);

    planCacheInvalidate("user-1");

    expect(planCacheGet("user-1")).toBeNull();
    expect(planCacheGet("user-2")).toEqual(TRIAL_SUB);
  });

  it("planCacheInvalidate is a no-op on an unknown user", () => {
    planCacheSet("user-1", PRO_SUB);
    expect(() => planCacheInvalidate("user-not-set")).not.toThrow();
    expect(planCacheGet("user-1")).toEqual(PRO_SUB);
  });

  it("planCacheClear empties the entire map (test isolation)", () => {
    planCacheSet("user-1", PRO_SUB);
    planCacheSet("user-2", TRIAL_SUB);
    planCacheClear();

    expect(planCacheGet("user-1")).toBeNull();
    expect(planCacheGet("user-2")).toBeNull();
  });
});