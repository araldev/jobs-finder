/**
 * Tests for SCN-PDPRSC-005-A (REQ-PDPRSC-005) —
 * `globals.css` MUST NOT contain a Google Fonts `@import` URL.
 *
 * The `next/font/google` self-hosting strategy in `app/layout.tsx`
 * (SCN-PDPRSC-005-B) eliminates the runtime dependency on
 * `fonts.googleapis.com`. The corresponding file change is
 * DELETE line 1 of `globals.css` (the `@import url(...)` line).
 * If that line is ever re-introduced, the page will start
 * blocking on the Google Fonts CDN again (~329ms render-
 * blocking). This test guards against regression.
 *
 * The test reads the file as text and asserts NO line matches
 * the canonical Google Fonts `@import` pattern. Pure string
 * scan — no module load, no jsdom gymnastics.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const GLOBALS_CSS_PATH = path.resolve(
  __dirname,
  "..",
  "globals.css",
);

describe("globals.css — SCN-PDPRSC-005-A (no Google Fonts @import)", () => {
  it("contains no @import url('https://fonts.googleapis.com/...')", () => {
    const content = fs.readFileSync(GLOBALS_CSS_PATH, "utf8");
    const googleFontsImportPattern =
      /^@import url\(['"]https:\/\/fonts\.googleapis\.com/m;

    const offendingLines = content
      .split("\n")
      .filter((line) => googleFontsImportPattern.test(line.trim()));

    expect(offendingLines).toEqual([]);
  });
});
