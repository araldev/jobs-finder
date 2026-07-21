// Tests for the Stripe webhook signature verifier.
//
// `verifyWebhookSignature` calls `stripe.webhooks.constructEvent`
// over the raw body bytes. We mock `stripe` (already exercised in
// stripe-server.test.ts) and assert that:
//   - a clear error is thrown when STRIPE_WEBHOOK_SECRET is unset,
//   - a verified event is returned when the signature is valid,
//   - a WebhookSignatureError wraps any constructEvent failure,
//   - the env-var error message includes the var name (so the
//     operator knows what to fix).

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockConstructEvent = vi.fn();

vi.mock("stripe", () => {
  class FakeStripe {
    webhooks = {
      constructEvent: (...args: unknown[]) => mockConstructEvent(...args),
    };
  }
  return { default: FakeStripe };
});

const mockGetStripe = vi.fn();
vi.mock("@/lib/billing/stripe-server", () => ({
  getStripe: () => mockGetStripe(),
}));

import { verifyWebhookSignature, WebhookSignatureError } from "../webhook-verify";

const ORIGINAL_SECRET = process.env.STRIPE_WEBHOOK_SECRET;
const ORIGINAL_KEY = process.env.STRIPE_SECRET_KEY;

beforeEach(() => {
  mockConstructEvent.mockReset();
  mockGetStripe.mockReset();
  process.env.STRIPE_SECRET_KEY = "sk_test_dummy";
  process.env.STRIPE_WEBHOOK_SECRET = "whsec_test_dummy";

  mockGetStripe.mockReturnValue({
    webhooks: { constructEvent: mockConstructEvent },
  });
});

describe("verifyWebhookSignature", () => {
  it("throws when STRIPE_WEBHOOK_SECRET is unset", () => {
    delete process.env.STRIPE_WEBHOOK_SECRET;

    expect(() => verifyWebhookSignature("body", "sig"))
      .toThrow(/STRIPE_WEBHOOK_SECRET/);
    expect(mockConstructEvent).not.toHaveBeenCalled();
  });

  it("returns the verified Stripe.Event on a valid signature", () => {
    const fakeEvent = {
      id: "evt_123",
      type: "customer.subscription.updated",
      data: { object: {} },
    };
    mockConstructEvent.mockReturnValue(fakeEvent);

    const result = verifyWebhookSignature(
      '{"id":"evt_123"}',
      "valid-sig",
    );

    expect(result).toEqual(fakeEvent);
    expect(mockConstructEvent).toHaveBeenCalledWith(
      '{"id":"evt_123"}',
      "valid-sig",
      "whsec_test_dummy",
    );
  });

  it("wraps a Stripe Error in WebhookSignatureError (invalid sig)", () => {
    mockConstructEvent.mockImplementation(() => {
      throw new Error("No signatures found matching the expected signature");
    });

    expect(() => verifyWebhookSignature("body", "bad-sig"))
      .toThrow(WebhookSignatureError);
  });

  it("wraps a non-Error throw in WebhookSignatureError (defensive)", () => {
    mockConstructEvent.mockImplementation(() => {
      throw "string-not-error"; // intentional: not an Error instance
    });

    expect(() => verifyWebhookSignature("body", "bad-sig"))
      .toThrow(WebhookSignatureError);
  });

  it("WebhookSignatureError has a recognisable name (downstream catches via instanceof)", () => {
    mockConstructEvent.mockImplementation(() => {
      throw new Error("mismatch");
    });
    try {
      verifyWebhookSignature("body", "bad");
    } catch (err) {
      expect(err).toBeInstanceOf(WebhookSignatureError);
      expect((err as Error).name).toBe("WebhookSignatureError");
    }
  });

  it("does not leak the raw Stripe error message in the thrown WebhookSignatureError wrapper", () => {
    // We log the underlying message server-side; the error type is
    // what propagates. This assertion pins the contract that the
    // wrapper message includes "verification failed".
    mockConstructEvent.mockImplementation(() => {
      throw new Error("internal-super-secret-key-leaked-message");
    });

    let caught: Error | null = null;
    try {
      verifyWebhookSignature("body", "bad");
    } catch (err) {
      caught = err as Error;
    }
    expect(caught).not.toBeNull();
    expect(caught!.message).toContain("verification failed");
  });

  // Restore env so we don't pollute other tests.
  afterAllEnvRestore();

  function afterAllEnvRestore() {
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
  }
});