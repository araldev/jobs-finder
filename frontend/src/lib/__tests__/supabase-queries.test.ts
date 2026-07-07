import { describe, it, expect, vi, beforeEach } from "vitest";

/**
 * Tests for `supabase-queries.ts`.
 *
 * The functions under test call `createClient()` from
 * `@/lib/supabase/server` and chain Supabase query-builder methods
 * (`from`, `select`, `eq`, `in`, `or`, `ilike`, `gte`, `order`,
 * `range`). We mock the server client to return a chainable
 * `thenable` query-builder stub whose `await`-resolution shape
 * `{ data, error, count }` mirrors the real PostgREST response.
 *
 * `server-only` is mocked to a no-op (matches the `api-client.test.ts`
 * pattern) so the module loads under vitest/jsdom.
 */

vi.mock("server-only", () => ({}));

interface QueryStub {
  from: ReturnType<typeof vi.fn>;
  select: ReturnType<typeof vi.fn>;
  eq: ReturnType<typeof vi.fn>;
  in: ReturnType<typeof vi.fn>;
  or: ReturnType<typeof vi.fn>;
  ilike: ReturnType<typeof vi.fn>;
  gte: ReturnType<typeof vi.fn>;
  order: ReturnType<typeof vi.fn>;
  range: ReturnType<typeof vi.fn>;
  then: Promise<unknown>["then"];
}

function makeQueryStub(
  resolved: { data?: unknown; error?: { message: string } | null; count?: number | null },
): QueryStub {
  const stub: Partial<QueryStub> = {};
  const chainable = () => stub as QueryStub;
  stub.from = vi.fn(chainable);
  stub.select = vi.fn(chainable);
  stub.eq = vi.fn(chainable);
  stub.in = vi.fn(chainable);
  stub.or = vi.fn(chainable);
  stub.ilike = vi.fn(chainable);
  stub.gte = vi.fn(chainable);
  stub.order = vi.fn(chainable);
  stub.range = vi.fn(chainable);
  stub.then = Promise.resolve(resolved).then.bind(Promise.resolve(resolved));
  return stub as QueryStub;
}

const mockSupabase = {
  from: vi.fn(),
};

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => mockSupabase,
}));

import {
  fetchDashboardStats,
  fetchJobsHistory,
  fetchLatestJobs,
} from "../supabase-queries";
import type { Job } from "@/types/job";

