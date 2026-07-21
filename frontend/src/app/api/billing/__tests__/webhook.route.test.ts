// Tests for POST /api/billing/webhook.
//
// The webhook is the ONLY Stripe-touched code path that runs without
// a user JWT — it authenticates via the Stripe signature over the
// raw body bytes. We mock:
//   - stripe.webhooks.constructEvent (returns a controlled event),
//   - the service-role Supabase client (UPSERT + INSERT + count).
//
// The 6-event matrix is the canonical regression surface; we also
// pin the contract for replay-safe idempotency and bad-signature
// rejection.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

// ── Stripe SDK mock ──────────────────────────────────────────────────────

const mockConstructEvent = vi.fn();

vi.mock("stripe", () => {
  class FakeStripe {
    webhooks = { constructEvent: (...args: unknown[]) => mockConstructEvent(...args) };
  }
  return { default: FakeStripe };
});

vi.mock("@/lib/billing/stripe-server", () => ({
  getStripe: () => ({
    webhooks: { constructEvent: mockConstructEvent },
  }),
}));

// ── Service-role Supabase mock ───────────────────────────────────────────

const mockFrom = vi.fn();
const mockServiceSupabase = {
  from: mockFrom,
};

vi.mock("@/lib/supabase/service-role", () => ({
  getServiceRoleClient: () => mockServiceSupabase,
}));

import { POST } from "../webhook/route";
import { planCacheClear, planCacheGet, planCacheSet } from "@/lib/billing/plan-cache";

const ORIGINAL_BILLING = process.env.NEXT_PUBLIC_BILLING_ENABLED;
const ORIGINAL_SECRET = process.env.STRIPE_WEBHOOK_SECRET;
const ORIGINAL_KEY = process.env.STRIPE_SECRET_KEY;

beforeEach(() => {
  vi.clearAllMocks();
  planCacheClear();
  process.env.NEXT_PUBLIC_BILLING_ENABLED = "true";
  process.env.STRIPE_WEBHOOK_SECRET = "whsec_test_dummy";
  process.env.STRIPE_SECRET_KEY = "sk_test_dummy";
});

// ── Test helpers ──────────────────────────────────────────────────────────

interface FakeSubscription {
  id: string;
  object: "subscription";
  status: "active" | "trialing" | "past_due" | "canceled";
  customer: string;
  current_period_end: number;
  trial_end: number | null;
  cancel_at_period_end: boolean;
  metadata: { userId: string };
  items: { data: Array<{ price: { id: string } }> };
}

function makeSubscriptionEvent(
  type:
    | "customer.subscription.created"
    | "customer.subscription.updated"
    | "customer.subscription.deleted",
  overrides: Partial<FakeSubscription> = {},
): { id: string; type: string; data: { object: FakeSubscription } } {
  const baseSub: FakeSubscription = {
    id: "sub_test_xyz",
    object: "subscription",
    status: "active",
    customer: "cus_test_abc",
    current_period_end: Math.floor(Date.now() / 1000) + 86400 * 30,
    trial_end: null,
    cancel_at_period_end: false,
    metadata: { userId: "user-webhook-1" },
    items: { data: [{ price: { id: "price_monthly_123" } }] },
    ...overrides,
  };
  return {
    id: `evt_${type}_${Math.random().toString(36).slice(2, 10)}`,
    type,
    data: { object: baseSub },
  };
}

/**
 * Build a Request whose `text()` returns the exact raw bytes (Stripe
 * HMAC must verify over these bytes — parsing JSON first would
 * corrupt the signature). The body is the JSON-serialized event.
 */
function makeWebhookRequest(event: object): Request {
  const body = JSON.stringify(event);
  return new Request("http://localhost/api/billing/webhook", {
    method: "POST",
    body,
    headers: {
      "Content-Type": "application/json",
      // Stripe sends the signature header verbatim; our route reads
      // it as `request.headers.get("stripe-signature")`. The actual
      // signature value is irrelevant — constructEvent is mocked.
      "stripe-signature": "t=1234567890,v1=fake-signature",
    },
  });
}

/**
 * Build a chainable mock that resolves to a single Insert/Upsert
 * result. The webhook handler never chains beyond the leaf, so a
 * flat builder is enough.
 */
