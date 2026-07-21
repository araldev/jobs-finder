// Tests for DELETE /api/account/me.
//
// Hard-delete the caller's account. The route MUST:
//   - reject anonymous callers (401),
//   - best-effort cancel the user's Stripe subscription (failure
//     MUST NOT block the deletion),
//   - invoke the delete_current_user RPC,
//   - invalidate the user's plan cache,
//   - return 204 No Content on success.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockAuth = { getSession: vi.fn() };
const mockRpc = vi.fn();
const mockFrom = vi.fn();

const mockSupabase = {
  auth: mockAuth,
  rpc: mockRpc,
  from: mockFrom,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

const mockStripeSubscriptionsCancel = vi.fn();
const mockStripeInstance = {
  subscriptions: { cancel: mockStripeSubscriptionsCancel },
};

vi.mock("@/lib/billing/stripe-server", () => ({
  getStripe: () => mockStripeInstance,
}));

import { DELETE } from "../me/route";
import { planCacheClear, planCacheGet, planCacheSet } from "@/lib/billing/plan-cache";
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
  process.env.STRIPE_SECRET_KEY = "sk_test_dummy";
});

describe("DELETE /api/account/me — auth", () => {
  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });

    const res = await DELETE(req as never);

    expect(res.status).toBe(401);
    expect(mockRpc).not.toHaveBeenCalled();
    expect(mockStripeSubscriptionsCancel).not.toHaveBeenCalled();
  });
});

describe("DELETE /api/account/me — best-effort Stripe cancellation", () => {
  it("cancels the Stripe subscription by its SUBSCRIPTION ID, then deletes", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-1" } } },
      error: null,
    });

    // The route selects `stripe_subscription_id` (NOT customer id).
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: { stripe_subscription_id: "sub_xyz" },
            error: null,
          }),
        }),
      }),
    });

    mockStripeSubscriptionsCancel.mockResolvedValueOnce({ id: "sub_xyz" });
    mockRpc.mockResolvedValueOnce({ error: null });

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });
    const res = await DELETE(req as never);

    expect(res.status).toBe(204);
    // Stripe was canceled by subscription ID, not customer ID.
    expect(mockStripeSubscriptionsCancel).toHaveBeenCalledWith("sub_xyz");
    // The RPC ran.
    expect(mockRpc).toHaveBeenCalledWith("delete_current_user");
  });

  it("STILL deletes when Stripe throws (best-effort — deletion must commit)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-2" } } },
      error: null,
    });

    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: { stripe_subscription_id: "sub_to_cancel" },
            error: null,
          }),
        }),
      }),
    });

    // Stripe is down.
    mockStripeSubscriptionsCancel.mockRejectedValueOnce(
      new Error("Stripe API is unreachable"),
    );

    mockRpc.mockResolvedValueOnce({ error: null });

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });
    const res = await DELETE(req as never);

    expect(res.status).toBe(204);
    // RPC ran anyway — deletion commits even when Stripe fails.
    expect(mockRpc).toHaveBeenCalledWith("delete_current_user");
  });

  it("STILL deletes when the user has no Stripe subscription (Free user)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-3" } } },
      error: null,
    });

    // No subscription row → maybeSingle returns null.
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: null,
            error: null,
          }),
        }),
      }),
    });

    mockRpc.mockResolvedValueOnce({ error: null });

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });
    const res = await DELETE(req as never);

    expect(res.status).toBe(204);
    // Stripe was never touched (no subscription to cancel).
    expect(mockStripeSubscriptionsCancel).not.toHaveBeenCalled();
    expect(mockRpc).toHaveBeenCalledWith("delete_current_user");
  });
});

describe("DELETE /api/account/me — cache invalidation", () => {
  it("invalidates the user's plan cache before returning 204", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-cache" } } },
      error: null,
    });
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: null,
            error: null,
          }),
        }),
      }),
    });
    mockRpc.mockResolvedValueOnce({ error: null });

    // Pre-warm the cache so we can prove invalidation.
    planCacheSet("user-cache", PRO_SUB);
    expect(planCacheGet("user-cache")).toEqual(PRO_SUB);

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });
    const res = await DELETE(req as never);

    expect(res.status).toBe(204);
    expect(planCacheGet("user-cache")).toBeNull();
  });
});

describe("DELETE /api/account/me — RPC failure", () => {
  it("returns 500 (with a generic error) when the RPC fails", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-rpc-fail" } } },
      error: null,
    });
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: null,
            error: null,
          }),
        }),
      }),
    });
    mockRpc.mockResolvedValueOnce({
      error: { message: "FK violation: user owns content" },
    });

    const req = new Request("http://localhost/api/account/me", {
      method: "DELETE",
    });
    const res = await DELETE(req as never);

    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/deletion failed/i);
    // The internal FK violation message MUST NOT leak to the client.
    expect(body.error).not.toContain("FK violation");
  });
});