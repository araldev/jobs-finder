// Tests for GET /api/cv/count.
//
// The route reads the `user_engagement` table directly from Supabase
// (replaces the previous Python backend proxy). As of the
// user-roles-and-billing change, the contract switched from a
// DAILY count (`total_today`) to a MONTHLY count (`total_this_month`)
// — D5 from the spec requires 3 CVs per UTC month for Free, not per
// day. The filter on the Supabase query now uses `monthStartUtc()`
// instead of the UTC midnight of the current day.
//
// We mock `@/lib/supabase/server` to return a chainable query-builder
// stub whose `.then`-resolution shape mirrors PostgREST:
// `{ count, error }`. The mock pattern is the same as
// `supabase-queries.test.ts`.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("server-only", () => ({}));

interface CountStub {
  from: ReturnType<typeof vi.fn>;
  select: ReturnType<typeof vi.fn>;
  eq: ReturnType<typeof vi.fn>;
  gte: ReturnType<typeof vi.fn>;
  then: Promise<unknown>["then"];
}

function makeCountStub(
  resolved: { count?: number | null; error?: { message: string } | null },
): CountStub {
  const stub: Partial<CountStub> = {};
  const chainable = () => stub as CountStub;
  stub.from = vi.fn(chainable);
  stub.select = vi.fn(chainable);
  stub.eq = vi.fn(chainable);
  stub.gte = vi.fn(chainable);
  stub.then = Promise.resolve(resolved).then.bind(Promise.resolve(resolved));
  return stub as CountStub;
}

const mockAuth = {
  getSession: vi.fn(),
};

const mockSupabase = {
  from: vi.fn(),
  auth: mockAuth,
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

import { GET } from "../route";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/cv/count", () => {
  it("returns total_this_month=0 when the user is not authenticated", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: { session: null },
      error: null,
    });

    const res = await GET(new Request("http://localhost/api/cv/count") as never);

    expect(res.status).toBe(200);
    const body = (await res.json()) as { total_this_month: number };
    expect(body.total_this_month).toBe(0);
    // No Supabase query when there's no session — privacy + cost.
    expect(mockSupabase.from).not.toHaveBeenCalled();
  });

  it("queries user_engagement filtered by event_type and the UTC month-start timestamp", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: {
        session: { user: { id: "user-1" } },
      },
      error: null,
    });
    const stub = makeCountStub({ count: 3, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const res = await GET(new Request("http://localhost/api/cv/count") as never);

    expect(res.status).toBe(200);
    expect(mockSupabase.from).toHaveBeenCalledWith("user_engagement");
    expect(stub.select).toHaveBeenCalledWith("id", {
      count: "exact",
      head: true,
    });
    expect(stub.eq).toHaveBeenCalledWith("event_type", "cv_adapted");
    // The filter is now a full ISO 8601 timestamp (the UTC month
    // start), not a YYYY-MM-DD date. The shape is fixed by
    // monthStartUtc() and the test only needs to assert that the
    // value parses as a valid UTC month-start.
    expect(stub.gte).toHaveBeenCalledWith(
      "created_at",
      expect.stringMatching(/^\d{4}-\d{2}-01T00:00:00\.000Z$/),
    );

    const body = (await res.json()) as { total_this_month: number };
    expect(body.total_this_month).toBe(3);
  });

  it("returns total_this_month=0 on Supabase error (graceful degradation)", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: {
        session: { user: { id: "user-1" } },
      },
      error: null,
    });
    const stub = makeCountStub({
      count: null,
      error: { message: "permission denied for table user_engagement" },
    });
    mockSupabase.from.mockReturnValue(stub);

    const res = await GET(new Request("http://localhost/api/cv/count") as never);

    expect(res.status).toBe(200);
    const body = (await res.json()) as { total_this_month: number };
    expect(body.total_this_month).toBe(0);
  });

  it("returns total_this_month=0 when count is null but no error", async () => {
    mockAuth.getSession.mockResolvedValueOnce({
      data: {
        session: { user: { id: "user-1" } },
      },
      error: null,
    });
    const stub = makeCountStub({ count: null, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const res = await GET(new Request("http://localhost/api/cv/count") as never);

    expect(res.status).toBe(200);
    const body = (await res.json()) as { total_this_month: number };
    expect(body.total_this_month).toBe(0);
  });
});