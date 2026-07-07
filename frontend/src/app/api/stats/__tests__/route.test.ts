/**
 * Tests for the `/api/stats` route handler after Phase 2
 * sub-task 2 — the handler reads dashboard stats directly
 * from Supabase via `fetchDashboardStats()` (no backend
 * proxy needed).
 *
 * Contract preserved from REQ-PDPRSC-003:
 *   1. The route handler calls `fetchDashboardStats()` exactly
 *      once (no waterfall).
 *   2. The response body is a `DashboardStats` JSON shape
 *      (the existing `useStats` hook + `StatsCardsRow` component
 *      keep working without changes).
 *
 * The test mocks `@/lib/supabase-queries` at the module level
 * via `vi.mock` so the route handler uses the mock instead of
 * the real Supabase client. The mock is hoisted above the
 * dynamic `import()` of the route so vitest rewires the
 * module references.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock `@/lib/supabase-queries` BEFORE importing the route so
// the route handler's
// `import { fetchDashboardStats } from "@/lib/supabase-queries"`
// resolves to the mocked export. The mock factory returns a
// resolved promise with a known shape so the test can assert
// the route handler forwards it byte-for-byte.
vi.mock("@/lib/supabase-queries", () => ({
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

import { fetchDashboardStats } from "@/lib/supabase-queries";

beforeEach(() => {
  vi.mocked(fetchDashboardStats).mockClear();
});

describe("GET /api/stats — Supabase-direct read (post-Phase-2)", () => {
  it("calls fetchDashboardStats exactly once", async () => {
    // Dynamic import so the mock is applied.
    const { GET } = await import("../route");
    const response = await GET();

    // Exactly one logical call (the new contract: 5 parallel
    // count queries inside the fetcher, but ONE call from the
    // route handler's perspective).
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

  it("response body matches the DashboardStats type", async () => {
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
