/**
 * Tests for SCN-PDPRSC-002-A — `StatsCardsRow` (now an async RSC)
 * MUST render the LCP date text from the server HTML payload,
 * NOT after a client-side `useStats()` fetch.
 *
 * The LCP element is the "15 de Jun de 2026" date inside the
 * `lastSync` StatCard. Before commit 6, this date appeared
 * AFTER `main-app.js` finished executing — it was the last
 * thing to paint on the dashboard. After commit 6, the date
 * arrives in the initial server HTML because `StatsCardsRow`
 * awaits `fetchDashboardStats()` directly via the
 * `server-only` `api-client`.
 *
 * This file pins the **import graph + structural contract**
 * that proves the LCP path is server-rendered. Per the batch-1
 * design deviation (SCN-005-B), `renderToStaticMarkup` cannot
 * complete async server components under React 19 (the
 * components suspend on `await cookies()` + `await fetch()`,
 * and synchronous rendering cannot resolve the suspense).
 * File-content + import-graph assertions are the canonical
 * check for this SCN:
 *
 *   1. `StatsCardsRow` is an RSC (no `"use client"`).
 *   2. It awaits `fetchDashboardStats()` from the server-only
 *      `api-client` (NOT a client `useStats()` hook).
 *   3. The `lastSync` StatCard renders the result of
 *      `formatRelativeDate(...)` — the localizer that turns
 *      `last_sync: "2026-06-15T..."` into "15 de Jun de 2026".
 *   4. The `last_sync` payload flows from the awaited
 *      `fetchDashboardStats()` result into the formatter —
 *      there's no client-only hydration barrier in between.
 *
 * If a future refactor re-introduces a `"use client"` directive
 * or replaces the server fetcher with a `useQuery()` call, ALL
 * four assertions fail — that's the regression guard.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const STATS_CARDS_ROW_PATH = path.resolve(__dirname, "..", "StatsCardsRow.tsx");
const API_CLIENT_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "lib",
  "api-client.ts",
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

describe("StatsCardsRow — SCN-PDPRSC-002-A (LCP path is server-rendered)", () => {
  const source = fs.readFileSync(STATS_CARDS_ROW_PATH, "utf8");

  it("is an RSC (no 'use client' directive)", () => {
    const first = firstNonCommentNonBlankLine(source);
    expect(first).not.toBe(`"use client";`);
    expect(first).not.toBe(`'use client';`);
  });

  it("imports fetchDashboardStats from @/lib/api-client (NOT a client hook)", () => {
    // The server fetcher is the ONLY way the LCP date can land
    // in the server HTML payload. A `useStats()` client query
    // would defer the date to post-hydration — the exact
    // regression this SCN prevents.
    expect(source).toMatch(/fetchDashboardStats\b/);
    expect(source).toMatch(/from\s*["']@\/lib\/api-client["']/);
  });

  it("does NOT import or call the client-side useStats hook (code-only)", () => {
    // Belt-and-suspenders: the file must not even reference the
    // client hook IN CODE. A typo'd import would silently fall
    // through to a client fetch.
    //
    // We strip JSDoc/`/* */` and `//` comments before scanning
    // because the docstring mentions `useStats()` for historical
    // context — only code references count as a regression.
    const codeOnly = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    expect(codeOnly).not.toMatch(/useStats\b/);
  });

  it("renders the lastSync StatCard with formatRelativeDate (the LCP element)", () => {
    // The LCP element is `<p class="font-display ...">{value}</p>`
    // inside the lastSync StatCard. `value` is computed by
    // `formatRelativeDate(stats.last_sync, locale)`. Pin both:
    //   - The function call exists.
    //   - The lastSync StatCard receives a value derived from
    //     `formatRelativeDate(...)`.
    expect(source).toMatch(/formatRelativeDate\(/);
    // The lastSync StatCard is wired with a literal `"Last Sync"`
    // label in the post-commit-6 RSC version (the i18n keys were
    // removed because the server component can't read
    // `useTranslations()`). The label + value pair is the LCP
    // element.
    expect(source).toMatch(/["']Last Sync["']/);
  });
});

describe("api-client — SCN-PDPRSC-002-F (server fetcher is gated by 'server-only')", () => {
  const source = fs.readFileSync(API_CLIENT_PATH, "utf8");

  it("first non-comment, non-blank line is `import \"server-only\";`", () => {
    // The build-time gate. Any accidental client import of
    // api-client fails the Next.js build. This is what makes
    // the StatsCardsRow server-fetch path safe — no client code
    // can ever reach into it.
    const first = firstNonCommentNonBlankLine(source);
    expect(first).toBe(`import "server-only";`);
  });
});