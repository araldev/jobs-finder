/**
 * Tests for REQ-PDPRSC-002 (Dashboard RSC streaming) — the
 * dashboard route, its RSC leaf components, and its single
 * client island (`EngagementStatsRow`) MUST be structured so
 * the LCP date arrives in the server HTML, not after a client
 * JS fetch.
 *
 * The contract verified here is **structural** (file-content
 * scans), matching the batch-1 convention for SCN-005-B
 * (file-content instead of `renderToString`, because async
 * server components suspend and `renderToStaticMarkup` cannot
 * complete them under React 19). Each assertion pins a single
 * contract that would regress silently if a future refactor
 * re-introduced client-side data fetching.
 *
 *   - SCN-PDPRSC-002-B: `dashboard/page.tsx` has NO `"use client"`
 *     directive (the page is an async RSC).
 *   - SCN-PDPRSC-002-C: `StatsCardsRow` + `RightSidebar` are
 *     async RSC (no `"use client"`) AND they import from the
 *     server-only `supabase-queries` module (which carries
 *     `import "server-only"`).
 *   - EngagementStatsRow is the lone client island — it MUST
 *     keep `"use client"` so `useOpenedJobs()` + `useFavorites()` +
 *     `useCVAdapted()` (localStorage-backed hooks) can run.
 *
 * Behavioral tests for the actual server-rendered HTML live in
 * `StatsCardsRow.server.test.tsx` (import-graph + structural
 * checks for the LCP text path).
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const DASHBOARD_PAGE_PATH = path.resolve(
  __dirname,
  "..",
  "page.tsx",
);
const STATS_CARDS_ROW_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "components",
  "dashboard",
  "StatsCardsRow.tsx",
);
const RIGHT_SIDEBAR_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "components",
  "dashboard",
  "RightSidebar.tsx",
);
const ENGAGEMENT_STATS_ROW_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "components",
  "dashboard",
  "EngagementStatsRow.tsx",
);

function firstNonCommentNonBlankLine(source: string): string | undefined {
  return source
    .split("\n")
    .map((line) => line.trim())
    .find(
      (line) =>
        line.length > 0 &&
        !line.startsWith("//") &&
        !line.startsWith("/*") &&
        !line.startsWith("*"),
    );
}

describe("dashboard/page.tsx — SCN-PDPRSC-002-B (no 'use client')", () => {
  const source = fs.readFileSync(DASHBOARD_PAGE_PATH, "utf8");

  it("first non-comment, non-blank line is NOT 'use client'", () => {
    // The page MUST be a React Server Component (no client-side
    // directive). Client components cannot `await` data on the
    // server, so the LCP date would have to wait for hydration.
    const first = firstNonCommentNonBlankLine(source);
    expect(first).toBeDefined();
    expect(first).not.toBe(`"use client";`);
    expect(first).not.toBe(`'use client';`);
  });
});

describe("StatsCardsRow — SCN-PDPRSC-002-C (RSC + server-only supabase-queries)", () => {
  const source = fs.readFileSync(STATS_CARDS_ROW_PATH, "utf8");

  it("first non-comment, non-blank line is NOT 'use client'", () => {
    // StatsCardsRow awaits fetchDashboardStats() server-side; the
    // server fetcher is the only place stats can land in the LCP
    // HTML payload. Re-introducing "use client" would force a
    // client-side fetch and undo the perf win.
    const first = firstNonCommentNonBlankLine(source);
    expect(first).toBeDefined();
    expect(first).not.toBe(`"use client";`);
    expect(first).not.toBe(`'use client';`);
  });

  it("imports from @/lib/supabase-queries (which carries 'import \"server-only\"')", () => {
    // The server fetcher lives in @/lib/supabase-queries.ts:1
    // with `import "server-only"` — that import acts as a
    // build-time gate that fails any client import. Pinning
    // this here proves StatsCardsRow reads the server fetcher
    // (NOT a client hook).
    expect(source).toMatch(
      /from\s*["']@\/lib\/supabase-queries["']/,
    );
  });
});

describe("RightSidebar — SCN-PDPRSC-002-C (RSC + server-only supabase-queries)", () => {
  const source = fs.readFileSync(RIGHT_SIDEBAR_PATH, "utf8");

  it("first non-comment, non-blank line is NOT 'use client'", () => {
    const first = firstNonCommentNonBlankLine(source);
    expect(first).toBeDefined();
    expect(first).not.toBe(`"use client";`);
    expect(first).not.toBe(`'use client';`);
  });

  it("imports from @/lib/supabase-queries", () => {
    expect(source).toMatch(/from\s*["']@\/lib\/supabase-queries["']/);
  });
});

describe("RightSidebar — SCN-PDPRSC-002-D (locale passed as prop, not hardcoded)", () => {
  const source = fs.readFileSync(RIGHT_SIDEBAR_PATH, "utf8");

  it("accepts a locale as a destructured function parameter", () => {
    // The function signature must destructure `locale` from props.
    // A server component cannot call `useLocale()` — the locale
    // must arrive as a prop from the page (which has `params.locale`).
    expect(source).toMatch(/\blocale\b.*:/);
    expect(source).toMatch(/RightSidebar\(\s*\{/);
  });

  it("does NOT hardcode a literal string locale in formatRelativeDate calls", () => {
    // Strip comments — the docstring explains the historical
    // "es" hardcode. Only code references count as regression.
    const codeOnly = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    expect(codeOnly).not.toMatch(
      /formatRelativeDate\(\s*[^,]+,\s*["']es["']\s*\)/,
    );
  });
});

describe("dashboard/page.tsx — SCN-PDPRSC-002-E (passes locale prop to RightSidebar)", () => {
  const source = fs.readFileSync(DASHBOARD_PAGE_PATH, "utf8");

  it("renders <RightSidebar> with a locale prop", () => {
    // The page must pass the locale (from params) to RightSidebar
    // so it can format dates in the user's language.
    expect(source).toMatch(/<RightSidebar\s+locale=/);
  });

  it("receives locale from page params", () => {
    // Since localePrefix: 'never', the locale arrives via the
    // [locale] dynamic route segment — the page must destructure
    // `locale` from `params` (a Promise in Next.js 15).
    expect(source).toMatch(/\bparams\b/);
  });
});

describe("EngagementStatsRow — client island (edge case)", () => {
  it("file exists and starts with 'use client' (it uses localStorage-backed hooks)", () => {
    // EngagementStatsRow is the lone client island under the
    // dashboard. Its hooks (`useOpenedJobs` from `chat-storage`,
    // `useFavorites`, `useCVAdapted`) all read `localStorage`,
    // which does not exist server-side. So this file MUST stay
    // `"use client"` while the rest of the dashboard migrates
    // to RSC.
    expect(fs.existsSync(ENGAGEMENT_STATS_ROW_PATH)).toBe(true);
    const source = fs.readFileSync(ENGAGEMENT_STATS_ROW_PATH, "utf8");
    const first = firstNonCommentNonBlankLine(source);
    expect(first).toBe(`"use client";`);
  });
});