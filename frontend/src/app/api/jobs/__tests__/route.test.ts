/**
 * Tests for the `/api/jobs/[id]` route handler after Phase 2 sub-task 2.
 *
 * Pre-Phase-2 this handler proxied `${BACKEND_URL}/jobs/history/by-id/{id}`
 * on the Python backend. Post-Phase-2 it reads directly from the
 * `jobs` Supabase table via `createClient()` from
 * `@/lib/supabase/server`. The contract verified here:
 *
 *   1. The handler queries `from("jobs")` with the exact `source_id`
 *      column (`useJobDetail` passes the source-native id as the `[id]`
 *      route param).
 *   2. It uses `.maybeSingle()` — at most one row per `source_id`
 *      because of `UNIQUE (source, source_id)` (migration 001).
 *   3. The success response body maps `source_id → id` (the
 *      cross-cutting convention) so the `useJobDetail` hook sees
 *      a `Job` shape.
 *   4. A `null` row (no match) returns 404.
 *   5. A Supabase error returns 503 with a generic message (no leak
 *      of PostgREST internals to the client).
 *
 * Mock pattern: `vi.doMock` (not `vi.mock`) for both `server-only`
 * and `@/lib/supabase/server`. `vi.doMock` only applies to imports
 * that occur AFTER it runs. We import the route handler via
 * `await import("../[id]/route")` in `beforeAll` so the mocks are
 * in place. (The path uses `/[id]/route` explicitly because a
 * relative `../route` from this test file would resolve to the
 * sibling route at `src/app/api/jobs/route.ts` — different file.)
 */

import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import type { NextRequest } from "next/server";

interface QueryStub {
  from: ReturnType<typeof vi.fn>;
  select: ReturnType<typeof vi.fn>;
  eq: ReturnType<typeof vi.fn>;
  maybeSingle: ReturnType<typeof vi.fn>;
}

function makeQueryStub(resolved: {
  data?: unknown;
  error?: { message: string } | null;
}): QueryStub {
  const stub: Partial<QueryStub> = {};
  // Each chainable method returns the SAME stub. We deliberately do
  // NOT attach a `.then` to the stub itself — only `maybeSingle`
  // returns a Promise. This matches how the real Supabase JS client
  // behaves (the promise is only awaited at the end of the chain).
  const self = () => stub as QueryStub;
  stub.from = vi.fn(self);
  stub.select = vi.fn(self);
  stub.eq = vi.fn(self);
  stub.maybeSingle = vi.fn(() => Promise.resolve(resolved));
  return stub as QueryStub;
}

const mockSupabase = { from: vi.fn() };

// Type of the GET handler — declared manually here to avoid the
// module-resolution + type narrowing that comes from `vi.mock`
// collapsing the second parameter. Matches the signature in
// `../[id]/route.ts` byte-for-byte.
type GetHandler = (
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) => Promise<Response>;

let GET: GetHandler;

beforeAll(async () => {
  vi.doMock("server-only", () => ({}));
  vi.doMock("@/lib/supabase/server", () => ({
    createClient: async () => mockSupabase,
  }));
  // IMPORTANT: use the absolute-from-test path `../[id]/route` to
  // disambiguate from the sibling `../route` (which is the
  // `/api/jobs` collection route, not the `[id]` member route).
  const mod = (await import("../[id]/route")) as { GET: GetHandler };
  GET = mod.GET;
});

beforeEach(() => {
  vi.clearAllMocks();
});

function callGet(id: string): Promise<Response> {
  const request = new Request(
    `http://localhost/api/jobs/${id}`,
  ) as unknown as NextRequest;
  return GET(request, { params: Promise.resolve({ id }) });
}

describe("GET /api/jobs/[id] — Supabase-direct read (post-Phase-2)", () => {
  it("queries the jobs table by source_id with maybeSingle()", async () => {
    const stub = makeQueryStub({ data: sampleRow, error: null });
    mockSupabase.from.mockReturnValue(stub);

    await callGet("li-42");

    expect(mockSupabase.from).toHaveBeenCalledWith("jobs");
    expect(stub.select).toHaveBeenCalledWith(
      "source, source_id, title, company, location, url, description, posted_at",
    );
    expect(stub.eq).toHaveBeenCalledWith("source_id", "li-42");
    expect(stub.maybeSingle).toHaveBeenCalledTimes(1);
  });

  it("returns the row mapped to a Job shape (id = source_id)", async () => {
    const stub = makeQueryStub({ data: sampleRow, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const response = await callGet("li-42");
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toEqual({
      id: "li-42",
      source: "linkedin",
      title: "Senior Engineer",
      company: "Acme",
      location: "Madrid",
      url: "https://linkedin.com/jobs/li-42",
      posted_at: "2026-07-01T10:00:00Z",
      description: "Cool job",
    });
  });

  it("returns 404 when no row matches the source_id", async () => {
    const stub = makeQueryStub({ data: null, error: null });
    mockSupabase.from.mockReturnValue(stub);

    const response = await callGet("missing");
    expect(response.status).toBe(404);
    const body = await response.json();
    expect(body.error).toBe("Job not found");
  });

  it("returns 503 with a generic message on Supabase error (no leak)", async () => {
    const stub = makeQueryStub({
      data: null,
      error: { message: "internal PostgREST stack trace" },
    });
    mockSupabase.from.mockReturnValue(stub);

    const response = await callGet("li-42");
    expect(response.status).toBe(503);
    const body = await response.json();
    // Generic user-facing message — never the raw PostgREST error.
    expect(body.error).toBe("Backend unreachable");
    expect(JSON.stringify(body)).not.toContain("PostgREST");
  });
});

const sampleRow = {
  source: "linkedin",
  source_id: "li-42",
  title: "Senior Engineer",
  company: "Acme",
  location: "Madrid",
  url: "https://linkedin.com/jobs/li-42",
  description: "Cool job",
  posted_at: "2026-07-01T10:00:00Z",
};
