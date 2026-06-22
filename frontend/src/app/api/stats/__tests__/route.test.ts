/**
 * Tests for REQ-PDPRSC-003 (frontend half) — `GET /api/stats`
 * proxies the new backend `/jobs/stats` endpoint in ONE outbound
 * fetch (down from 6 fetches via the legacy 3-waterfall handler).
 *
 * The route handler MUST:
 *   1. Call `fetchDashboardStats()` exactly once (no waterfall).
 *   2. Return the response as a `DashboardStats` JSON shape
 *      (SCN-PDPRSC-003-E backward compat — the existing
 *      `useStats` client hook + `StatsCardsRow` component keep
 *      working without changes).
 *
 * The 2 tests:
 *   - `test_calls_fetchDashboardStats_once` — mocks the
 *     `fetchDashboardStats` import and asserts the spy was
 *     invoked exactly once with no args.
 *   - `test_response_matches_DashboardStats_shape` — asserts
 *     the response body is structurally a `DashboardStats`
 *     (TypeScript compiles + all 5 fields present).
 *
 * The test mocks `@/lib/api-client` at the module level via
 * `vi.mock` so the route handler uses the mock instead of the
 * real `fetch`. The mock is hoisted above the dynamic `import()`
 * of the route so vitest rewires the module references.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock `@/lib/api-client` BEFORE importing the route so the
// route handler's `import { fetchDashboardStats } from "@/lib/api-client"`
// resolves to the mocked export. The mock factory returns a
// resolved promise with a known shape so the test can assert
// the route handler forwards it byte-for-byte.
vi.mock("@/lib/api-client", () => ({
  fetchDashboardStats: vi.fn(async () => ({
    total_jobs: 42,
    jobs_today: 5,
    active_platforms: 3,
    last_sync: "2026-06-22T10:00:00Z",
    platform_distribution: {
      linkedin: 20,
      indeed: 15,
      infojobs: 7,
    },
  })),
}));

import { fetchDashboardStats } from "@/lib/api-client";

beforeEach(() => {
  vi.mocked(fetchDashboardStats).mockClear();
});

describe("GET /api/stats — REQ-PDPRSC-003 (proxy backend /jobs/stats)", () => {
  it("calls fetchDashboardStats exactly once", async () => {
    // Dynamic import so the mock is applied.
    const { GET } = await import("../route");
    const response = await GET();

    // Exactly one outbound call (the new contract: 1 fetch, not 6).
    expect(fetchDashboardStats).toHaveBeenCalledTimes(1);
    expect(fetchDashboardStats).toHaveBeenCalledWith();

    // The route handler forwards the payload — status 200 + the
    // mocked shape.
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.total_jobs).toBe(42);
    expect(body.jobs_today).toBe(5);
    expect(body.active_platforms).toBe(3);
    expect(body.last_sync).toBe("2026-06-22T10:00:00Z");
    expect(body.platform_distribution).toEqual({
      linkedin: 20,
      indeed: 15,
      infojobs: 7,
    });
  });

  it("response body matches the DashboardStats type (SCN-PDPRSC-003-E)", async () => {
    const { GET } = await import("../route");
    const response = await GET();

    expect(response.status).toBe(200);
    const body = await response.json();

    // All 5 fields present + types match the DashboardStats
    // contract in `frontend/src/types/stats.ts`. A drift between
    // the route handler and the type surfaces here as a
    // `missing field` assertion failure.
    expect(typeof body.total_jobs).toBe("number");
    expect(typeof body.jobs_today).toBe("number");
    expect(typeof body.active_platforms).toBe("number");
    // `last_sync` is `string | null` — the mocked value is a
    // string but the contract allows null (the graceful-
    // degradation path).
    expect(["string", "object"]).toContain(typeof body.last_sync);
    if (body.last_sync !== null) {
      expect(typeof body.last_sync).toBe("string");
    }
    expect(typeof body.platform_distribution).toBe("object");
    expect(body.platform_distribution).not.toBeNull();
    // Every per-source count is a number.
    for (const source of ["linkedin", "indeed", "infojobs"] as const) {
      expect(typeof body.platform_distribution[source]).toBe("number");
    }
  });
});
