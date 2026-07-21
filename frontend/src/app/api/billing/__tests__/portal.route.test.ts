// Tests for POST /api/billing/portal.
//
// The route returns a Stripe Customer Portal URL for the caller's
// existing Stripe customer (paid users only). Free users without a
// Stripe customer ID get 400.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockAuth = { getSession: vi.fn() };
const mockFrom = vi.fn();
const mockSupabase = {
  auth: mockAuth,
  from: mockFrom,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

const mockPortalSessionsCreate = vi.fn();
const mockStripeInstance = {
  billingPortal: { sessions: { create: mockPortalSessionsCreate } },
};

vi.mock("@/lib/billing/stripe-server", () => ({
  getStripe: () => mockStripeInstance,
}));

import { POST } from "../portal/route";

const ORIGINAL_KEY = process.env.STRIPE_SECRET_KEY;

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.NEXT_PUBLIC_BILLING_ENABLED;
  process.env.NEXT_PUBLIC_BILLING_ENABLED = "true";
  process.env.STRIPE_SECRET_KEY = "sk_test_dummy";
});

describe("POST /api/billing/portal — kill switch + auth", () => {
  it("returns 503 when billing is disabled", async () => {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = "false";

    const res = await POST();

    expect(res.status).toBe(503);
  });

  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await POST();

    expect(res.status).toBe(401);
    expect(mockPortalSessionsCreate).not.toHaveBeenCalled();
  });
});

describe("POST /api/billing/portal — paid-only access", () => {
  it("returns 400 when the user has NO Stripe customer ID (Free user)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-free" } } },
      error: null,
    });
    // `maybeSingle` returns null when no row matches.
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

    const res = await POST();

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/billing account/i);
    expect(mockPortalSessionsCreate).not.toHaveBeenCalled();
  });

  it("returns 302 to the Stripe Portal URL for a paid user", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-paid" } } },
      error: null,
    });
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: { stripe_customer_id: "cus_xyz" },
            error: null,
          }),
        }),
      }),
    });
    mockPortalSessionsCreate.mockResolvedValueOnce({
      url: "https://billing.stripe.com/p/session/test_abc",
    });

    const res = await POST();

    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://billing.stripe.com/p/session/test_abc",
    );
    expect(mockPortalSessionsCreate).toHaveBeenCalledWith({
      customer: "cus_xyz",
      return_url: expect.stringContaining("/settings/billing"),
    });
  });

  it("returns 500 when Stripe itself throws (no raw error leakage)", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-paid-2" } } },
      error: null,
    });
    mockFrom.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: { stripe_customer_id: "cus_zzz" },
            error: null,
          }),
        }),
      }),
    });
    mockPortalSessionsCreate.mockRejectedValueOnce(
      new Error("Stripe customer cus_zzz does not exist"),
    );

    const res = await POST();

    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/portal/i);
    // Customer ID / error message must NOT leak to the client.
    expect(body.error).not.toContain("cus_zzz");
    errSpy.mockRestore();
  });
});

// Restore env after the suite runs (vitest doesn't auto-restore).
if (ORIGINAL_KEY === undefined) {
  delete process.env.STRIPE_SECRET_KEY;
} else {
  process.env.STRIPE_SECRET_KEY = ORIGINAL_KEY;
}