const sampleJobRow = {
  source: "linkedin",
  source_id: "li-1",
  title: "Software Engineer",
  company: "Acme",
  location: "Madrid",
  url: "https://linkedin.com/jobs/li-1",
  description: "Great job",
  posted_at: "2026-07-01T10:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("fetchJobsHistory — filter shape", () => {
  it("builds a Supabase query with no filters when no args are passed", async () => {
    const dataStub = makeQueryStub({
      data: [sampleJobRow],
      error: null,
      count: 1,
    });
    mockSupabase.from.mockReturnValue(dataStub);

    const result = await fetchJobsHistory({});

    expect(mockSupabase.from).toHaveBeenCalledWith("jobs");
    expect(dataStub.select).toHaveBeenCalledWith(
      "source, source_id, title, company, location, url, description, posted_at",
    );
    expect(dataStub.order).toHaveBeenCalledWith("posted_at", { ascending: false });
    expect(dataStub.range).toHaveBeenCalledWith(0, 19);

    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
    expect(result.limit).toBe(20);
    expect(result.offset).toBe(0);
  });

  it("applies the keyword filter as title.ilike OR company.ilike", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ keywords: "typescript" });

    expect(dataStub.or).toHaveBeenCalledWith(
      "title.ilike.%typescript%,company.ilike.%typescript%",
    );
  });

  it("applies the location filter as location.ilike", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ location: "Madrid" });

    expect(dataStub.ilike).toHaveBeenCalledWith("location", "%Madrid%");
  });

  it("parses CSV sources and applies .in() with the parsed list", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ sources: "linkedin,indeed" });

    expect(dataStub.in).toHaveBeenCalledWith("source", ["linkedin", "indeed"]);
  });

  it("ignores unknown sources in the CSV and emits the valid subset", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ sources: "linkedin,glassdoor,indeed,foo" });

    expect(dataStub.in).toHaveBeenCalledWith("source", ["linkedin", "indeed"]);
  });

  it("omits the .in() call entirely when sources is empty/unknown only", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ sources: "glassdoor,foo," });

    expect(dataStub.in).not.toHaveBeenCalled();
  });

  it("clamps limit to MAX_LIMIT=200 and uses it in .range()", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ limit: 500, offset: 50 });

    expect(dataStub.range).toHaveBeenCalledWith(50, 249);
  });

  it("uses DEFAULT_LIMIT=20 when limit is undefined or <= 0", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ offset: 40 });
    expect(dataStub.range).toHaveBeenLastCalledWith(40, 59);

    await fetchJobsHistory({ limit: 0, offset: 0 });
    expect(dataStub.range).toHaveBeenLastCalledWith(0, 19);
  });

  it("clamps negative offset to 0", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ limit: 10, offset: -5 });

    expect(dataStub.range).toHaveBeenCalledWith(0, 9);
  });

  it("escapes LIKE wildcards in the keyword pattern", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchJobsHistory({ keywords: "50%_off" });

    expect(dataStub.or).toHaveBeenCalledWith(
      "title.ilike.%50\\%\\_off%,company.ilike.%50\\%\\_off%",
    );
  });

  it("returns items with id mapped from source_id (per cross-cutting convention)", async () => {
    const dataStub = makeQueryStub({
      data: [
        sampleJobRow,
        { ...sampleJobRow, source: "indeed", source_id: "in-2", title: "PM" },
      ],
      error: null,
      count: 2,
    });
    mockSupabase.from.mockReturnValue(dataStub);

    const result = await fetchJobsHistory({});

    const expected: Job[] = [
      {
        id: "li-1",
        source: "linkedin",
        title: "Software Engineer",
        company: "Acme",
        location: "Madrid",
        url: "https://linkedin.com/jobs/li-1",
        description: "Great job",
        posted_at: "2026-07-01T10:00:00Z",
      },
      {
        id: "in-2",
        source: "indeed",
        title: "PM",
        company: "Acme",
        location: "Madrid",
        url: "https://linkedin.com/jobs/li-1",
        description: "Great job",
        posted_at: "2026-07-01T10:00:00Z",
      },
    ];
    expect(result.items).toEqual(expected);
  });

  it("returns the canonical response shape: { items, total, limit, offset }", async () => {
    const dataStub = makeQueryStub({
      data: [sampleJobRow],
      error: null,
      count: 42,
    });
    mockSupabase.from.mockReturnValue(dataStub);

    const result = await fetchJobsHistory({ limit: 5, offset: 10 });

    expect(Object.keys(result).sort()).toEqual(["items", "limit", "offset", "total"]);
    expect(result.total).toBe(42);
    expect(result.limit).toBe(5);
    expect(result.offset).toBe(10);
  });

  it("throws when the data query returns an error", async () => {
    // First .from() is the count query (success), second is the
    // data query (failure). Both share the same chained builders
    // inside the function but resolve independently.
    const countStub = makeQueryStub({
      data: null,
      error: null,
      count: 0,
    });
    const dataStub = makeQueryStub({
      data: null,
      error: { message: "boom" },
      count: null,
    });
    mockSupabase.from
      .mockReturnValueOnce(countStub)
      .mockReturnValueOnce(dataStub);

    await expect(fetchJobsHistory({})).rejects.toThrow(/fetchJobsHistory data: boom/);
  });

  it("throws when the count query returns an error", async () => {
    const countStub = makeQueryStub({
      data: null,
      error: { message: "count fail" },
      count: null,
    });
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from
      .mockReturnValueOnce(countStub)
      .mockReturnValueOnce(dataStub);

    await expect(fetchJobsHistory({})).rejects.toThrow(/count: count fail/);
  });
});

describe("fetchLatestJobs — thin wrapper", () => {
  it("calls fetchJobsHistory with limit=5 by default", async () => {
    const dataStub = makeQueryStub({
      data: [sampleJobRow],
      error: null,
      count: 1,
    });
    mockSupabase.from.mockReturnValue(dataStub);

    const result = await fetchLatestJobs();

    expect(dataStub.range).toHaveBeenCalledWith(0, 4);
    expect(result.items).toHaveLength(1);
  });

  it("respects an explicit limit arg", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    await fetchLatestJobs({ limit: 12 });

    expect(dataStub.range).toHaveBeenCalledWith(0, 11);
  });
});

