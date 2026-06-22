/**
 * Shared queryKey helpers for the `useJobs` + `useJobsInfinite`
 * hook pair (REQ-CACHEUX-003).
 *
 * Background: the perf-frontend-cache-ux audit found that the two
 * hooks had DIFFERENT queryKey shapes for what is effectively the
 * same underlying `/api/jobs` fetch. That prevented the Next.js
 * Data Cache (L2, REQ-CACHEUX-001) from deduping repeat calls
 * across the sidebar (`useJobs({limit:5})`) and the grid
 * (`useJobsInfinite({pageSize:20})`).
 *
 * The shared prefix `["jobs", "list", sharedArgs]` lets L2 dedupe.
 * The mode discriminator (`"single"` vs `"infinite"`) keeps the
 * React Query entries distinct at L3 — the two hooks return
 * DIFFERENT data shapes (flat `{items, total, ...}` vs accumulated
 * `{pages: [...]}`), so they cannot share an L3 entry.
 *
 * `sharedArgs` is a JSON serialization of the 3 shared inputs
 * (q, location, sources). The keys are sorted alphabetically before
 * serialization so `JSON.stringify({q: "x", location: "y"})` and
 * `JSON.stringify({location: "y", q: "x"})` produce identical
 * strings. `undefined` values are normalized to `null` (consistent
 * cache keys across optional args).
 */

export interface SharedJobsArgs {
  readonly q?: string;
  readonly location?: string;
  readonly sources?: string;
}

export function sharedJobsArgs(args: SharedJobsArgs): string {
  return JSON.stringify({
    q: args.q ?? null,
    location: args.location ?? null,
    sources: args.sources ?? null,
  });
}
