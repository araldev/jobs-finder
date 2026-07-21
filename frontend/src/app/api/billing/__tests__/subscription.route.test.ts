// Tests for GET /api/billing/subscription.
//
// The route has 3 paths:
//   - Billing disabled → 503 with a clear error.
//   - Cache HIT (planCacheGet(userId) → truthy) → return cached value.
//   - Cache MISS → fetch from DB via service-role, cache it,
//     default to Free if no row.
//
// We mock both the user-facing Supabase client (for getSession) and
// the service-role client (for getSubscriptionForUser). The plan
// cache is real — we use planCacheClear() for test isolation.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockAuth = {
  getSession: vi.fn(),
};

const mockUserSupabase = {
  auth: mockAuth,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockUserSupabase,
}));

const mockGetSubscriptionForUser = vi.fn();
const mockServiceRole = {};

vi.mock("@/lib/supabase/service-role", () => ({
  getServiceRoleClient: () => mockServiceRole,
}));

vi.mock("@/lib/billing/plan-repo", () => ({
  getSubscriptionForUser: (...args: unknown[]) =>
    mockGetSubscriptionForUser(...args),
}));

import { GET } from "../subscription/route";
import { planCacheClear, planCacheGet } from "@/lib/billing/plan-cache";
import type { Subscription } from "@/types/billing";

const PRO_SUB: Subscription = {
  plan: "pro",
  status: "active",
  currentPeriodEnd: "2026-08-01T00:00:00.000Z",
  trialEnd: null,
  cancelAtPeriodEnd: false,
  stripeCustomerId: "cus_xyz",
};

beforeEach(() => {
  vi.clearAllMocks();
  planCacheClear();
  delete process.env.NEXT_PUBLIC_BILLING_ENABLED;
  process.env.NEXT_PUBLIC_BILLING_ENABLED = "true";
});

describe("GET /api/billing/subscription — kill switch + anon paths", () => {
  it("returns 503 when NEXT_PUBLIC_BILLING_ENABLED is not 'true'", async () => {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = "false";

    const res = await GET();

    expect(res.status).toBe(503);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/not enabled/i);
  });

  it("returns the Free default for an anonymous caller (no session)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as { subscription: Subscription };
    expect(body.subscription.plan).toBe("free");
    expect(body.subscription.status).toBe("active");
    // Anonymous callers MUST NOT trigger a DB read.
    expect(mockGetSubscriptionForUser).not.toHaveBeenCalled();
  });
});

describe("GET /api/billing/subscription — cache path", () => {
  it("returns the cached value on a cache HIT (no DB read)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-cached" } } },
      error: null,
    });
    // Pre-warm the cache (production code calls planCacheSet on a
    // cache miss; the route handler short-circuits on a hit).
    planCacheClear();
    // Manually inject a cached subscription via the public setter.
    const { planCacheSet } = await import("@/lib/billing/plan-cache");
    planCacheSet("user-cached", PRO_SUB);

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as { subscription: Subscription };
    expect(body.subscription).toEqual(PRO_SUB);
    expect(mockGetSubscriptionForUser).not.toHaveBeenCalled();
    // Sanity: the cache itself still holds the value (the GET path
    // doesn't accidentally evict on a hit).
    expect(planCacheGet("user-cached")).toEqual(PRO_SUB);
  });
});

describe("GET /api/billing/subscription — DB path", () => {
  it("returns the DB row on cache miss and primes the cache", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-uncached" } } },
      error: null,
    });
    mockGetSubscriptionForUser.mockResolvedValueOnce(PRO_SUB);

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as { subscription: Subscription };
    expect(body.subscription).toEqual(PRO_SUB);
    expect(mockGetSubscriptionForUser).toHaveBeenCalledWith("user-uncached");
    // The cache was primed so the next read skips the DB.
    expect(planCacheGet("user-uncached")).toEqual(PRO_SUB);
  });

  it("returns the Free default when the user has NO subscription row", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-no-row" } } },
      error: null,
    });
    mockGetSubscriptionForUser.mockResolvedValueOnce(null);

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as { subscription: Subscription };
    expect(body.subscription.plan).toBe("free");
    // The Free default is also cached so a follow-up read doesn't
    // re-hit the DB.
    expect(planCacheGet("user-no-row")?.plan).toBe("free");
  });

  it("returns the Free default (does NOT throw) when the DB read fails", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-db-err" } } },
      error: null,
    });
    mockGetSubscriptionForUser.mockRejectedValueOnce(new Error("connection refused"));

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as { subscription: Subscription };
    expect(body.subscription.plan).toBe("free");
    errSpy.mockRestore();
  });
});