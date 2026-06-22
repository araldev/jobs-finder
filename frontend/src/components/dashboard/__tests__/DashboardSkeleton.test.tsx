/**
 * Tests for SCN-PDPRSC-002-D — `DashboardSkeleton` MUST match
 * the dimensions of the legacy `isLoading` skeleton in
 * `dashboard/page.tsx` so the Suspense fallback has the same
 * CLS footprint as the post-load content (design #618 R-NEW-2:
 * CLS regression guard; sdd-verify gates on CLS<0.1, current
 * baseline 0.002).
 *
 * The legacy skeleton's structural contract (file-content
 * pinned here):
 *   - 6 items (the default page size for `useJobsInfinite`).
 *   - Responsive grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`.
 *   - Each item: `h-[120px] rounded-xl skeleton-shimmer`.
 *   - `LoadingHint` rendered below the grid.
 *
 * Any future drift between `DashboardSkeleton` and these
 * dimensions risks a layout-shift regression. This file is the
 * guard.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SKELETON_PATH = path.resolve(__dirname, "..", "DashboardSkeleton.tsx");

describe("DashboardSkeleton — SCN-PDPRSC-002-D (CLS regression guard)", () => {
  const source = fs.readFileSync(SKELETON_PATH, "utf8");

  it("uses the same responsive grid as the legacy isLoading skeleton", () => {
    // CLS=0.002 baseline depends on the grid being identical
    // between the Suspense fallback and the post-load render.
    expect(source).toMatch(/grid-cols-1/);
    expect(source).toMatch(/md:grid-cols-2/);
    expect(source).toMatch(/lg:grid-cols-3/);
  });

  it("renders exactly 6 skeleton items (default pageSize)", () => {
    // The legacy skeleton's count is `length: 6`. Match it.
    expect(source).toMatch(/length:\s*6/);
  });

  it("each skeleton item uses h-[120px] rounded-xl skeleton-shimmer", () => {
    // Same per-item dimensions as the legacy. `h-[120px]` is
    // the magic number — drift here shifts the row height and
    // pops CLS.
    expect(source).toMatch(/h-\[120px\]/);
    expect(source).toMatch(/rounded-xl/);
    expect(source).toMatch(/skeleton-shimmer/);
  });

  it("renders <LoadingHint /> below the grid (matches legacy)", () => {
    // The legacy skeleton also renders <LoadingHint />. Keep
    // the fallback identical.
    expect(source).toMatch(/<LoadingHint\b/);
  });
});