function makeInsertBuilder(resolved: { error: { message: string } | null } = {
  error: null,
}) {
  return {
    upsert: vi.fn().mockResolvedValue(resolved),
    insert: vi.fn().mockResolvedValue(resolved),
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    maybeSingle: vi.fn().mockResolvedValue({ data: null, error: null }),
  };
}

// ── Tests ────────────────────────────────────────────────────────────────

describe("POST /api/billing/webhook — kill switch + signature", () => {
  it("returns 503 when billing is disabled", async () => {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = "false";

    const res = await POST(
      makeWebhookRequest({}) as never,
    );

    expect(res.status).toBe(503);
    expect(mockConstructEvent).not.toHaveBeenCalled();
  });

  it("returns 400 on a bad signature (mocked constructEvent throws)", async () => {
    mockConstructEvent.mockImplementationOnce(() => {
      const err = new Error("No signatures found matching the expected signature");
      throw err;
    });

    const res = await POST(makeWebhookRequest({ id: "evt_x", type: "x" }) as never);

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/invalid signature/i);
  });
});

describe("POST /api/billing/webhook — replay-safe idempotency", () => {
  it("returns 200 with received:true on a REPLAYED event (already in billing_events)", async () => {
    const event = makeSubscriptionEvent("customer.subscription.updated");
    mockConstructEvent.mockReturnValueOnce(event);

    // The insert into billing_events throws because the event_id
    // already exists (unique constraint). The route catches and
    // returns 200 — no UPSERT, no cache invalidate.
    mockFrom.mockReturnValue({
      insert: vi.fn().mockResolvedValueOnce({
        error: { message: 'duplicate key value violates unique constraint "billing_events_event_id_key"' },
      }),
    });

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    const body = (await res.json()) as { received: boolean };
    expect(body.received).toBe(true);
    // No UPSERT on replay.
    const upsertCalls = mockFrom.mock.results
      .map((r) => (r.value as { upsert?: ReturnType<typeof vi.fn> })?.upsert)
      .filter(Boolean);
    expect(upsertCalls).toHaveLength(0);
  });
});

