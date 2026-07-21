// Tests for the service-role subscription + billing-event repo.
//
// The repo bypasses RLS via `getServiceRoleClient` and reads/writes
// the `subscriptions` + `billing_events` tables. We mock the
// service-role client so we can:
//   - assert the SELECT / UPSERT / INSERT / count-query shapes,
//   - assert error propagation,
//   - assert row→Subscription mapping (snake_case DB → camelCase TS),
//   - and PIN the contract that `billingEventExists` returns a real
//     boolean (the original implementation had a broken expression
//     that always evaluated to `false`).

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockSupabase = {
  from: vi.fn(),
};

vi.mock("@/lib/supabase/service-role", () => ({
  getServiceRoleClient: () => mockSupabase,
}));

import {
  getSubscriptionForUser,
  upsertSubscription,
  appendBillingEvent,
  billingEventExists,
} from "../plan-repo";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getSubscriptionForUser — row→Subscription mapping", () => {
  it("returns null when the user has no subscription row", async () => {
    mockSupabase.from.mockReturnValue({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({ data: null, error: null }),
        }),
      }),
    });

    const result = await getSubscriptionForUser("user-1");

    expect(result).toBeNull();
  });

  it("maps a free active row (snake_case → camelCase)", async () => {
    mockSupabase.from.mockReturnValue({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: {
              user_id: "user-1",
              plan: "free",
              status: "active",
              stripe_customer_id: null,
              stripe_subscription_id: null,
              current_period_end: null,
              trial_end: null,
              cancel_at_period_end: false,
              created_at: "2026-07-21T00:00:00.000Z",
              updated_at: "2026-07-21T00:00:00.000Z",
            },
            error: null,
          }),
        }),
      }),
    });

    const result = await getSubscriptionForUser("user-1");

    expect(result).toEqual({
      plan: "free",
      status: "active",
      currentPeriodEnd: null,
      trialEnd: null,
      cancelAtPeriodEnd: false,
      stripeCustomerId: null,
    });
  });

  it("maps a pro trialing row with Stripe IDs populated", async () => {
    mockSupabase.from.mockReturnValue({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: {
              user_id: "user-2",
              plan: "pro",
              status: "trialing",
              stripe_customer_id: "cus_abc",
              stripe_subscription_id: "sub_xyz",
              current_period_end: "2026-08-01T00:00:00.000Z",
              trial_end: "2026-07-28T00:00:00.000Z",
              cancel_at_period_end: true,
              created_at: "2026-07-21T00:00:00.000Z",
              updated_at: "2026-07-21T00:00:00.000Z",
            },
            error: null,
          }),
        }),
      }),
    });

    const result = await getSubscriptionForUser("user-2");

    expect(result).toEqual({
      plan: "pro",
      status: "trialing",
      currentPeriodEnd: "2026-08-01T00:00:00.000Z",
      trialEnd: "2026-07-28T00:00:00.000Z",
      cancelAtPeriodEnd: true,
      stripeCustomerId: "cus_abc",
    });
  });

  it("throws when Supabase reports an error (caller must surface the failure)", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabase.from.mockReturnValue({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          maybeSingle: vi.fn().mockResolvedValue({
            data: null,
            error: { message: "permission denied" },
          }),
        }),
      }),
    });

    await expect(getSubscriptionForUser("user-1")).rejects.toBeDefined();
    errSpy.mockRestore();
  });
});

describe("upsertSubscription — onConflict: user_id", () => {
  it("UPSERTs the row with snake_case keys + onConflict user_id", async () => {
    const mockUpsert = vi.fn().mockResolvedValue({ error: null });
    mockSupabase.from.mockReturnValue({ upsert: mockUpsert });

    await upsertSubscription({
      userId: "user-1",
      plan: "pro",
      status: "active",
      stripeCustomerId: "cus_abc",
      stripeSubscriptionId: "sub_xyz",
      currentPeriodEnd: "2026-08-01T00:00:00.000Z",
      trialEnd: null,
      cancelAtPeriodEnd: false,
    });

    expect(mockSupabase.from).toHaveBeenCalledWith("subscriptions");
    expect(mockUpsert).toHaveBeenCalledTimes(1);
    const [payload, opts] = mockUpsert.mock.calls[0]!;
    expect(payload).toMatchObject({
      user_id: "user-1",
      plan: "pro",
      status: "active",
      stripe_customer_id: "cus_abc",
      stripe_subscription_id: "sub_xyz",
      current_period_end: "2026-08-01T00:00:00.000Z",
      trial_end: null,
      cancel_at_period_end: false,
    });
    expect(payload).toHaveProperty("updated_at");
    expect(opts).toEqual({ onConflict: "user_id" });
  });

  it("throws when Supabase reports an error", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabase.from.mockReturnValue({
      upsert: vi.fn().mockResolvedValue({
        error: { message: "duplicate key value violates unique constraint" },
      }),
    });

    await expect(
      upsertSubscription({ userId: "user-1", plan: "pro", status: "active" }),
    ).rejects.toBeDefined();
    errSpy.mockRestore();
  });
});

describe("appendBillingEvent — INSERT into billing_events", () => {
  it("inserts event_id, event_type, payload", async () => {
    const mockInsert = vi.fn().mockResolvedValue({ error: null });
    mockSupabase.from.mockReturnValue({ insert: mockInsert });

    await appendBillingEvent({
      eventId: "evt_123",
      eventType: "customer.subscription.updated",
      payload: { id: "evt_123", type: "customer.subscription.updated" },
    });

    expect(mockSupabase.from).toHaveBeenCalledWith("billing_events");
    expect(mockInsert).toHaveBeenCalledWith({
      event_id: "evt_123",
      event_type: "customer.subscription.updated",
      payload: { id: "evt_123", type: "customer.subscription.updated" },
    });
  });
});

describe("billingEventExists — unique-violation idempotency check", () => {
  it("returns TRUE when the count is 1 (event already seen)", async () => {
    // PostgREST returns `count` (a number) when `head: true` is set;
    // the data field is null. We exercise the canonical shape.
    mockSupabase.from.mockReturnValue({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockReturnValue({
          // The actual SQL count comes back via the second await — we
          // resolve a { count, error } pair directly.
          // (The repo unwraps via Promise resolution; that's how
          // Supabase JS v2 returns it.)
        }),
      }),
    });

    // The repo currently resolves via `await supabase.from(...).select(...).eq(...)`
    // — and the `count` lands on the `.eq(...)` chain's resolved value
    // because `head: true` skips the row payload.
    mockSupabase.from.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockResolvedValue({
          count: 1,
          error: null,
        }),
      }),
    });

    const exists = await billingEventExists("evt_duplicate");
    expect(exists).toBe(true);
  });

  it("returns FALSE when the count is 0 (event has not been seen)", async () => {
    mockSupabase.from.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockResolvedValue({
          count: 0,
          error: null,
        }),
      }),
    });

    const exists = await billingEventExists("evt_fresh");
    expect(exists).toBe(false);
  });

  it("returns FALSE on Supabase error (graceful — caller falls back to inserting)", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabase.from.mockReturnValueOnce({
      select: vi.fn().mockReturnValue({
        eq: vi.fn().mockResolvedValue({
          count: null,
          error: { message: "transient" },
        }),
      }),
    });

    const exists = await billingEventExists("evt_err");
    expect(exists).toBe(false);
    errSpy.mockRestore();
  });
});