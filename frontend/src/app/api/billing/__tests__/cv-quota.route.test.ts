// Tests for GET /api/billing/cv-quota.
//
// The route returns `{ used, limit, plan }` derived from the cached
// plan + a Supabase count of this-month's cv_adapted events. Auth
// is required (anon callers get 401).

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockAuth = {
  getSession: vi.fn(),
};

// The user-facing Supabase client (for getSession + user_engagement
// count via createClient from @/lib/supabase/server).
const mockSupabase = {
  auth: mockAuth,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

import { GET } from "../cv-quota/route";
import { planCacheClear, planCacheSet } from "@/lib/billing/plan-cache";
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

describe("GET /api/billing/cv-quota — kill switch + auth", () => {
  it("returns 503 when billing is disabled", async () => {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = "false";

    const res = await GET();

    expect(res.status).toBe(503);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/not enabled/i);
  });

  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await GET();

    expect(res.status).toBe(401);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/unauthorized/i);
  });
});

describe("GET /api/billing/cv-quota — monthly boundary + plan variants", () => {
  function makeCountChain(resolved: {
    count?: number | null;
    error?: { message: string } | null;
  }) {
    const stub: Record<string, unknown> = {};
    stub.from = vi.fn(() => stub);
    stub.select = vi.fn(() => stub);
    stub.eq = vi.fn(() => stub);
    stub.gte = vi.fn(() => Promise.resolve(resolved));
    return stub as unknown as { from: ReturnType<typeof vi.fn> };
  }

  it("returns used/limit/plan for a Free user with 2 adaptations this month", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-free" } } },
      error: null,
    });
    // No cached plan → default to Free.
    const stub = makeCountChain({ count: 2, error: null });
    mockSupabase.from = stub.from as never;

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      used: number;
      limit: number | "unlimited";
      plan: string;
    };
    expect(body).toEqual({ used: 2, limit: 3, plan: "free" });
  });

  it("returns unlimited limit for a Pro user (cached)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-pro" } } },
      error: null,
    });
    planCacheSet("user-pro", PRO_SUB);
    // The cv count is still queried but the limit comes from the
    // plan config. (The route does not call .from when the cache
    // hits — but in this case it DOES query user_engagement to
    // compute `used`. We mock that to return 12.)
    const stub = makeCountChain({ count: 12, error: null });
    mockSupabase.from = stub.from as never;

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      used: number;
      limit: number | "unlimited";
      plan: string;
    };
    expect(body).toEqual({ used: 12, limit: "unlimited", plan: "pro" });
  });

  it("returns used=0 when Supabase reports an error (graceful degradation)", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-err" } } },
      error: null,
    });
    const stub = makeCountChain({
      count: null,
      error: { message: "permission denied" },
    });
    mockSupabase.from = stub.from as never;

    const res = await GET();

    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      used: number;
      limit: number | "unlimited";
      plan: string;
    };
    // countCvAdaptedThisMonth returns 0 on error → `used` is 0 but
    // the limit is still derived from the plan (Free default).
    expect(body.used).toBe(0);
    expect(body.limit).toBe(3);
    expect(body.plan).toBe("free");
    errSpy.mockRestore();
  });
});