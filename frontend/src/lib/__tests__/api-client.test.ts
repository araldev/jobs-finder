import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Tests for REQ-CACHEUX-001 — `fetchJobsHistory` and
 * `fetchSchedulerStatus` MUST pass `next: { revalidate: 60, tags: [...] }`
 * so the Next.js Data Cache (L2) can dedupe repeat calls within 60s.
 *
 * Without these options, every fetch call bypasses the L2 cache and
 * every dashboard mount costs one backend `/jobs/history` round trip
 * (the bug surfaced in the perf-frontend-cache-ux audit).
 *
 * Implementation note: `api-client.ts` imports `"server-only"` so it
 * cannot be evaluated in a client test environment. We mock
 * `server-only` to a no-op so the module loads under vitest/jsdom,
 * then spy on the global `fetch` to assert the `next` config the
 * production code forwards.
 */

vi.mock("server-only", () => ({}));

import {
  fetchDashboardStats,
  fetchJobsHistory,
  fetchSchedulerStatus,
} from "../api-client";

const ORIGINAL_FETCH = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn(async () => {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = ORIGINAL_FETCH;
  vi.restoreAllMocks();
});

describe("fetchJobsHistory — revalidate:60 + tag (REQ-CACHEUX-001)", () => {
  it("sets next.revalidate to 60 with tag jobs-history on /jobs/history fetch", async () => {
    await fetchJobsHistory({});

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const call = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0];
    const url = call?.[0];
    const opts = call?.[1] as { next?: { revalidate?: number; tags?: string[] } };

    // URL hits the /jobs/history endpoint.
    expect(String(url)).toContain("/jobs/history");
    // The next.revalidate is set to 60s (L2 cache TTL).
    expect(opts.next?.revalidate).toBe(60);
    // The next.tags contains the canonical jobs-history tag
    // (spec arch decision #2 — these are the canonical
    // invalidation keys for future revalidateTag() calls).
    expect(opts.next?.tags).toEqual(["jobs-history"]);
  });
});

describe("fetchSchedulerStatus — revalidate:60 + tag (REQ-CACHEUX-001)", () => {
  it("sets next.revalidate to 60 with tag scheduler-status on /scheduler/status fetch", async () => {
    await fetchSchedulerStatus();

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const call = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0];
    const url = call?.[0];
    const opts = call?.[1] as { next?: { revalidate?: number; tags?: string[] } };

    expect(String(url)).toContain("/scheduler/status");
    expect(opts.next?.revalidate).toBe(60);
    expect(opts.next?.tags).toEqual(["scheduler-status"]);
  });
});

describe("fetchDashboardStats — revalidate:60 + tag (REQ-PDPRSC-003)", () => {
  it("sets next.revalidate to 60 with tag jobs-stats on /jobs/stats fetch", async () => {
    await fetchDashboardStats();

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const call = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0];
    const url = call?.[0];
    const opts = call?.[1] as { next?: { revalidate?: number; tags?: string[] } };

    // URL hits the new consolidated /jobs/stats endpoint.
    expect(String(url)).toContain("/jobs/stats");
    // The next.revalidate is set to 60s (L2 cache TTL) — same
    // env knob as the per-source fetcher.
    expect(opts.next?.revalidate).toBe(60);
    // The next.tags contains the canonical jobs-stats tag.
    expect(opts.next?.tags).toEqual(["jobs-stats"]);
  });
});