describe("POST /api/billing/webhook — 6-event matrix", () => {
  it("customer.subscription.created: UPSERTs and invalidates the cache", async () => {
    const event = makeSubscriptionEvent("customer.subscription.created");
    mockConstructEvent.mockReturnValueOnce(event);

    // billing_events INSERT succeeds (new event).
    const insertBuilder = makeInsertBuilder({ error: null });
    // subscriptions UPSERT.
    const upsertBuilder = makeInsertBuilder({ error: null });
    let fromCall = 0;
    mockFrom.mockImplementation(() => {
      fromCall++;
      // 1st: billing_events insert. 2nd: subscriptions upsert.
      return fromCall === 1 ? insertBuilder : upsertBuilder;
    });

    // Pre-warm the cache so we can prove invalidation happens.
    planCacheSet("user-webhook-1", {
      plan: "free",
      status: "active",
      currentPeriodEnd: null,
      trialEnd: null,
      cancelAtPeriodEnd: false,
      stripeCustomerId: null,
    });

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    expect(mockFrom).toHaveBeenCalledWith("billing_events");
    expect(mockFrom).toHaveBeenCalledWith("subscriptions");
    expect(upsertBuilder.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: "user-webhook-1",
        plan: "pro",
        status: "active",
        stripe_customer_id: "cus_test_abc",
        stripe_subscription_id: "sub_test_xyz",
      }),
      expect.objectContaining({ onConflict: "user_id" }),
    );
    // Cache was invalidated.
    expect(planCacheGet("user-webhook-1")).toBeNull();
  });

  it("customer.subscription.updated (trialing): UPSERTs with status=trialing", async () => {
    const event = makeSubscriptionEvent("customer.subscription.updated", {
      status: "trialing",
      trial_end: Math.floor(Date.now() / 1000) + 86400 * 7,
    });
    mockConstructEvent.mockReturnValueOnce(event);

    const insertBuilder = makeInsertBuilder({ error: null });
    const upsertBuilder = makeInsertBuilder({ error: null });
    let fromCall = 0;
    mockFrom.mockImplementation(() => {
      fromCall++;
      return fromCall === 1 ? insertBuilder : upsertBuilder;
    });

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    expect(upsertBuilder.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        plan: "pro",
        status: "trialing",
      }),
      expect.any(Object),
    );
  });

  it("customer.subscription.deleted: UPSERTs plan=free, status=canceled", async () => {
    const event = makeSubscriptionEvent("customer.subscription.deleted", {
      status: "canceled",
    });
    mockConstructEvent.mockReturnValueOnce(event);

    const insertBuilder = makeInsertBuilder({ error: null });
    const upsertBuilder = makeInsertBuilder({ error: null });
    let fromCall = 0;
    mockFrom.mockImplementation(() => {
      fromCall++;
      return fromCall === 1 ? insertBuilder : upsertBuilder;
    });

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    expect(upsertBuilder.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        plan: "free",
        status: "canceled",
      }),
      expect.any(Object),
    );
  });

  it("invoice.paid: returns 200 but does NOT mutate the subscription", async () => {
    const event = {
      id: "evt_invoice_paid_xyz",
      type: "invoice.paid",
      data: {
        object: {
          id: "in_test_xyz",
          object: "invoice",
          customer: "cus_test_abc",
          subscription: "sub_test_xyz",
          amount_paid: 1999,
          status: "paid",
        },
      },
    };
    mockConstructEvent.mockReturnValueOnce(event);

    const insertBuilder = makeInsertBuilder({ error: null });
    mockFrom.mockReturnValueOnce(insertBuilder);

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    // Only the billing_events insert happened — no subscription UPSERT.
    expect(insertBuilder.insert).toHaveBeenCalledTimes(1);
    expect(insertBuilder.upsert).not.toHaveBeenCalled();
  });

  it("invoice.payment_failed: acknowledges + appends billing_events (no UPSERT — userId unknown from invoice)", async () => {
    // The Invoice payload exposes the Stripe subscription_id but
    // NOT the userId metadata (that's on the Subscription object).
    // v1 relies on the companion customer.subscription.updated event
    // (Stripe always sends both) to drive the actual UPSERT. The
    // handler here just acknowledges + appends the audit event.
    const event = {
      id: "evt_invoice_failed_xyz",
      type: "invoice.payment_failed",
      data: {
        object: {
          id: "in_test_yyy",
          object: "invoice",
          customer: "cus_test_abc",
          subscription: "sub_test_xyz",
          amount_due: 1999,
        },
      },
    };
    mockConstructEvent.mockReturnValueOnce(event);

    const insertBuilder = makeInsertBuilder({ error: null });
    mockFrom.mockReturnValueOnce(insertBuilder);

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    // billing_events INSERT happened for audit.
    expect(insertBuilder.insert).toHaveBeenCalledTimes(1);
    // No UPSERT — the handler can't resolve userId from the Invoice alone.
    expect(insertBuilder.upsert).not.toHaveBeenCalled();
  });

  it("checkout.session.completed: routes to the same subscription upsert path", async () => {
    const event = makeSubscriptionEvent("customer.subscription.created");
    // The actual `type` for this test case is checkout.session.completed
    // — the route treats it identically to customer.subscription.created
    // (both flow through handleSubscriptionChange).
    event.type = "checkout.session.completed";
    mockConstructEvent.mockReturnValueOnce(event);

    const insertBuilder = makeInsertBuilder({ error: null });
    const upsertBuilder = makeInsertBuilder({ error: null });
    let fromCall = 0;
    mockFrom.mockImplementation(() => {
      fromCall++;
      return fromCall === 1 ? insertBuilder : upsertBuilder;
    });

    const res = await POST(makeWebhookRequest(event) as never);

    expect(res.status).toBe(200);
    expect(upsertBuilder.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        plan: "pro",
      }),
      expect.any(Object),
    );
  });
});

// ── Env restoration ──────────────────────────────────────────────────────

afterAll(() => {
  if (ORIGINAL_BILLING === undefined) {
    delete process.env.NEXT_PUBLIC_BILLING_ENABLED;
  } else {
    process.env.NEXT_PUBLIC_BILLING_ENABLED = ORIGINAL_BILLING;
  }
  if (ORIGINAL_SECRET === undefined) {
    delete process.env.STRIPE_WEBHOOK_SECRET;
  } else {
    process.env.STRIPE_WEBHOOK_SECRET = ORIGINAL_SECRET;
  }
  if (ORIGINAL_KEY === undefined) {
    delete process.env.STRIPE_SECRET_KEY;
  } else {
    process.env.STRIPE_SECRET_KEY = ORIGINAL_KEY;
  }
});