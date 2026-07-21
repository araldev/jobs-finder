// Tests for the CV-quota primitives.
//
// `monthStartUtc` and `enforceCvQuota` are pure functions (no I/O).
// `countCvAdaptedThisMonth` reads Supabase — we mock
// `@/lib/supabase/server` so the call shape is controlled per test.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockSupabase = {
  from: vi.fn(),
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

import {
  monthStartUtc,
  countCvAdaptedThisMonth,
  enforceCvQuota,
} from "../quota";

describe("monthStartUtc — UTC month boundary", () => {
  it("returns the ISO timestamp for the start of the current UTC month", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-21T15:42:13.123Z"));

    const start = monthStartUtc();

    expect(start).toBe("2026-07-01T00:00:00.000Z");

    vi.useRealTimers();
  });

  it("rolls over at the UTC month boundary (Jan 31 23:59 → Feb 1)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-31T23:59:59.999Z"));

    expect(monthStartUtc()).toBe("2026-01-01T00:00:00.000Z");

    vi.setSystemTime(new Date("2026-02-01T00:00:00.000Z"));

    expect(monthStartUtc()).toBe("2026-02-01T00:00:00.000Z");

    vi.useRealTimers();
  });
});

describe("enforceCvQuota — plan limits", () => {
  it("Free: allows up to (but not including) the limit, blocks when used ≥ limit", () => {
    expect(enforceCvQuota("free", 0)).toEqual({
      allowed: true,
      remaining: 3,
      limit: 3,
    });
    expect(enforceCvQuota("free", 2)).toEqual({
      allowed: true,
      remaining: 1,
      limit: 3,
    });
    expect(enforceCvQuota("free", 3)).toEqual({
      allowed: false,
      remaining: 0,
      limit: 3,
    });
  });

  it("Pro: always allowed, unlimited remaining, unlimited limit", () => {
    expect(enforceCvQuota("pro", 0)).toEqual({
      allowed: true,
      remaining: "unlimited",
      limit: "unlimited",
    });
    expect(enforceCvQuota("pro", 1_000_000)).toEqual({
      allowed: true,
      remaining: "unlimited",
      limit: "unlimited",
    });
  });

  it("Pro Plus: unlimited (locked schema slot — behaves as Pro for v1)", () => {
    expect(enforceCvQuota("pro_plus", 0)).toEqual({
      allowed: true,
      remaining: "unlimited",
      limit: "unlimited",
    });
  });

  it("Free: remaining is clamped to 0 (never negative)", () => {
    expect(enforceCvQuota("free", 99).remaining).toBe(0);
    expect(enforceCvQuota("free", 99).allowed).toBe(false);
  });
});

describe("countCvAdaptedThisMonth — Supabase delegation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function makeChain(resolved: {
    count?: number | null;
    error?: { message: string } | null;
  }) {
    const stub: Record<string, unknown> = {};
    stub.from = vi.fn(() => stub);
    stub.select = vi.fn(() => stub);
    stub.eq = vi.fn(() => stub);
    stub.gte = vi.fn(() => Promise.resolve(resolved));
    return stub as unknown as ReturnType<typeof mockSupabase.from>;
  }

  it("counts cv_adapted rows for the user since monthStartUtc", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-21T12:00:00.000Z"));
    const stub = makeChain({ count: 4, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const result = await countCvAdaptedThisMonth("user-1");

    expect(result).toBe(4);
    expect(mockSupabase.from).toHaveBeenCalledWith("user_engagement");
    expect(stub.select).toHaveBeenCalledWith("id", {
      count: "exact",
      head: true,
    });
    expect(stub.eq).toHaveBeenCalledWith("user_id", "user-1");
    expect(stub.eq).toHaveBeenCalledWith("event_type", "cv_adapted");
    expect(stub.gte).toHaveBeenCalledWith(
      "created_at",
      "2026-07-01T00:00:00.000Z",
    );
    vi.useRealTimers();
  });

  it("returns 0 when Supabase reports an error (graceful degradation)", async () => {
    const stub = makeChain({
      count: null,
      error: { message: "permission denied for table user_engagement" },
    });
    mockSupabase.from.mockReturnValue(stub);

    // Suppress the expected console.error noise.
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const result = await countCvAdaptedThisMonth("user-1");
    errSpy.mockRestore();

    expect(result).toBe(0);
  });

  it("returns 0 when count is null (no events this month)", async () => {
    const stub = makeChain({ count: null, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const result = await countCvAdaptedThisMonth("user-1");

    expect(result).toBe(0);
  });
});