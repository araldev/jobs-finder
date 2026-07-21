// Tests for POST /api/billing/checkout.
//
// The route:
//   - returns 503 when billing is disabled,
//   - returns 401 when the user is not authenticated,
//   - creates a Stripe Checkout session with a per-user
//     idempotency key (so a double-click returns the same session),
//   - passes trial_period_days=7 for Pro,
//   - redirects (302) to the Stripe-hosted Checkout URL,
//   - returns 500 when the Stripe price ID env vars are missing,
//   - returns 500 when Stripe itself throws.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockAuth = { getSession: vi.fn() };
const mockSupabase = { auth: mockAuth };

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

const mockSessionsCreate = vi.fn();
const mockStripeInstance = {
  checkout: { sessions: { create: mockSessionsCreate } },
};

vi.mock("@/lib/billing/stripe-server", () => ({
  getStripe: () => mockStripeInstance,
}));

import { POST } from "../checkout/route";

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  vi.clearAllMocks();
  process.env = { ...ORIGINAL_ENV };
  process.env.NEXT_PUBLIC_BILLING_ENABLED = "true";
  process.env.STRIPE_PRICE_ID_PRO_MONTHLY = "price_monthly_123";
  process.env.STRIPE_PRICE_ID_PRO_ANNUAL = "price_annual_456";
  process.env.STRIPE_SECRET_KEY = "sk_test_dummy";
});

describe("POST /api/billing/checkout — kill switch + auth", () => {
  it("returns 503 when billing is disabled", async () => {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = "false";

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
    });

    const res = await POST(req as never);

    expect(res.status).toBe(503);
  });

  it("returns 401 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
    });

    const res = await POST(req as never);

    expect(res.status).toBe(401);
    expect(mockSessionsCreate).not.toHaveBeenCalled();
  });
});

describe("POST /api/billing/checkout — Stripe call shape", () => {
  it("creates a monthly session with trial_period_days=7 and redirects 302", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: {
        session: { user: { id: "user-1", email: "u@example.com" } },
      },
      error: null,
    });
    mockSessionsCreate.mockResolvedValueOnce({
      url: "https://checkout.stripe.com/c/pay/cs_test_abc",
    });

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "monthly" }),
    });

    const res = await POST(req as never);

    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://checkout.stripe.com/c/pay/cs_test_abc",
    );

    expect(mockSessionsCreate).toHaveBeenCalledTimes(1);
    const [params, opts] = mockSessionsCreate.mock.calls[0]!;
    expect(params.mode).toBe("subscription");
    expect(params.line_items).toEqual([
      { price: "price_monthly_123", quantity: 1 },
    ]);
    expect(params.subscription_data?.trial_period_days).toBe(7);
    expect(params.customer_email).toBe("u@example.com");
    expect(params.metadata?.userId).toBe("user-1");
    expect(params.success_url).toContain("/settings/billing?upgraded=1");
    expect(params.cancel_url).toContain("/settings/billing?canceled=1");

    // Idempotency key MUST be per-user+per-interval.
    expect(opts).toEqual({
      idempotencyKey: "checkout-user-1-monthly",
    });
  });

  it("creates an annual session when priceInterval=annual", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-2", email: null } } },
      error: null,
    });
    mockSessionsCreate.mockResolvedValueOnce({
      url: "https://checkout.stripe.com/c/pay/cs_test_xyz",
    });

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "annual" }),
    });

    const res = await POST(req as never);

    expect(res.status).toBe(302);
    const [, opts] = mockSessionsCreate.mock.calls[0]!;
    expect(opts).toEqual({ idempotencyKey: "checkout-user-2-annual" });
    const [params] = mockSessionsCreate.mock.calls[0]!;
    expect(params.line_items).toEqual([
      { price: "price_annual_456", quantity: 1 },
    ]);
  });

  it("reuses the SAME idempotency key on a repeat call (double-click safe)", async () => {
    mockAuth.getSession.mockResolvedValue({
      data: { session: { user: { id: "user-3", email: null } } },
      error: null,
    });
    mockSessionsCreate.mockResolvedValue({
      url: "https://checkout.stripe.com/c/pay/cs_test_same",
    });

    const req1 = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "monthly" }),
    });
    const req2 = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "monthly" }),
    });

    await POST(req1 as never);
    await POST(req2 as never);

    expect(mockSessionsCreate).toHaveBeenCalledTimes(2);
    const opts1 = mockSessionsCreate.mock.calls[0]![1] as { idempotencyKey: string };
    const opts2 = mockSessionsCreate.mock.calls[1]![1] as { idempotencyKey: string };
    // Stripe uses the same key to return the cached session on the
    // second call — same key = no duplicate subscription.
    expect(opts1.idempotencyKey).toBe(opts2.idempotencyKey);
  });

  it("returns 500 when STRIPE_PRICE_ID_PRO_MONTHLY is unset", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-4", email: null } } },
      error: null,
    });
    delete process.env.STRIPE_PRICE_ID_PRO_MONTHLY;

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "monthly" }),
    });

    const res = await POST(req as never);

    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/price/i);
    expect(mockSessionsCreate).not.toHaveBeenCalled();
  });

  it("returns 500 when Stripe itself throws (no raw error leakage)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { user: { id: "user-5", email: null } } },
      error: null,
    });
    mockSessionsCreate.mockRejectedValueOnce(
      new Error("Stripe API key invalid: sk_test_SUPER_SECRET"),
    );

    const req = new Request("http://localhost/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ priceInterval: "monthly" }),
    });

    const res = await POST(req as never);

    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/failed to create/i);
    // The Stripe API key MUST NOT leak.
    expect(body.error).not.toContain("sk_test_SUPER_SECRET");
  });
});