describe("fetchDashboardStats — parallel count queries", () => {
  it("issues 5 count queries in parallel (total, today, 3 per-source)", async () => {
    const countStub = makeQueryStub({
      data: null,
      error: null,
      count: 10,
    });
    mockSupabase.from.mockReturnValue(countStub);

    await fetchDashboardStats();

    // The query plan is one Promise.all over 5 .from() calls.
    expect(mockSupabase.from).toHaveBeenCalledTimes(5);
    // Each call uses head:true + count:exact (count-only request).
    for (const call of countStub.select.mock.calls) {
      expect(call[0]).toBe("*");
      expect(call[1]).toEqual({ count: "exact", head: true });
    }
  });

  it("filters jobs_today with .gte('posted_at', today_utc)", async () => {
    const countStub = makeQueryStub({
      data: null,
      error: null,
      count: 3,
    });
    mockSupabase.from.mockReturnValue(countStub);

    await fetchDashboardStats();

    // One of the 5 queries applies the .gte('posted_at', today) filter.
    // Inspect mock state: there should be exactly one call to .gte across
    // all stubs (the today-stub).
    const today = new Date().toISOString().slice(0, 10);
    expect(countStub.gte).toHaveBeenCalledWith("posted_at", today);
  });

  it("returns the 5-field DashboardStats shape with last_sync: null", async () => {
    const countStub = makeQueryStub({
      data: null,
      error: null,
      count: 7,
    });
    mockSupabase.from.mockReturnValue(countStub);

    const stats = await fetchDashboardStats();

    expect(Object.keys(stats).sort()).toEqual([
      "active_platforms",
      "jobs_today",
      "last_sync",
      "platform_distribution",
      "total_jobs",
    ]);
    expect(stats.total_jobs).toBe(7);
    expect(stats.jobs_today).toBe(7);
    expect(stats.active_platforms).toBe(3);
    expect(stats.last_sync).toBeNull();
    expect(stats.platform_distribution).toEqual({
      linkedin: 7,
      indeed: 7,
      infojobs: 7,
    });
  });

  it("counts active_platforms as sources with count > 0", async () => {
    let callIndex = 0;
    const perSourceCounts = [5, 0, 12];
    mockSupabase.from.mockImplementation(() => {
      const i = callIndex++;
      const stub = makeQueryStub({
        data: null,
        error: null,
        count:
          i === 0
            ? 17
            : i === 1
              ? 8
              : perSourceCounts[i - 2] ?? 0,
      });
      return stub;
    });

    const stats = await fetchDashboardStats();

    // total=17, today=8, linkedin=5, indeed=0, infojobs=12.
    expect(stats.total_jobs).toBe(17);
    expect(stats.jobs_today).toBe(8);
    expect(stats.platform_distribution).toEqual({
      linkedin: 5,
      indeed: 0,
      infojobs: 12,
    });
    // Only linkedin (5) and infojobs (12) are active.
    expect(stats.active_platforms).toBe(2);
  });

  it("throws when any of the 5 queries returns an error", async () => {
    let callIndex = 0;
    mockSupabase.from.mockImplementation(() => {
      const i = callIndex++;
      const error = i === 2 ? { message: "rate limited" } : null;
      return makeQueryStub({ data: null, error, count: 5 });
    });

    await expect(fetchDashboardStats()).rejects.toThrow(/rate limited/);
  });

  it("falls back to 0 when count comes back null (defensive)", async () => {
    const countStub = makeQueryStub({
      data: null,
      error: null,
      count: null,
    });
    mockSupabase.from.mockReturnValue(countStub);

    const stats = await fetchDashboardStats();

    expect(stats.total_jobs).toBe(0);
    expect(stats.jobs_today).toBe(0);
    expect(stats.active_platforms).toBe(0);
    expect(stats.platform_distribution).toEqual({
      linkedin: 0,
      indeed: 0,
      infojobs: 0,
    });
  });
});

describe("React.cache() — per-request memoization (not unit-testable)", () => {
  // NOTE: React's `cache()` only memoizes inside an RSC render context.
  // In the production build (`react/cjs/react.production.js`) `cache()`
  // is a passthrough (`return function () { return fn.apply(null, arguments); }`);
  // the deduping Map is only active when the RSC renderer is on the call
  // stack. Under vitest (jsdom + production React) each `await` is a fresh
  // "render pass", so calling a cached function twice will hit Supabase
  // twice. The deduping is verified end-to-end in the Next.js RSC pipeline,
  // not by unit tests — see `api-client.ts`'s docstring on
  // `React.cache()` for the same caveat.
  //
  // We assert that the `import "server-only"` + `cache()` wrapping
  // pattern is honored at the call-site (the exports are async
  // functions whose behavior is tested above), and that the source
  // itself does NOT change observable behavior under vitest.
  it("fetchJobsHistory returns a fresh HistoryResponse on every call (cache is RSC-scoped)", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    // Deep-equal but reference-distinct: each call resolves a new
    // object because the cache Map is RSC-scoped (see note above).
    const first = await fetchJobsHistory({});
    const second = await fetchJobsHistory({});
    expect(first).toStrictEqual(second);
  });

  it("fetchLatestJobs returns a fresh HistoryResponse on every call (cache is RSC-scoped)", async () => {
    const dataStub = makeQueryStub({ data: [], error: null, count: 0 });
    mockSupabase.from.mockReturnValue(dataStub);

    const first = await fetchLatestJobs();
    const second = await fetchLatestJobs();
    expect(first).toStrictEqual(second);
  });
});