// Tests for the lazy Stripe SDK singleton.
//
// `getStripe()` returns a memoized Stripe instance so we don't pay
// the SDK init cost on every webhook / checkout call. It MUST throw
// when STRIPE_SECRET_KEY is missing (the SDK constructor would throw
// a less-helpful error otherwise — design D3 / AGENTS.md rule #23).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockStripeInstance = {
  __sentinel: "stripe-instance",
};

const mockStripeCtor = vi.fn();

// The Stripe SDK exports the constructor as the module's default
// export (ESM-style). The source uses `import Stripe from "stripe"`
// (and `new Stripe(key, opts)`), so the mock must expose a
// constructible `default`. vi.mock factories run at module init, so
// the FakeStripe class is declared INSIDE the factory closure to
// avoid TDZ when vi.mock is hoisted.
vi.mock("stripe", () => {
  class FakeStripe {
    constructor(...args: unknown[]) {
      mockStripeCtor(...args);
      return mockStripeInstance as unknown as FakeStripe;
    }
  }
  return { default: FakeStripe };
});

import { getStripe } from "../stripe-server";

describe("getStripe — lazy SDK singleton", () => {
  const ORIGINAL_KEY = process.env.STRIPE_SECRET_KEY;

  beforeEach(() => {
    mockStripeCtor.mockReset();
    delete process.env.STRIPE_SECRET_KEY;
  });

  afterEach(() => {
    if (ORIGINAL_KEY === undefined) {
      delete process.env.STRIPE_SECRET_KEY;
    } else {
      process.env.STRIPE_SECRET_KEY = ORIGINAL_KEY;
    }
    vi.clearAllMocks();
  });

  it("throws a clear error when STRIPE_SECRET_KEY is unset", () => {
    expect(() => getStripe()).toThrow(/STRIPE_SECRET_KEY/);
    expect(mockStripeCtor).not.toHaveBeenCalled();
  });

  it("instantiates the Stripe SDK with the secret key + api version when configured", async () => {
    // Reset the module so the test starts with a fresh `_stripe`
    // singleton slot (the prior test threw before instantiating but
    // we want a clean slate for the constructor assertion).
    vi.resetModules();
    const fresh = await import("../stripe-server");
    process.env.STRIPE_SECRET_KEY = "sk_test_xyz";

    const instance = fresh.getStripe();

    expect(mockStripeCtor).toHaveBeenCalledTimes(1);
    expect(mockStripeCtor).toHaveBeenCalledWith("sk_test_xyz", {
      apiVersion: expect.stringMatching(/^\d{4}-\d{2}-\d{2}\./),
    });
    expect(instance).toBe(mockStripeInstance);
  });

  it("returns the same singleton across multiple calls (no re-instantiation)", async () => {
    vi.resetModules();
    const fresh = await import("../stripe-server");
    process.env.STRIPE_SECRET_KEY = "sk_test_xyz";

    const a = fresh.getStripe();
    const b = fresh.getStripe();
    const c = fresh.getStripe();

    expect(a).toBe(b);
    expect(b).toBe(c);
    // The Stripe SDK constructor must only run once per process.
    expect(mockStripeCtor).toHaveBeenCalledTimes(1);
  });
});